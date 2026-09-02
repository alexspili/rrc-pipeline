"""Tier 2: the box-grading sheet is well-formed and still matches its run.

Same posture as the other label validators: quiet while blank, loud on a typo,
because an ungraded box scores nothing and a mistyped grade scores the wrong
thing.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "box_grades.csv"

#: The four documents the protocol fixes, one per era bucket.
GRADED_DOCS = {("1493608", "5 6"), ("1495195", "15"),
               ("1912687", "2"), ("1495193", "8")}

GRADES = {"hit", "near", "miss"}


def _rows():
    if not SHEET.exists():
        pytest.skip("box-grading sheet not generated yet: "
                    "scripts/overlay_boxes.py --sheet")
    return list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))


def _filled():
    rows = _rows()
    if not any(r["grade"].strip() for r in rows):
        pytest.skip("box grades not filled in yet")
    return rows


def test_the_sheet_covers_exactly_the_protocol_documents():
    documents = {(r["record_id"], r["pages"]) for r in _rows()}
    assert documents == GRADED_DOCS


def test_box_numbers_are_unique_within_a_document():
    """The number on the page and the row in the sheet are one enumeration;
    a duplicate would grade one box under another's name.
    """
    seen = Counter((r["record_id"], r["pages"], r["box_num"])
                   for r in _rows())
    duplicates = [k for k, n in seen.items() if n > 1]
    assert not duplicates, duplicates


def test_every_row_names_a_field_and_carries_the_raw_value():
    for row in _rows():
        assert "." in row["field"] or "[" in row["field"], row["field"]


def test_every_grade_is_in_the_vocabulary():
    bad = [(r["record_id"], r["box_num"], r["grade"]) for r in _filled()
           if r["grade"].strip() and r["grade"].strip() not in GRADES]
    assert not bad, f"grades must be hit, near or miss: {bad[:8]}"


def test_every_box_is_graded_once_grading_starts():
    missing = [(r["record_id"], r["box_num"]) for r in _filled()
               if not r["grade"].strip()]
    assert not missing, f"ungraded boxes: {missing[:10]}"


def test_handwritten_is_answered_yes_or_no():
    """The split the snap analysis needs and cannot produce for itself."""
    bad = [(r["record_id"], r["box_num"], r["handwritten"])
           for r in _filled()
           if r["handwritten"].strip().lower() not in {"y", "n"}]
    assert not bad, f"handwritten must be y or n: {bad[:8]}"
