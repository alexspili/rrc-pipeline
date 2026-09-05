"""Tier 2: the corpus extraction runner, which is the script that spends.

No API calls. What is checked is the part that cannot be checked afterwards:
that every document gets a distinct custom_id, because results come back keyed
by it and a collision silently gives one document another's values; and that
the two modes are the two modes the protocol elected, not two spellings of one.

Skips when data/ is absent, as data/ is never committed (CLAUDE.md rule 3).
"""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"

pytestmark = pytest.mark.skipif(
    not DOCS.exists(), reason="needs data/extract/reassemble.jsonl")


def _runner():
    spec = importlib.util.spec_from_file_location(
        "run_extraction", ROOT / "scripts" / "run_extraction.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_document_gets_a_distinct_custom_id():
    """A batch is addressed by custom_id and nothing else. Two documents
    sharing one means one overwrites the other, and the loss is invisible: the
    run reports the right number of results, with the wrong values in them.
    """
    docs = _runner().documents(faces_only=False)
    duplicates = [cid for cid, n in
                  Counter(d["custom_id"] for d in docs).items() if n > 1]
    assert not duplicates, f"custom_id collisions: {duplicates}"


def test_the_escape_mode_sends_one_page_per_document():
    """--faces-only is the elected escape for a failing fourth sitting: no
    attachment ships, so no document may carry a page it did not read alone.
    """
    docs = _runner().documents(faces_only=True)
    assert docs, "no documents built"
    assert {len(d["pages"]) for d in docs} == {1}


def test_the_two_modes_cover_the_same_documents():
    """The escape changes what each document contains, never which documents
    exist. A face that vanished under the escape would be a silent drop.
    """
    runner = _runner()
    grouped = {d["custom_id"] for d in runner.documents(faces_only=False)}
    faces = {d["custom_id"] for d in runner.documents(faces_only=True)}
    assert grouped == faces


def test_the_escape_is_a_strict_subset_of_the_grouped_pages():
    """Face-only must drop attached pages and add nothing."""
    runner = _runner()
    grouped = {d["custom_id"]: set(d["pages"])
               for d in runner.documents(faces_only=False)}
    for doc in runner.documents(faces_only=True):
        assert set(doc["pages"]) <= grouped[doc["custom_id"]]


def test_spending_needs_an_explicit_confirmation():
    """Every money-spending script in this repo refuses to start without it,
    and this is the most expensive one.
    """
    text = (ROOT / "scripts" / "run_extraction.py").read_text()
    assert "--confirm" in text
    assert "if not args.confirm:" in text
    assert "dry run. Nothing sent" in text
