"""The Part 7 eval set: 20 items, frozen before any model is run."""

from __future__ import annotations

import json
from pathlib import Path

from cohort_diff import registry

ITEMS = Path(__file__).resolve().parent.parent / "evals" / "items.jsonl"
FIELDS = {"id", "reference", "label", "condition", "source", "answerable", "citation", "text"}


def _items() -> list[dict[str, object]]:
    return [json.loads(line) for line in ITEMS.read_text(encoding="utf-8").splitlines() if line]


def test_twenty_items_with_unique_ids() -> None:
    items = _items()
    assert len(items) == 20
    assert len({i["id"] for i in items}) == 20
    assert all(set(i) == FIELDS for i in items)


def test_every_definition_is_an_item_exactly_once() -> None:
    references = [i["reference"] for i in _items() if i["answerable"]]
    assert sorted(references) == sorted(registry.builtin())


def test_references_match_their_condition() -> None:
    builtin = registry.builtin()
    for item in _items():
        if item["answerable"]:
            assert builtin[str(item["reference"])].condition == item["condition"]
        else:
            assert item["reference"] is None


def test_texts_are_short_cited_excerpts() -> None:
    for item in _items():
        assert item["source"] in {"author", "code", "paper"}
        assert str(item["citation"]).strip()
        assert 5 <= len(str(item["text"]).split()) <= 300
