"""Draft a cohort definition from methods text with an LLM (Part 7).

Only the item text and the table and column names below are sent to the API, never
patient data. The Anthropic SDK is an optional dependency (``cohort-diff[llm]``): it is
imported only when a real client is created, so tests and normal installs don't need it.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from importlib import resources
from typing import Any, Protocol

# The columns the built-in definitions use, as in MIMIC-IV (hosp/ and icu/ modules).
SCHEMA: dict[str, tuple[str, ...]] = {
    "patients": ("subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"),
    "admissions": (
        "subject_id", "hadm_id", "admittime", "dischtime", "deathtime", "admission_type",
        "admission_location", "discharge_location", "hospital_expire_flag",
    ),
    "diagnoses_icd": ("subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"),
    "labevents": (
        "labevent_id", "subject_id", "hadm_id", "itemid", "charttime", "valuenum", "valueuom",
    ),
    "d_labitems": ("itemid", "label", "fluid", "category"),
    "prescriptions": ("subject_id", "hadm_id", "starttime", "stoptime", "drug"),
    "icustays": ("subject_id", "hadm_id", "stay_id", "intime", "outtime"),
    "chartevents": ("subject_id", "hadm_id", "stay_id", "charttime", "itemid", "valuenum"),
}  # fmt: skip

# What the model must return. Every field is required; no other field is allowed.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "condition": {"type": "string", "enum": ["aki", "diabetes", "readmission"]},
        "rule_stated": {"type": "boolean"},
        "sql": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "condition", "rule_stated", "sql", "assumptions"],
    "additionalProperties": False,
}

SYSTEM = """You write cohort definitions for MIMIC-IV as DuckDB SQL.

The database has these tables and columns (MIMIC-IV names; times are TIMESTAMP):
{schema}

Write one SELECT query that returns exactly one column, hadm_id: the admissions that meet the
definition, each once. Use only the tables and columns above. Follow the text exactly: keep its
numbers, windows and inequality signs. Where the text leaves a choice open, make it and list it
in "assumptions". If the text does not state a rule that can be computed without inventing a
number, code list or time window, set "rule_stated" to false, return the SQL
"SELECT NULL::BIGINT AS hadm_id WHERE false", and say what is missing in "assumptions"."""

CONDITIONS = ("A", "B")  # A: the item's methods text; B: the reference's full SQL header


class MessagesClient(Protocol):
    """The part of ``anthropic.Anthropic`` used here, so tests can pass a fake."""

    @property
    def messages(self) -> Any: ...


@dataclass(frozen=True)
class Draft:
    """One model answer for one item, or the reason there is none (``error``)."""

    item_id: str
    condition: str
    model: str
    effort: str
    sample: int
    name: str = ""
    cohort_condition: str = ""
    rule_stated: bool = False
    sql: str = ""
    assumptions: tuple[str, ...] = ()
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


def schema_text() -> str:
    return "\n".join(f"- {table}({', '.join(cols)})" for table, cols in SCHEMA.items())


def spec_header(definition: str) -> str:
    """The comment header of a built-in definition, without its query (condition B)."""
    text = (resources.files("cohort_diff") / "definitions" / f"{definition}.sql").read_text()
    lines = []
    for line in text.splitlines():
        if not line.lstrip().startswith("--"):
            break
        lines.append(line)
    return "\n".join(lines)


def prompt(item: dict[str, Any], condition: str) -> str:
    """The user message for one item in condition A or B."""
    if condition == "A":
        return f"Methods text ({item['citation']}):\n\n{item['text']}"
    if condition == "B":
        if not item["answerable"]:
            raise ValueError(f"{item['id']} has no reference definition, so no condition B")
        return f"Specification:\n\n{spec_header(str(item['reference']))}"
    raise ValueError(f"unknown condition {condition!r}; known: {', '.join(CONDITIONS)}")


def request(item: dict[str, Any], condition: str, model: str, effort: str) -> dict[str, Any]:
    """The keyword arguments for ``client.messages.create``.

    No server-side fallbacks: a refused request must stay a refusal of this model, not be
    answered by another one, or the eval would grade the wrong model.
    """
    return {
        "model": model,
        "max_tokens": 16000,
        "system": SYSTEM.format(schema=schema_text()),
        "messages": [{"role": "user", "content": prompt(item, condition)}],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
    }


def draft(
    client: MessagesClient,
    item: dict[str, Any],
    condition: str,
    model: str,
    effort: str = "high",
    sample: int = 0,
) -> Draft:
    """Ask the model for one draft. API errors are returned as a Draft with ``error`` set."""
    result = Draft(
        item_id=str(item["id"]), condition=condition, model=model, effort=effort, sample=sample
    )
    try:
        response = client.messages.create(**request(item, condition, model, effort))
    except Exception as exc:  # any SDK or network error is a result to log, not a crash
        return replace(result, error=f"api: {type(exc).__name__}: {exc}")
    result = replace(
        result,
        stop_reason=str(response.stop_reason),
        input_tokens=int(response.usage.input_tokens),
        output_tokens=int(response.usage.output_tokens),
    )
    if response.stop_reason != "end_turn":
        return replace(result, error=f"stop_reason: {response.stop_reason}")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        return replace(
            result,
            name=str(data["name"]),
            cohort_condition=str(data["condition"]),
            rule_stated=bool(data["rule_stated"]),
            sql=str(data["sql"]),
            assumptions=tuple(str(a) for a in data["assumptions"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return replace(result, error=f"schema: {type(exc).__name__}: {exc}")


def anthropic_client() -> MessagesClient:
    """A real client; needs ``pip install cohort-diff[llm]`` and ANTHROPIC_API_KEY."""
    try:
        sdk = importlib.import_module("anthropic")
    except ImportError as exc:
        raise RuntimeError("the LLM extension needs: uv sync --extra llm") from exc
    client: MessagesClient = sdk.Anthropic()
    return client
