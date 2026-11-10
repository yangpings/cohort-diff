"""Part 7 eval runner. Step 7.3 adds the grader self-check; later steps add runs and reports.

uv run python scripts/llm_eval.py selfcheck
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from cohort_diff import engine, grade, registry
from cohort_diff.llm import Draft
from cohort_diff.synth import SynthConfig, generate

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "evals" / "items.jsonl"
TESTS = ROOT / "tests"
EVAL_DATA = SynthConfig(n_patients=2000, seed=0)  # the eval's synthetic data, fixed


def load_items() -> list[dict[str, Any]]:
    return [json.loads(line) for line in ITEMS.read_text(encoding="utf-8").splitlines() if line]


def _as_draft(item: dict[str, Any], sql: str, label: str) -> Draft:
    return Draft(item_id=str(item["id"]), condition=label, model="reference", effort="", sample=0,
                 rule_stated=True, sql=sql)  # fmt: skip


def selfcheck() -> int:
    """The grader must pass every reference and catch a planted boundary bug."""
    con = engine.connect(generate(EVAL_DATA))
    failures = 0
    for item in load_items():
        if not item["answerable"]:
            continue
        name = str(item["reference"])
        start = time.perf_counter()
        sql = registry.load(name).sql
        g = grade.grade(
            _as_draft(item, sql, "self"), item, con, grade.reference_ids(con, name), TESTS
        )
        ok = g.exact and g.tests is not False
        failures += not ok
        tests = {True: "pass", False: "FAIL", None: "n/a"}[g.tests]
        print(f"{'ok  ' if ok else 'FAIL'} {item['id']} {name:24} exact={g.exact} "
              f"tests={tests:4} ({time.perf_counter() - start:.0f} s) {g.detail}")  # fmt: skip
    # Planted bugs: one that synthetic data exposes (level 3), one only the tests catch (level 4).
    planted = [
        ("aki_kdigo_48h", ">= 0.3", "> 0.3"),
        ("dm_cheng2025", "WHERE icd_version = 10\n  AND icd_code", "WHERE icd_code"),
    ]
    for name, old, new in planted:
        item = next(i for i in load_items() if i["reference"] == name)
        good = registry.load(name).sql
        bad = good.replace(old, new)
        assert bad != good, f"the planted change to {name} did not apply"
        g = grade.grade(
            _as_draft(item, bad, "planted"), item, con, grade.reference_ids(con, name), TESTS
        )
        level = (
            "level 3 (cohort differs)"
            if not g.exact
            else "level 4 (tests)"
            if g.tests is False
            else ""
        )
        caught = g.runs and bool(level)
        failures += not caught
        status = "ok  " if caught else "FAIL"
        print(f"{status} planted {name}: {new!r} caught at {level or 'NOT CAUGHT'} "
              f"(jaccard {g.jaccard}) {g.detail}")  # fmt: skip
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selfcheck", help="grade every reference against itself, plus a planted bug")
    args = parser.parse_args()
    if args.command == "selfcheck":
        return selfcheck()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
