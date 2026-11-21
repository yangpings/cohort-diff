"""Grade an LLM-drafted definition against its reference (Part 7).

Four levels, each only tried when the one before passed:
1. valid: the model returned a well-formed answer (no API error, refusal or broken JSON);
2. runs: the SQL runs on DuckDB and returns exactly one column;
3. exact: it selects the same admissions as the reference on the eval's synthetic data;
4. tests: every test file that names the reference passes with the draft swapped in.
For an item with no computable rule, the grade is whether the model said so.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from cohort_diff import engine, registry
from cohort_diff.llm import Draft

# Test files that only exercise the eval machinery, not definitions.
NOT_DEFINITION_TESTS = {"oracles.py", "conftest.py", "test_llm.py", "test_grade.py"}
OVERRIDE_ENV = "COHORT_DIFF_DRAFT"


@dataclass(frozen=True)
class Grade:
    item_id: str
    condition: str
    model: str
    sample: int
    answerable: bool
    valid: bool = False
    runs: bool = False
    exact: bool = False
    tests: bool | None = None  # None: not tried, or no test file names the reference
    abstained: bool | None = None  # only for items without a computable rule
    n_draft: int = 0
    n_reference: int = 0
    jaccard: float = 0.0
    detail: str = ""


def run_sql(con: duckdb.DuckDBPyConnection, sql: str) -> set[int]:
    """The admissions a draft selects; raises ValueError unless it returns one column."""
    try:
        cursor = con.execute(sql)
    except duckdb.Error as exc:
        raise ValueError(f"SQL error: {exc}") from exc
    if len(cursor.description or []) != 1:
        raise ValueError(f"returns {len(cursor.description or [])} columns, not 1")
    return {int(r[0]) for r in cursor.fetchall() if r[0] is not None}


def test_files(reference: str, tests_dir: Path) -> list[Path]:
    """Every test file that names the reference definition."""
    return sorted(
        p
        for p in tests_dir.glob("*.py")
        if p.name not in NOT_DEFINITION_TESTS and reference in p.read_text(encoding="utf-8")
    )


def run_tests(reference: str, sql: str, tests_dir: Path) -> tuple[bool | None, str]:
    """Run the reference's test files with the draft SQL in its place (see conftest.py)."""
    files = test_files(reference, tests_dir)
    if not files:
        return None, "no test file names the reference"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "draft.sql"
        path.write_text(sql, encoding="utf-8")
        env = {**os.environ, OVERRIDE_ENV: f"{reference}={path}"}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider",
             "-x", *map(str, files)],
            env=env, capture_output=True, text=True, check=False,
        )  # fmt: skip
    last = (result.stdout.strip().splitlines() or [""])[-1]
    return result.returncode == 0, last


def grade(
    draft: Draft,
    item: dict[str, Any],
    con: duckdb.DuckDBPyConnection,
    reference_ids: set[int] | None,
    tests_dir: Path | None = None,
) -> Grade:
    """Grade one draft. ``reference_ids`` is None for an item without a computable rule.

    Pass ``tests_dir`` to run level 4; leave it out for a fast grade (levels 1-3).
    """
    g = Grade(
        item_id=draft.item_id,
        condition=draft.condition,
        model=draft.model,
        sample=draft.sample,
        answerable=bool(item["answerable"]),
    )
    if draft.error:
        return _with(g, detail=draft.error)
    g = _with(g, valid=True)
    if not g.answerable:
        return _with(g, abstained=not draft.rule_stated)
    if reference_ids is None:
        raise ValueError(f"{draft.item_id} is answerable but has no reference admissions")
    try:
        ids = run_sql(con, draft.sql)
    except ValueError as exc:
        return _with(g, detail=str(exc))
    union = ids | reference_ids
    g = _with(
        g,
        runs=True,
        n_draft=len(ids),
        n_reference=len(reference_ids),
        jaccard=round(len(ids & reference_ids) / len(union), 3) if union else 1.0,
        exact=ids == reference_ids,
    )
    if not g.exact or tests_dir is None:
        return g
    passed, detail = run_tests(str(item["reference"]), draft.sql, tests_dir)
    return _with(g, tests=passed, detail=detail)


def _with(g: Grade, **changes: Any) -> Grade:
    return Grade(**{**g.__dict__, **changes})


def reference_ids(con: duckdb.DuckDBPyConnection, name: str) -> set[int]:
    """The reference definition's admissions on the same data."""
    return engine.run(con, registry.load(name))
