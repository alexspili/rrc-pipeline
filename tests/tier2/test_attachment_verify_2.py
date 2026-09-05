"""Tier 2: the second sitting's sheet is the one the rule specified.

The rule was written on 2026-09-04, before the three fixes existed. What is
worth testing is that the sheet obeys it rather than something that drifted
while the script was written, because this sitting gates the corpus spend.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "attachment_verify_2.csv"
FIRST = ROOT / "tests" / "fixtures" / "attachment_verify.csv"
VERDICTS = {"yes", "no", "cannot-tell"}


def _rows(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated")
    raw = path.read_bytes().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(raw)))


def test_no_pair_from_the_first_sitting_appears_again():
    """The whole point of a fresh sample. A rule built against the first eight
    cannot be judged on the first eight."""
    def key(row):
        return (row["record_id"], row["file_index"],
                tuple(sorted(row["pages"].split())))
    first = {key(r) for r in _rows(FIRST) if r["part"] == "A"}
    assert not {key(r) for r in _rows(SHEET)} & first


def test_the_sample_is_every_unjudged_attachment_not_a_subset():
    """The rule: fewer than eight means all are judged and the count is
    reported, never topped up. It also means never trimmed."""
    docs = ROOT / "data" / "extract" / "reassemble.jsonl"
    if not docs.exists():
        pytest.skip("run output is git-ignored, not present here")
    import json
    total = sum(len(json.loads(l)["pages"]) - 1
                for l in docs.open() if l.strip())
    judged = len([r for r in _rows(FIRST) if r["part"] == "A"])
    # 11 attachments, 4 of them pairs already judged
    assert len(_rows(SHEET)) == total - 4
    assert judged == 8


def test_every_pair_says_what_joined_it_and_where_the_values_came_from():
    for row in _rows(SHEET):
        assert row["joined_on"].strip(), row["item"]
        assert row["received_stamps"].strip(), row["item"]
        assert len(row["pages"].split()) == 2, row["item"]


def test_every_verdict_is_in_the_vocabulary():
    for row in _rows(SHEET):
        verdict = row["verdict"].strip().lower()
        if verdict:
            assert verdict in VERDICTS, f"{row['item']}: {verdict!r}"


def test_a_partly_judged_sheet_is_not_scored():
    rows = _rows(SHEET)
    filled = [r for r in rows if r["verdict"].strip()]
    if filled and len(filled) != len(rows):
        pytest.fail(f"partly judged: {len(filled)}/{len(rows)}. The gate is "
                    "every pair; finish it or clear it.")
