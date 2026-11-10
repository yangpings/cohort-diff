"""Part 7 eval runner. Step 7.3 adds the grader self-check; later steps add runs and reports.

uv run python scripts/llm_eval.py selfcheck
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cohort_diff import engine, grade, llm, registry
from cohort_diff.llm import Draft
from cohort_diff.synth import SynthConfig, generate

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "evals" / "items.jsonl"
TESTS = ROOT / "tests"
EVAL_DATA = SynthConfig(n_patients=2000, seed=0)  # the eval's synthetic data, fixed
RUNS = ROOT / "evals" / "runs"
# US$ per million tokens (input, output), first-party API list prices on 2026-11-10.
# Thinking tokens are billed as output and are included in output_tokens.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


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


def run(args: argparse.Namespace) -> int:
    """Draft, grade and log. Every draft is a line in a new file; nothing is overwritten."""
    unknown = [m for m in args.models if m not in PRICES]
    if unknown:
        raise SystemExit(f"no price for {unknown}; add it to PRICES first")
    items = [i for i in load_items() if not args.items or i["id"] in args.items]
    con = engine.connect(generate(EVAL_DATA))
    references = {
        str(i["reference"]): grade.reference_ids(con, str(i["reference"]))
        for i in items
        if i["answerable"]
    }
    client = llm.anthropic_client()
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    total = 0.0
    with out.open("x", encoding="utf-8") as f:
        for model in args.models:
            for item in items:
                for condition in args.conditions:
                    if condition == "B" and not item["answerable"]:
                        continue
                    for sample in range(args.samples):
                        d = llm.draft(client, item, condition, model, args.effort, sample)
                        ref = references.get(str(item["reference"]))
                        g = grade.grade(d, item, con, ref, TESTS if args.tests else None)
                        price_in, price_out = PRICES[model]
                        cost = (d.input_tokens * price_in + d.output_tokens * price_out) / 1e6
                        total += cost
                        row = {"draft": asdict(d), "grade": asdict(g), "cost_usd": round(cost, 5)}
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        level = (
                            4 if g.tests else 3 if g.exact else 2 if g.runs else 1 if g.valid else 0
                        )
                        print(f"{model} {item['id']} {condition} s{sample}: level {level} "
                              f"abstained={g.abstained} jaccard={g.jaccard} ${cost:.4f} "
                              f"{d.error or g.detail}")  # fmt: skip
    print(f"wrote {out.relative_to(ROOT)}; total ${total:.4f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selfcheck", help="grade every reference against itself, plus planted bugs")
    r = sub.add_parser("run", help="draft with the API, grade and log (costs money)")
    r.add_argument("--models", nargs="+", required=True)
    r.add_argument("--items", nargs="*", default=[], help="item ids (default: all 20)")
    r.add_argument("--conditions", nargs="+", default=list(llm.CONDITIONS), choices=llm.CONDITIONS)
    r.add_argument("--samples", type=int, default=1)
    r.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    r.add_argument("--tests", action="store_true", help="also run level 4 (slow)")
    args = parser.parse_args()
    if args.command == "selfcheck":
        return selfcheck()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
