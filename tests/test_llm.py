"""Part 7: prompt building and response parsing, with a fake client (no network, no key)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from cohort_diff import llm

ITEM = {
    "id": "item99",
    "reference": "aki_kdigo_48h",
    "label": "aki_kdigo_48h",
    "condition": "aki",
    "source": "author",
    "answerable": True,
    "citation": "A test citation.",
    "text": "Serum creatinine rises by >= 0.3 mg/dL within 48 hours.",
}
GOOD = {
    "name": "aki_test",
    "condition": "aki",
    "rule_stated": True,
    "sql": "SELECT hadm_id FROM admissions",
    "assumptions": ["creatinine is itemid 50912"],
}


@dataclass
class Block:
    type: str
    text: str = ""


@dataclass
class Usage:
    input_tokens: int = 1200
    output_tokens: int = 300


@dataclass
class Response:
    content: list[Block]
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


class FakeMessages:
    def __init__(self, reply: Response | Exception) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeClient:
    def __init__(self, reply: Response | Exception) -> None:
        self.messages = FakeMessages(reply)


def _text(data: object) -> Response:
    return Response([Block("thinking"), Block("text", json.dumps(data))])


def test_prompt_a_is_the_methods_text_with_its_citation() -> None:
    text = llm.prompt(ITEM, "A")
    assert ITEM["text"] in text
    assert "A test citation." in text


def test_prompt_b_is_the_reference_header_without_its_query() -> None:
    text = llm.prompt(ITEM, "B")
    assert "-- name: aki_kdigo_48h" in text
    assert all(line.startswith("--") for line in text.split("\n\n", 1)[1].splitlines())
    assert "SELECT" not in text


def test_no_condition_b_for_an_item_without_a_reference() -> None:
    with pytest.raises(ValueError, match="no reference"):
        llm.prompt({**ITEM, "answerable": False, "reference": None}, "B")


def test_request_uses_structured_output_and_sends_no_data() -> None:
    req = llm.request(ITEM, "A", "claude-haiku-5-5", "high")
    assert req["output_config"]["format"]["schema"] == llm.OUTPUT_SCHEMA
    assert req["output_config"]["effort"] == "high"
    assert "fallbacks" not in req and "temperature" not in req
    assert "hadm_id" in req["system"] and "labevents(" in req["system"]


def test_a_good_answer_becomes_a_draft() -> None:
    client = FakeClient(_text(GOOD))
    d = llm.draft(client, ITEM, "A", "claude-haiku-5-5", sample=2)
    assert d.error == ""
    assert (d.sql, d.rule_stated, d.sample) == (GOOD["sql"], True, 2)
    assert d.assumptions == ("creatinine is itemid 50912",)
    assert (d.input_tokens, d.output_tokens) == (1200, 300)
    assert client.messages.calls[0]["model"] == "claude-haiku-5-5"


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (Response([Block("text", "")], stop_reason="refusal"), "stop_reason: refusal"),
        (Response([Block("text", "{")], stop_reason="max_tokens"), "stop_reason: max_tokens"),
        (Response([Block("text", "not json")]), "schema: JSONDecodeError"),
        (_text({k: v for k, v in GOOD.items() if k != "sql"}), "schema: KeyError"),
        (ConnectionError("network down"), "api: ConnectionError: network down"),
    ],
)
def test_every_failure_is_kept_as_a_draft_with_its_reason(
    reply: Response | Exception, error: str
) -> None:
    d = llm.draft(FakeClient(reply), ITEM, "A", "claude-haiku-5-5")
    assert d.error.startswith(error)
    assert d.sql == ""


def test_the_real_client_is_optional() -> None:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="--extra llm"):
            llm.anthropic_client()


def test_unknown_condition_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown condition"):
        llm.prompt(ITEM, "C")
