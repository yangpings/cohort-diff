from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from cohort_diff import registry
from cohort_diff.synth import SynthConfig, generate


@pytest.fixture(scope="session")
def tables() -> dict[str, pd.DataFrame]:
    return generate(SynthConfig(n_patients=400, seed=3))


@pytest.fixture(scope="session", autouse=True)
def draft_in_place_of_reference() -> Iterator[None]:
    """Part 7 grading: with COHORT_DIFF_DRAFT=name=path, tests see the draft's SQL as ``name``.

    Unset (always, outside grading), this does nothing.
    """
    spec = os.environ.get("COHORT_DIFF_DRAFT")
    if not spec:
        yield
        return
    name, path = spec.split("=", 1)
    original = registry.builtin()
    patched = {**original, name: replace(original[name], sql=Path(path).read_text())}
    # registry.load looks names up through registry.builtin, so patching builtin is enough.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(registry, "builtin", lambda: dict(patched))
        yield
