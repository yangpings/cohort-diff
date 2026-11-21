"""Part 7 eval runner. Step 7.3 adds the grader self-check; later steps add runs and reports.

uv run python scripts/llm_eval.py selfcheck
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

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


MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
FULL_RUN = 114  # drafts per model in a full run: (20 A + 18 B) x 3 samples


def correct(g: dict[str, Any]) -> bool:
    """Exact on synthetic data and no failing reference test (n/a counts as passed)."""
    return bool(g["exact"]) and g["tests"] is not False


def category(row: dict[str, Any]) -> str:
    """One failure category per draft, first match wins; "" for a correct draft."""
    d, g = row["draft"], row["grade"]
    if d["error"]:
        return "API error, refusal or cut off"
    if not g["answerable"]:
        return "" if g["abstained"] else "computed a rule where the text states none"
    if not g["runs"]:
        return "SQL error"
    if correct(g):
        return ""
    if g["exact"]:
        return "right cohort on synthetic data, fails a reference test"
    if g["jaccard"] >= 0.99:
        return "near miss (Jaccard >= 0.99)"
    return "different cohort (Jaccard < 0.99)"


def load_full_runs() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(RUNS.glob("*.jsonl")):
        file_rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        ]
        if len(file_rows) != FULL_RUN:
            continue  # pilots and interrupted runs
        for r in file_rows:
            r["file"] = path.name
        rows += file_rows
    return rows


def item_bootstrap(rows: list[dict[str, Any]], seed: int = 0, n: int = 2000) -> tuple[float, float]:
    """95% interval for the share correct, resampling whole items.

    A model's samples of one item are not independent, so items, not drafts, are resampled.
    """
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        by_item.setdefault(r["draft"]["item_id"], []).append(correct(r["grade"]))
    items = sorted(by_item)
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        drawn = [x for i in rng.choices(items, k=len(items)) for x in by_item[i]]
        stats.append(sum(drawn) / len(drawn))
    low, high = np.percentile(stats, [2.5, 97.5])
    return float(low), float(high)


def paired_difference(
    rows: list[dict[str, Any]], a: tuple[str, str], b: tuple[str, str], seed: int = 0, n: int = 2000
) -> tuple[float, float, float]:
    """Share correct of b minus a, item by item, with an item-bootstrap 95% interval."""

    def rate(model: str, cond: str, item: str) -> float:
        xs = [
            correct(r["grade"])
            for r in rows
            if r["draft"]["model"] == model
            and r["draft"]["condition"] == cond
            and r["draft"]["item_id"] == item
        ]
        return sum(xs) / len(xs)

    items = sorted({r["draft"]["item_id"] for r in rows if r["grade"]["answerable"]})
    diffs = {i: rate(*b, i) - rate(*a, i) for i in items}
    rng = random.Random(seed)
    boot = [float(np.mean([diffs[i] for i in rng.choices(items, k=len(items))])) for _ in range(n)]
    low, high = np.percentile(boot, [2.5, 97.5])
    return float(np.mean(list(diffs.values()))), float(low), float(high)


def _share(rows: list[dict[str, Any]]) -> float:
    return sum(correct(r["grade"]) for r in rows) / len(rows)


def analyze() -> int:
    rows = load_full_runs()
    files = sorted({r["file"] for r in rows})
    items = {i["id"]: i for i in load_items()}
    answerable = [r for r in rows if r["grade"]["answerable"]]
    cost = sum(r["cost_usd"] for r in rows)
    out = [
        "# Part 7 results",
        "",
        f"Full runs: {', '.join(files)} ({len(rows)} drafts, US${cost:.2f}).",
        "Correct = the same admissions as the reference on synthetic data"
        " and no failing reference test.",
        "Intervals: 95%, bootstrap over the 18 items (a draft's samples are not independent).",
        "",
        "## Share of drafts correct",
        "",
        "| Model | Condition | Correct | 95% CI | Drafts | By run |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for model in MODELS:
        for cond in ("A", "B"):
            sel = [
                r
                for r in answerable
                if r["draft"]["model"] == model and r["draft"]["condition"] == cond
            ]
            k = sum(correct(r["grade"]) for r in sel)
            low, high = item_bootstrap(sel)
            by_run = " / ".join(
                f"{_share([r for r in sel if r['file'] == f]):.0%}"
                for f in files
                if any(r["file"] == f for r in sel)
            )
            out.append(
                f"| {model} | {cond} | {k / len(sel):.0%} | {low:.0%}-{high:.0%} | {len(sel)} "
                f"| {by_run} |"
            )
    out += [
        "",
        "## Paired differences (share correct, item by item)",
        "",
        "| Comparison | Difference | 95% CI |",
        "| --- | --- | --- |",
    ]
    pairs = [((m, "A"), (m, "B")) for m in MODELS] + [
        ((MODELS[0], "B"), (MODELS[2], "B")),
        ((MODELS[0], "A"), (MODELS[2], "A")),
    ]
    for a, b in pairs:
        diff, low, high = paired_difference(rows, a, b)
        out.append(
            f"| {b[0]} {b[1]} minus {a[0]} {a[1]} | {diff:+.0%} | {low:+.0%} to {high:+.0%} |"
        )
    out += [
        "",
        "## Items with no computable rule: share that said so",
        "",
        "| Item | " + " | ".join(MODELS) + " |",
        "| --- |" + " --- |" * len(MODELS),
    ]
    for iid, item in items.items():
        if item["answerable"]:
            continue
        cells = []
        for model in MODELS:
            sel = [r for r in rows if r["draft"]["model"] == model and r["draft"]["item_id"] == iid]
            cells.append(f"{sum(bool(r['grade']['abstained']) for r in sel)}/{len(sel)}")
        out.append(f"| {iid} {item['label']} | " + " | ".join(cells) + " |")
    out += [
        "",
        "## Correct drafts per item (of 6 per model and condition)",
        "",
        "| Item | Definition | A: "
        + " / ".join(m.split("-")[1] for m in MODELS)
        + " | B: "
        + " / ".join(m.split("-")[1] for m in MODELS)
        + " |",
        "| --- | --- | --- | --- |",
    ]
    for iid, item in items.items():
        if not item["answerable"]:
            continue
        cells = []
        for cond in ("A", "B"):
            counts = []
            for model in MODELS:
                sel = [
                    r
                    for r in rows
                    if r["draft"]["model"] == model
                    and r["draft"]["condition"] == cond
                    and r["draft"]["item_id"] == iid
                ]
                counts.append(str(sum(correct(r["grade"]) for r in sel)))
            cells.append(" / ".join(counts))
        out.append(f"| {iid} | {item['label']} | {cells[0]} | {cells[1]} |")
    out += [
        "",
        "## Failure categories (every failed draft, one category each)",
        "",
        "| Category | " + " | ".join(MODELS) + " |",
        "| --- |" + " --- |" * len(MODELS),
    ]
    cats = sorted({category(r) for r in rows} - {""})
    for c in cats:
        out.append(
            f"| {c} | "
            + " | ".join(
                str(sum(category(r) == c for r in rows if r["draft"]["model"] == m)) for m in MODELS
            )
            + " |"
        )
    rounded = [
        r
        for r in answerable
        if "round(" in registry.load(str(items[r["draft"]["item_id"]]["reference"])).sql.lower()
    ]
    unrounded = sum("round(" not in r["draft"]["sql"].lower() for r in rounded)
    out += [
        "",
        f"Of {len(rounded)} drafts for definitions that round the creatinine comparison "
        f"(floating point), {unrounded} do not round it.",
        "",
    ]
    text = "\n".join(out)
    (ROOT / "evals" / "results.md").write_text(text, encoding="utf-8")
    print(text)
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
    sub.add_parser("analyze", help="results from the full runs in evals/runs (no API calls)")
    args = parser.parse_args()
    if args.command == "selfcheck":
        return selfcheck()
    if args.command == "analyze":
        return analyze()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
