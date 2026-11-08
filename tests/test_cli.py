from __future__ import annotations

from pathlib import Path

import pytest

from cohort_diff.cli import main


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("synth")
    assert main(["synth", "--out", str(root), "--patients", "80"]) == 0
    return root


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--condition", "aki"]) == 0
    out = capsys.readouterr().out
    assert "aki_kdigo_48h" in out and "dm_icd" not in out


def test_run_and_compare(data: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "ids.csv"
    assert main(["run", "aki_icd", "--data", str(data), "--out", str(out)]) == 0
    assert out.read_text().startswith("hadm_id")
    report = tmp_path / "r.md"
    args = ["compare", "--condition", "aki", "--data", str(data), "--out", str(report)]
    assert main([*args, "--bootstrap", "50"]) == 0
    text = report.read_text()
    assert "Pairwise overlap" in text and "Uncertainty (patient-level bootstrap)" in text


def test_compare_needs_two(data: Path) -> None:
    assert main(["compare", "aki_icd", "--data", str(data)]) == 2


def test_missing_data(tmp_path: Path) -> None:
    assert main(["run", "aki_icd", "--data", str(tmp_path)]) == 2


def test_list_with_an_unknown_condition_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    # "AKI" used to print nothing and exit 0, which reads as "no such definitions".
    assert main(["list", "--condition", "AKI"]) == 2
    err = capsys.readouterr().err
    assert "unknown condition 'AKI'" in err
    assert "aki, diabetes, readmission" in err


def test_compare_with_an_unknown_condition_does_not_ask_for_two_definitions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["compare", "--condition", "AKI", "--data", "unused"]) == 2
    assert "unknown condition 'AKI'" in capsys.readouterr().err


def test_compare_rejects_a_condition_and_definition_names_together(
    data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The names used to be dropped without a word once --condition was given.
    assert main(["compare", "aki_icd", "--condition", "aki", "--data", str(data)]) == 2
    assert "give --condition or definition names, not both" in capsys.readouterr().err


def test_broken_definition_sql_is_reported_not_raised(
    data: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.sql"
    bad.write_text(
        "-- name: bad\n-- condition: aki\n-- description: d\n-- reference: r\n"
        "SELECT hadm_id FROM nowhere\n"
    )
    assert main(["run", str(bad), "--data", str(data)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: definition 'bad' failed:")
    assert "nowhere" in err


def test_negative_bootstrap_is_rejected(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # It used to be skipped silently, so the report had no uncertainty section.
    with pytest.raises(SystemExit) as exit_info:
        main(["compare", "aki_icd", "aki_kdigo_48h", "--data", str(data), "--bootstrap", "-5"])
    assert exit_info.value.code == 2
    assert "--bootstrap" in capsys.readouterr().err


def test_zero_bootstrap_still_skips_the_uncertainty_section(data: Path, tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    args = ["compare", "aki_icd", "aki_kdigo_48h", "--data", str(data), "--bootstrap", "0"]
    assert main([*args, "--out", str(report)]) == 0
    assert "Uncertainty" not in report.read_text()


def test_synth_rejects_a_non_positive_patient_count(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["synth", "--out", str(tmp_path / "s"), "--patients", "0"])
    assert exit_info.value.code == 2


def test_compare_shows_where_the_cohorts_disagree(data: Path, tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    args = ["compare", "aki_icd", "aki_kdigo_48h", "--data", str(data), "--bootstrap", "0"]
    assert main([*args, "--out", str(report)]) == 0
    text = report.read_text()
    assert "## Where the cohorts disagree" in text
    assert "mortality_both_pct" in text


def test_run_prints_the_admission_ids_to_stdout(
    data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["run", "aki_icd", "--data", str(data)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "hadm_id" and all(line.isdigit() for line in out[1:])
