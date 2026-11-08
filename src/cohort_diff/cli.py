"""Command-line interface: ``cohort-diff <command> --help``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from cohort_diff import compare, engine, registry


def _conditions() -> list[str]:
    """The condition names the built-in definitions use, sorted."""
    return sorted({d.condition for d in registry.builtin().values()})


def _check_condition(condition: str) -> None:
    """Raise unless ``condition`` is one of the built-in ones.

    A typo used to print nothing (``list``) or claim that two definitions were needed
    (``compare``), which reads like an empty repository rather than a wrong name.
    """
    known = _conditions()
    if condition not in known:
        raise ValueError(f"unknown condition {condition!r}; known: {', '.join(known)}")


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, not {value}")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, not {value}")
    return value


def _list(args: argparse.Namespace) -> None:
    if args.condition:
        _check_condition(args.condition)
    for d in registry.builtin().values():
        if args.condition and d.condition != args.condition:
            continue
        print(f"{d.name:<16} {d.condition:<12} {d.description}")


def _run(args: argparse.Namespace) -> None:
    con = engine.connect(args.data)
    ids = sorted(engine.run(con, registry.load(args.definition)))
    out = "\n".join(["hadm_id", *map(str, ids)]) + "\n"
    if args.out:
        Path(args.out).write_text(out)
        print(f"{len(ids)} admissions -> {args.out}")
    else:
        sys.stdout.write(out)


def _compare(args: argparse.Namespace) -> None:
    if args.condition:
        _check_condition(args.condition)
        if args.definitions:
            raise ValueError("give --condition or definition names, not both")
        defs = [d for d in registry.builtin().values() if d.condition == args.condition]
    else:
        defs = [registry.load(n) for n in args.definitions]
    if len(defs) < 2:
        raise ValueError("compare needs at least two definitions")
    con = engine.connect(args.data)
    cohorts = {d.name: engine.run(con, d) for d in defs}
    admissions = engine.admissions_frame(con)
    uncertainty = (
        compare.bootstrap_pairs(cohorts, admissions, n_boot=args.bootstrap, seed=args.seed)
        if args.bootstrap > 0
        else None
    )
    report = compare.to_markdown(
        compare.overlap_table(cohorts),
        compare.describe(cohorts, admissions),
        title=f"cohort-diff: {', '.join(cohorts)}",
        uncertainty=uncertainty,
        exclusive=compare.exclusive_mortality(cohorts, admissions),
    )
    if args.out:
        Path(args.out).write_text(report)
    print(report)


def _synth(args: argparse.Namespace) -> None:
    from cohort_diff.synth import SynthConfig, generate

    root = Path(args.out)
    for name, frame in generate(SynthConfig(n_patients=args.patients, seed=args.seed)).items():
        folder = root / ("icu" if name == "icustays" else "hosp")  # MIMIC-IV layout
        folder.mkdir(parents=True, exist_ok=True)
        frame.to_csv(folder / f"{name}.csv.gz", index=False)
    print(f"wrote synthetic MIMIC-shaped tables to {root} (synthetic data, not real patients)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cohort-diff", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show built-in definitions")
    p.add_argument("--condition")
    p.set_defaults(func=_list)

    p = sub.add_parser("run", help="admissions meeting one definition")
    p.add_argument("definition", help="built-in name or path to a .sql file")
    p.add_argument("--data", required=True)
    p.add_argument("--out")
    p.set_defaults(func=_run)

    p = sub.add_parser("compare", help="overlap and downstream differences between definitions")
    p.add_argument("definitions", nargs="*", help="two or more names or .sql paths")
    p.add_argument("--condition", help="compare every built-in definition of this condition")
    p.add_argument("--data", required=True)
    p.add_argument("--out", help="write the markdown report here")
    p.add_argument("--bootstrap", type=_non_negative_int, default=1000, help="resamples (0 = skip)")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=_compare)

    p = sub.add_parser("synth", help="write synthetic MIMIC-shaped tables")
    p.add_argument("--out", required=True)
    p.add_argument("--patients", type=_positive_int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=_synth)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, KeyError, ValueError, duckdb.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
