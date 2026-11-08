"""Compare cohorts: overlap, who is in them, and how a downstream result moves.

The downstream result is deliberately simple and common in papers: the odds
ratio between cohort membership and in-hospital mortality. If that number
changes a lot between definitions of "the same" condition, so would the
conclusions of any study built on it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

# Haldane-Anscombe correction: half an admission in every cell when exactly one cell is
# empty, so a single empty cell does not send the estimate to zero or infinity.
CORRECTION = 0.5


@dataclass(frozen=True)
class OddsRatio:
    """An odds ratio, or the reason it has none.

    ``note`` is empty when the ratio exists. Otherwise ``estimate``, ``low`` and ``high``
    are NaN and ``note`` names the margin that is empty.
    """

    estimate: float
    low: float
    high: float
    note: str = ""

    @property
    def estimable(self) -> bool:
        return not self.note


def jaccard(a: set[int], b: set[int]) -> float:
    """Size of the intersection over size of the union; 1.0 when both are empty."""
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def overlap_table(cohorts: dict[str, set[int]]) -> pd.DataFrame:
    """One row per pair of definitions."""
    rows = []
    for (na, a), (nb, b) in combinations(cohorts.items(), 2):
        rows.append(
            {
                "a": na,
                "b": nb,
                "n_a": len(a),
                "n_b": len(b),
                "both": len(a & b),
                "only_a": len(a - b),
                "only_b": len(b - a),
                "jaccard": round(jaccard(a, b), 3),
            }
        )
    return pd.DataFrame(rows)


def _empty_margin(cells: np.ndarray) -> str:
    """Why a 2x2 table has no odds ratio, or "" when it has one."""
    a, b, c, d = cells
    if a + b == 0:
        return "no admissions in the cohort"
    if c + d == 0:
        return "no admissions outside the cohort"
    if a + c == 0:
        return "no deaths in either group"
    if b + d == 0:
        return "every admission died"
    return ""


def _corrected(cells: np.ndarray) -> np.ndarray:
    return cells + CORRECTION if (cells == 0).any() else cells


def odds_ratio(exposed: np.ndarray, outcome: np.ndarray) -> OddsRatio:
    """Woolf (log) 95% interval, with a 0.5 continuity correction when one cell is 0.

    An odds ratio needs both groups and both outcomes to be non-empty. When a whole
    margin is empty the correction divides by a zero margin and answers from the group
    sizes alone (an empty cohort "had" an OR of 14, a cohort with no deaths "had" one
    below 1), so those tables come back as NaN with the reason in ``note`` instead.
    """
    e, y = exposed.astype(bool), outcome.astype(bool)
    cells = np.array([(e & y).sum(), (e & ~y).sum(), (~e & y).sum(), (~e & ~y).sum()], dtype=float)
    note = _empty_margin(cells)
    if note:
        return OddsRatio(float("nan"), float("nan"), float("nan"), note)
    a, b, c, d = _corrected(cells)
    log_or = math.log((a * d) / (b * c))
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return OddsRatio(math.exp(log_or), math.exp(log_or - 1.96 * se), math.exp(log_or + 1.96 * se))


def _weighted_or(weights: np.ndarray, exposed: np.ndarray, outcome: np.ndarray) -> float | None:
    """Odds ratio from a 2x2 table of summed weights, None when a margin is empty."""
    cells = np.array(
        [
            weights @ (exposed & outcome),
            weights @ (exposed & ~outcome),
            weights @ (~exposed & outcome),
            weights @ (~exposed & ~outcome),
        ],
        dtype=float,
    )
    if _empty_margin(cells):
        return None
    a, b, c, d = _corrected(cells)
    return float((a * d) / (b * c))


def _interval(draws: np.ndarray) -> tuple[float, float]:
    """Percentile interval over the draws that have a value; NaN when none has one."""
    known = draws[np.isfinite(draws)]
    if known.size == 0:
        return float("nan"), float("nan")
    low, high = np.percentile(known, [2.5, 97.5])
    return float(low), float(high)


def bootstrap_pairs(
    cohorts: dict[str, set[int]],
    admissions: pd.DataFrame,
    n_boot: int = 1000,
    seed: int = 0,
) -> pd.DataFrame:
    """95% percentile intervals, per pair of definitions, for the Jaccard index and
    for the ratio of their mortality odds ratios (OR of a / OR of b).

    Patients are resampled, not admissions: one patient's admissions are not
    independent. A patient drawn k times contributes each of their admissions k times.
    A ratio of ORs whose interval excludes 1 means the two definitions give
    different answers to "is this condition associated with mortality, and how much".

    A resample in which a cohort has no deaths, or no admissions at all, has no ratio to
    contribute, so those draws are left out of the interval; it is NaN only when no draw
    had one. ``or_ratio_note`` names the cohorts whose observed table has an empty
    margin, which is also when the point estimate is NaN.
    """
    patients, patient_idx = np.unique(admissions["subject_id"].to_numpy(), return_inverse=True)
    n_patients = len(patients)
    died = admissions["hospital_expire_flag"].to_numpy().astype(bool)
    member = {n: admissions["hadm_id"].isin(ids).to_numpy() for n, ids in cohorts.items()}
    pairs = list(combinations(member, 2))
    jac = np.empty((len(pairs), n_boot))
    ratio = np.empty((len(pairs), n_boot))
    rng = np.random.default_rng(seed)
    for r in range(n_boot):
        drawn = np.bincount(rng.integers(0, n_patients, n_patients), minlength=n_patients)
        weights = drawn[patient_idx].astype(float)
        for k, (na, nb) in enumerate(pairs):
            a, b = member[na], member[nb]
            union = weights @ (a | b)
            jac[k, r] = (weights @ (a & b)) / union if union > 0 else 1.0
            or_a, or_b = _weighted_or(weights, a, died), _weighted_or(weights, b, died)
            ratio[k, r] = np.nan if or_a is None or or_b is None else or_a / or_b
    rows = []
    for k, (na, nb) in enumerate(pairs):
        a, b = member[na], member[nb]
        odds_a, odds_b = odds_ratio(a, died), odds_ratio(b, died)
        notes = [f"{n}: {r.note}" for n, r in ((na, odds_a), (nb, odds_b)) if r.note]
        j_low, j_high = _interval(jac[k])
        r_low, r_high = _interval(ratio[k])
        rows.append(
            {
                "a": na,
                "b": nb,
                "jaccard": round(jaccard(cohorts[na], cohorts[nb]), 3),
                "jaccard_low": round(j_low, 3),
                "jaccard_high": round(j_high, 3),
                "or_ratio": round(odds_a.estimate / odds_b.estimate, 2),
                "or_ratio_low": round(r_low, 2),
                "or_ratio_high": round(r_high, 2),
                "or_ratio_note": "; ".join(notes),
            }
        )
    return pd.DataFrame(rows)


def _mortality_pct(died: np.ndarray, mask: np.ndarray) -> float:
    """Percentage of the masked admissions that died; NaN when the mask is empty."""
    return round(float(died[mask].mean()) * 100, 1) if mask.any() else float("nan")


def describe(cohorts: dict[str, set[int]], admissions: pd.DataFrame) -> pd.DataFrame:
    """Size, prevalence, demographics and the mortality odds ratio per definition.

    ``mortality_or`` is NaN when its 2x2 table has an empty margin and ``or_note`` says
    which one: an empty cohort has no odds ratio, it is not some large number.
    """
    rows = []
    n_total = len(admissions)
    died = admissions["hospital_expire_flag"].to_numpy().astype(bool)
    hadm = admissions["hadm_id"]
    for name, ids in cohorts.items():
        member = hadm.isin(ids).to_numpy()
        sub = admissions[member]
        ratio = odds_ratio(member, died)
        rows.append(
            {
                "definition": name,
                "n": int(member.sum()),
                "prevalence": round(member.mean(), 4) if n_total else float("nan"),
                "age_mean": round(float(sub["age"].mean()), 1) if len(sub) else float("nan"),
                "female_pct": round(float((sub["gender"] == "F").mean() * 100), 1)
                if len(sub)
                else float("nan"),
                "mortality_pct": _mortality_pct(died, member),
                "mortality_or": round(ratio.estimate, 2),
                "or_low": round(ratio.low, 2),
                "or_high": round(ratio.high, 2),
                "or_note": ratio.note,
            }
        )
    return pd.DataFrame(rows)


def exclusive_mortality(cohorts: dict[str, set[int]], admissions: pd.DataFrame) -> pd.DataFrame:
    """Mortality among admissions in both definitions and in only one of them.

    A ratio of odds ratios says that two definitions disagree; this says where. An
    "only" group whose mortality is far from the shared group means the definitions
    select different severities, not just different numbers of admissions.
    """
    died = admissions["hospital_expire_flag"].to_numpy().astype(bool)
    hadm = admissions["hadm_id"]
    member = {name: hadm.isin(ids).to_numpy() for name, ids in cohorts.items()}
    rows = []
    for na, nb in combinations(member, 2):
        a, b = member[na], member[nb]
        rows.append(
            {
                "a": na,
                "b": nb,
                "n_both": int((a & b).sum()),
                "n_only_a": int((a & ~b).sum()),
                "n_only_b": int((b & ~a).sum()),
                "mortality_both_pct": _mortality_pct(died, a & b),
                "mortality_only_a_pct": _mortality_pct(died, a & ~b),
                "mortality_only_b_pct": _mortality_pct(died, b & ~a),
            }
        )
    return pd.DataFrame(rows)


def _cell(value: object) -> str:
    """A table cell: numbers as printed, a missing number as "n/a"."""
    if isinstance(value, float) and math.isnan(value):
        return "n/a"
    return str(value)


def _notes(
    frame: pd.DataFrame, column: str, label: Callable[[pd.Series], str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """The frame without its note column, plus "label (why)" for every note in it."""
    if column not in frame.columns:
        return frame, []
    name = label or (lambda row: str(row.iloc[0]))
    notes = [f"{name(row)} ({row[column]})" for _, row in frame.iterrows() if row[column]]
    return frame.drop(columns=column), notes


def to_markdown(
    overlap: pd.DataFrame,
    description: pd.DataFrame,
    title: str,
    uncertainty: pd.DataFrame | None = None,
    exclusive: pd.DataFrame | None = None,
) -> str:
    """The report: cohorts, pairwise overlap, where they disagree, and uncertainty."""

    def table(frame: pd.DataFrame) -> str:
        header = "| " + " | ".join(frame.columns) + " |"
        sep = "| " + " | ".join("---" for _ in frame.columns) + " |"
        body = [
            "| " + " | ".join(_cell(v) for v in row) + " |" for row in frame.itertuples(index=False)
        ]
        return "\n".join([header, sep, *body])

    cohorts, cohort_notes = _notes(description, "or_note")
    text = f"# {title}\n\n## Cohorts\n\n{table(cohorts)}\n\n"
    if cohort_notes:
        text += "Odds ratio not estimable: " + "; ".join(cohort_notes) + ".\n\n"
    text += (
        f"## Pairwise overlap\n\n{table(overlap)}\n\n"
        "Odds ratios: in-hospital mortality for members vs non-members, Woolf 95% CI.\n"
    )
    if exclusive is not None and len(exclusive):
        text += (
            f"\n## Where the cohorts disagree\n\n{table(exclusive)}\n\n"
            "Mortality among admissions in both definitions and in only one of them. A large "
            'gap between the "only" columns means the definitions select different\n'
            "severities, not just different numbers of admissions.\n"
        )
    if uncertainty is not None:

        def pair_label(row: pd.Series) -> str:
            return f"{row['a']} vs {row['b']}"

        draws, ratio_notes = _notes(uncertainty, "or_ratio_note", pair_label)
        text += (
            f"\n## Uncertainty (patient-level bootstrap)\n\n{table(draws)}\n\n"
            "95% percentile intervals. or_ratio = mortality OR of a / OR of b; "
            "an interval excluding 1 means the definitions disagree on the association.\n"
        )
        if ratio_notes:
            text += "Ratio of odds ratios not estimable: " + "; ".join(ratio_notes) + ".\n"
    return text
