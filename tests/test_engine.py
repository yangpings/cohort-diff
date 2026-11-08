from __future__ import annotations

import pandas as pd
import pytest

from cohort_diff import engine, registry


def _tables() -> dict[str, pd.DataFrame]:
    when = pd.Timestamp("2150-01-01")
    return {
        "patients": pd.DataFrame(
            {
                "subject_id": [1, 2],
                "gender": ["F", "M"],
                "anchor_age": [50, 60],
                "anchor_year": [2150, 2150],
            }
        ),
        "admissions": pd.DataFrame(
            {
                "hadm_id": [10, 11],
                "subject_id": [1, 2],
                "hospital_expire_flag": [0, 1],
                "admittime": [when, when + pd.Timedelta(days=5)],
                "dischtime": [when + pd.Timedelta(days=2), when + pd.Timedelta(days=7)],
                "discharge_location": ["HOME", "DIED"],
                "admission_type": ["EW EMER.", "EW EMER."],
            }
        ),
        "labevents": pd.DataFrame(
            {
                "hadm_id": [10],
                "itemid": [50912],
                "valuenum": [1.0],
                "charttime": [when],
            }
        ),
        "d_labitems": pd.DataFrame(
            {"itemid": [50912], "label": ["Creatinine"], "fluid": ["Blood"]}
        ),
        "diagnoses_icd": pd.DataFrame({"hadm_id": [10], "icd_code": ["N17"], "icd_version": [10]}),
    }


def _definition(sql: str) -> registry.Definition:
    return registry.Definition(
        name="probe", condition="aki", description="d", reference="r", sql=sql
    )


def test_run_reads_the_admission_id_column() -> None:
    con = engine.connect(_tables())
    assert engine.run(con, registry.load("aki_icd")) == {10}


def test_run_rejects_a_definition_with_more_than_one_column() -> None:
    # SELECT hadm_id, subject_id used to return the first column and look fine.
    con = engine.connect(_tables())
    with pytest.raises(ValueError, match=r"'probe' must return one column.*hadm_id, subject_id"):
        engine.run(con, _definition("SELECT hadm_id, subject_id FROM admissions"))


def test_run_rejects_admission_ids_that_are_not_integers() -> None:
    con = engine.connect(_tables())
    with pytest.raises(
        ValueError, match=r"'probe' returned a non-integer admission id \(str: 'F'\)"
    ):
        engine.run(con, _definition("SELECT gender FROM patients"))


def test_run_skips_null_admission_ids() -> None:
    con = engine.connect(_tables())
    sql = "SELECT hadm_id FROM admissions UNION ALL SELECT NULL"
    assert engine.run(con, _definition(sql)) == {10, 11}


def test_run_names_the_definition_when_its_sql_fails() -> None:
    con = engine.connect(_tables())
    with pytest.raises(
        ValueError, match=r"'probe' failed: .*Table with name nowhere does not exist"
    ):
        engine.run(con, _definition("SELECT hadm_id FROM nowhere"))
