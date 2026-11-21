"""Part 7: the grader, checked on known-good and known-bad drafts (levels 1-3, fast)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cohort_diff import engine, grade, registry
from cohort_diff.llm import Draft

TESTS = Path(__file__).resolve().parent
ITEM = {"id": "item02", "reference": "aki_kdigo_48h", "answerable": True}
NO_RULE = {"id": "item19", "reference": None, "answerable": False}


@pytest.fixture(scope="module")
def con(tables: dict[str, pd.DataFrame]):  # type: ignore[no-untyped-def]
    return engine.connect(tables)


def _draft(sql: str, **kw: object) -> Draft:
    return Draft(
        item_id="item02", condition="A", model="fake", effort="high", sample=0, sql=sql, **kw
    )  # type: ignore[arg-type]


def _reference(con) -> set[int]:  # type: ignore[no-untyped-def]
    return grade.reference_ids(con, "aki_kdigo_48h")


def test_the_reference_itself_is_exact(con) -> None:  # type: ignore[no-untyped-def]
    g = grade.grade(_draft(registry.load("aki_kdigo_48h").sql), ITEM, con, _reference(con))
    assert (g.valid, g.runs, g.exact, g.jaccard) == (True, True, True, 1.0)


def test_an_api_failure_stops_at_level_1(con) -> None:  # type: ignore[no-untyped-def]
    g = grade.grade(_draft("", error="stop_reason: refusal"), ITEM, con, _reference(con))
    assert (g.valid, g.runs, g.detail) == (False, False, "stop_reason: refusal")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT hadm_id FROM no_such_table",
        "SELECT hadm_id, subject_id FROM admissions",
    ],
)
def test_sql_that_fails_or_returns_two_columns_stops_at_level_2(con, sql: str) -> None:  # type: ignore[no-untyped-def]
    g = grade.grade(_draft(sql), ITEM, con, _reference(con))
    assert (g.valid, g.runs) == (True, False)


def test_a_different_cohort_stops_at_level_3_with_its_jaccard(con) -> None:  # type: ignore[no-untyped-def]
    g = grade.grade(_draft("SELECT hadm_id FROM admissions"), ITEM, con, _reference(con))
    assert (g.runs, g.exact) == (True, False)
    assert 0 < g.jaccard < 1 and g.n_draft > g.n_reference


def test_an_item_without_a_rule_is_graded_on_abstaining(con) -> None:  # type: ignore[no-untyped-def]
    said_so = grade.grade(_draft("", rule_stated=False), NO_RULE, con, None)
    invented = grade.grade(
        _draft("SELECT hadm_id FROM admissions", rule_stated=True), NO_RULE, con, None
    )
    assert (said_so.abstained, invented.abstained) == (True, False)


def test_level_4_runs_the_files_that_name_the_reference() -> None:
    names = {p.name for p in grade.test_files("readmit_shen2025", TESTS)}
    assert names == {"test_readmission_published.py"}
    assert grade.test_files("not_a_definition", TESTS) == []


def test_level_4_tests_the_draft_not_the_reference() -> None:
    # A Shen draft without the 1-day rule: its hand-made boundary test must fail, which only
    # happens if the tests really see the draft in place of the reference.
    good = registry.load("readmit_shen2025").sql
    bad = good.replace(">= dischtime + INTERVAL 1 DAY", "> dischtime")
    assert bad != good
    assert grade.run_tests("readmit_shen2025", good, TESTS)[0] is True
    assert grade.run_tests("readmit_shen2025", bad, TESTS)[0] is False
