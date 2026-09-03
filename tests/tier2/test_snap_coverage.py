"""Tier 2: the display band was added beside the measurement, not over it.

`display_box` is what a reviewer is shown. `snapped_box` is the word that
actually matched, and it is the evidence every snap number in
docs/modules/extract.md rests on. The two must not be confused, and adding
the first must not move the second.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "data" / "extract" / "snap_coverage.jsonl"

#: Recorded in docs/modules/extract.md. 173 of 562 present values located,
#: 30.8%. If this test fails, a published number moved.
EXPECTED = {"unique": 166, "disambiguated": 7, "ambiguous": 16,
            "no_match": 262, "unanchored": 111}


def _rows():
    if not SNAP.exists():
        pytest.skip("snap results are git-ignored output, not present here")
    return [json.loads(line) for line in SNAP.open() if line.strip()]


def test_the_outcome_histogram_is_the_one_the_documents_quote():
    assert Counter(r["outcome"] for r in _rows()) == EXPECTED


def test_the_located_rate_is_still_the_published_308_percent():
    rows = _rows()
    located = sum(1 for r in rows
                  if r["outcome"] in ("unique", "disambiguated"))
    assert located == 173 and len(rows) == 562
    assert round(located / len(rows) * 100, 1) == 30.8


def test_display_box_is_present_exactly_when_snapped_box_is():
    for row in _rows():
        assert (row.get("display_box") is None) == (row["snapped_box"] is None)


def test_the_display_band_always_contains_the_word_it_displays():
    for row in _rows():
        box, band = row["snapped_box"], row.get("display_box")
        if box is None:
            continue
        assert band[0] <= box[0] and band[1] <= box[1]
        assert band[2] >= box[2] and band[3] >= box[3]
