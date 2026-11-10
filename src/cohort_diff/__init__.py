"""cohort-diff: how different are "the same" EHR cohorts?"""

from cohort_diff.compare import bootstrap_pairs, describe, jaccard, overlap_table
from cohort_diff.engine import connect, run
from cohort_diff.registry import Definition, builtin, load

__version__ = "0.2.0"

__all__ = [
    "Definition",
    "__version__",
    "bootstrap_pairs",
    "builtin",
    "connect",
    "describe",
    "jaccard",
    "load",
    "overlap_table",
    "run",
]
