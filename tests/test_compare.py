from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cohort_diff.compare import (
    bootstrap_pairs,
    describe,
    exclusive_mortality,
    jaccard,
    odds_ratio,
    overlap_table,
    to_markdown,
)
from cohort_diff.engine import admissions_frame, connect
from cohort_diff.registry import builtin

sets = st.sets(st.integers(0, 50), max_size=30)


@given(sets, sets)
def test_jaccard_properties(a: set[int], b: set[int]) -> None:
    j = jaccard(a, b)
    assert 0.0 <= j <= 1.0
    assert j == jaccard(b, a)
    assert jaccard(a, a) == 1.0


def test_overlap_counts() -> None:
    t = overlap_table({"x": {1, 2, 3}, "y": {3, 4}})
    row = t.iloc[0]
    assert (row["both"], row["only_a"], row["only_b"]) == (1, 2, 1)
    assert row["jaccard"] == 0.25


def test_odds_ratio_known_table() -> None:
    # a=20, b=80, c=10, d=90 -> OR = (20*90)/(80*10) = 2.25
    exposed = np.r_[np.ones(100), np.zeros(100)]
    outcome = np.r_[np.ones(20), np.zeros(80), np.ones(10), np.zeros(90)]
    r = odds_ratio(exposed, outcome)
    assert abs(r.estimate - 2.25) < 1e-9
    assert r.low < 2.25 < r.high


def test_odds_ratio_zero_cell_is_finite() -> None:
    r = odds_ratio(np.array([1, 1, 0, 0]), np.array([0, 0, 1, 0]))
    assert np.isfinite(r.estimate)


def test_describe_and_markdown() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4],
            "hospital_expire_flag": [1, 0, 0, 1],
            "age": [60, 70, 80, 90],
            "gender": ["F", "M", "F", "M"],
        }
    )
    d = describe({"x": {1, 2}, "y": set()}, adm)
    assert d.loc[0, "n"] == 2 and d.loc[0, "mortality_pct"] == 50.0
    md = to_markdown(overlap_table({"x": {1, 2}, "y": set()}), d, "t")
    assert md.startswith("# t") and "| definition |" in md


def test_bootstrap_identical_cohorts_has_no_spread() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4, 5, 6],
            "subject_id": [1, 1, 2, 3, 4, 5],
            "hospital_expire_flag": [1, 0, 0, 1, 0, 0],
        }
    )
    t = bootstrap_pairs({"x": {1, 3, 5}, "y": {1, 3, 5}}, adm, n_boot=200)
    row = t.iloc[0]
    assert (row["jaccard_low"], row["jaccard_high"]) == (1.0, 1.0)
    assert (row["or_ratio_low"], row["or_ratio_high"]) == (1.0, 1.0)


def test_bootstrap_resamples_patients_not_admissions() -> None:
    # Patient 1: 10 admissions in both cohorts. Patient 2: 10 admissions only in x.
    # Resampling 2 patients, Jaccard can only be 0, 0.5 or 1, and both extremes
    # happen a quarter of the time, so the 95% interval is [0, 1]. Resampling
    # admissions instead would give a narrow interval around 0.5.
    adm = pd.DataFrame(
        {
            "hadm_id": range(20),
            "subject_id": [1] * 10 + [2] * 10,
            "hospital_expire_flag": [0, 1] * 10,
        }
    )
    t = bootstrap_pairs({"x": set(range(20)), "y": set(range(10))}, adm, n_boot=1000)
    assert (t.loc[0, "jaccard_low"], t.loc[0, "jaccard_high"]) == (0.0, 1.0)


def test_bootstrap_on_synthetic(tables: dict[str, pd.DataFrame]) -> None:
    con = connect(tables)
    defs = builtin()
    cohorts = {
        n: set(con.execute(defs[n].sql).fetchnumpy()["hadm_id"].tolist())
        for n in ("aki_icd", "aki_kdigo_48h", "aki_kdigo_7d")
    }
    t = bootstrap_pairs(cohorts, admissions_frame(con), n_boot=100, seed=1)
    assert len(t) == 3
    assert (t["jaccard_low"] <= t["jaccard"]).all() and (t["jaccard"] <= t["jaccard_high"]).all()
    assert (t["or_ratio_low"] < t["or_ratio_high"]).all()
    again = bootstrap_pairs(cohorts, admissions_frame(con), n_boot=100, seed=1)
    pd.testing.assert_frame_equal(t, again)


def test_odds_ratio_is_not_estimable_without_an_exposed_group() -> None:
    # 0.5 used to be added to every cell, so the "odds ratio" of a cohort nobody is
    # in came out as the ratio of the group sizes (9.0 here) instead of being absent.
    r = odds_ratio(np.zeros(4, dtype=bool), np.zeros(4, dtype=bool))
    assert not r.estimable
    assert math.isnan(r.estimate) and math.isnan(r.low) and math.isnan(r.high)
    assert r.note == "no admissions in the cohort"


def test_odds_ratio_is_not_estimable_without_a_single_event() -> None:
    r = odds_ratio(np.array([True, True, False, False]), np.zeros(4, dtype=bool))
    assert not r.estimable and r.note == "no deaths in either group"


def test_odds_ratio_is_not_estimable_when_everybody_died() -> None:
    r = odds_ratio(np.array([True, True, False, False]), np.ones(4, dtype=bool))
    assert not r.estimable and r.note == "every admission died"


def test_odds_ratio_still_corrects_a_single_empty_cell() -> None:
    # Every margin is non-zero, so the (Haldane) 0.5 correction keeps the estimate:
    # 2 exposed without the outcome, 1 unexposed with it and 1 without.
    r = odds_ratio(np.array([True, True, False, False]), np.array([False, False, True, False]))
    assert r.estimable and r.note == ""
    assert math.isfinite(r.estimate) and r.low < r.estimate < r.high


def test_describe_reports_an_empty_cohort_as_not_estimable() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4],
            "hospital_expire_flag": [0, 1, 0, 1],
            "age": [60, 70, 80, 90],
            "gender": ["F", "M", "F", "M"],
        }
    )
    d = describe({"ghost": {99}}, adm)
    assert d.loc[0, "n"] == 0
    assert math.isnan(d.loc[0, "mortality_or"])
    assert d.loc[0, "or_note"] == "no admissions in the cohort"
    md = to_markdown(overlap_table({"ghost": {99}}), d, "t")
    assert "| n/a |" in md
    assert "Odds ratio not estimable: ghost (no admissions in the cohort)." in md
    assert "or_note" not in md


def test_markdown_notes_the_reason_a_pair_has_no_ratio() -> None:
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4],
            "subject_id": [1, 2, 3, 4],
            "hospital_expire_flag": [0, 0, 0, 0],
            "age": [60, 70, 80, 90],
            "gender": ["F", "M", "F", "M"],
        }
    )
    cohorts = {"x": {1, 2}, "y": {2, 3}}
    t = bootstrap_pairs(cohorts, adm, n_boot=20)
    row = t.iloc[0]
    assert math.isnan(row["or_ratio"]) and math.isnan(row["or_ratio_low"])
    assert row["or_ratio_note"] == "x: no deaths in either group; y: no deaths in either group"
    assert row["jaccard"] == pytest.approx(1 / 3, abs=1e-3)
    md = to_markdown(overlap_table(cohorts), describe(cohorts, adm), "t", uncertainty=t)
    assert "Ratio of odds ratios not estimable: x vs y" in md
    assert "or_ratio_note" not in md


def test_bootstrap_ratio_uses_the_draws_that_are_estimable() -> None:
    # Patients 1 and 3 each carry the only death of their cohort, so a resample that
    # draws neither of them has no event to compare: those draws are left out of the
    # percentile instead of turning the whole interval into nan.
    adm = pd.DataFrame(
        {
            "hadm_id": [1, 2, 3, 4],
            "subject_id": [1, 2, 3, 4],
            "hospital_expire_flag": [1, 0, 1, 1],
        }
    )
    t = bootstrap_pairs({"x": {1, 2}, "y": {3, 4}}, adm, n_boot=200, seed=0)
    row = t.iloc[0]
    assert math.isfinite(row["or_ratio_low"])
    assert row["or_ratio_low"] < row["or_ratio_high"]


def test_exclusive_mortality_splits_each_pair_three_ways() -> None:
    adm = pd.DataFrame({"hadm_id": [1, 2, 3, 4], "hospital_expire_flag": [1, 0, 1, 0]})
    t = exclusive_mortality({"x": {1, 2, 3}, "y": {3, 4}}, adm)
    row = t.iloc[0]
    assert (row["a"], row["b"]) == ("x", "y")
    assert (row["n_both"], row["n_only_a"], row["n_only_b"]) == (1, 2, 1)
    assert row["mortality_both_pct"] == 100.0  # admission 3 died
    assert row["mortality_only_a_pct"] == 50.0  # 1 died, 2 survived
    assert row["mortality_only_b_pct"] == 0.0  # admission 4 survived


def test_exclusive_mortality_is_nan_for_an_empty_group() -> None:
    adm = pd.DataFrame({"hadm_id": [1, 2, 3, 4], "hospital_expire_flag": [1, 0, 1, 0]})
    t = exclusive_mortality({"x": {3, 4}, "y": {1, 2, 3, 4}}, adm)
    assert t.loc[0, "n_only_a"] == 0
    assert math.isnan(t.loc[0, "mortality_only_a_pct"])


def test_exclusive_mortality_needs_two_cohorts() -> None:
    adm = pd.DataFrame({"hadm_id": [1], "hospital_expire_flag": [0]})
    assert exclusive_mortality({"x": {1}}, adm).empty


def test_markdown_renders_the_exclusive_table() -> None:
    adm = pd.DataFrame({"hadm_id": [1, 2, 3, 4], "hospital_expire_flag": [1, 0, 1, 0]})
    cohorts = {"x": {1, 2, 3}, "y": {3, 4}}
    adm = adm.assign(age=[60, 70, 80, 90], gender=["F", "M", "F", "M"])
    md = to_markdown(
        overlap_table(cohorts),
        describe(cohorts, adm),
        "t",
        exclusive=exclusive_mortality(cohorts, adm),
    )
    assert "## Where the cohorts disagree" in md
    assert "| both | only a | only b |" not in md
    assert "| a | b | n_both |" in md


def test_markdown_accepts_a_description_table_without_a_note_column() -> None:
    # Callers that build their own table (no notes) still get a report.
    description = pd.DataFrame({"definition": ["x"], "n": [1], "mortality_or": [2.0]})
    md = to_markdown(overlap_table({"x": {1}, "y": {2}}), description, "t")
    assert "| definition | n | mortality_or |" in md
    assert "not estimable" not in md
