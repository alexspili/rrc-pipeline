"""Tier 2: the stage-four sheet is well-formed, blinded, and matches its key.

Same posture as the stage-two validator: quiet while blank, loud on a typo.
One extra job here, because this sheet is blinded: a test that the sheet does
not carry the answer. A source column that leaked into the committed CSV
would end the blind without anybody noticing, and the blind is the only thing
standing between the grader and a mechanism he already has an opinion about.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "box_grades_probe.csv"
KEY = ROOT / "data" / "labelset" / "overlay_probe" / \
    "KEY_do_not_open_until_graded.csv"

GRADES = {"hit", "near", "miss"}
SOURCES = {"template", "template_row", "text_layer"}


def _rows():
    if not SHEET.exists():
        pytest.skip("stage-four sheet not generated: "
                    "scripts/probe_boxes.py --sheet")
    return list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))


def test_the_sheet_does_not_carry_the_answer():
    rows = _rows()
    assert "source" not in rows[0]
    blob = SHEET.read_text().lower()
    for source in SOURCES:
        assert source not in blob, f"{source} leaked into the blinded sheet"


def test_the_sheet_is_one_document_and_the_expected_size():
    rows = _rows()
    assert {r["record_id"] for r in rows} == {"1493608"}
    assert len(rows) == 33
    assert Counter(r["page"] for r in rows) == {"5": 14, "6": 19}


def test_box_numbers_are_unique_and_contiguous():
    numbers = sorted(int(r["box_num"]) for r in _rows())
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_row_names_a_field_and_carries_a_value_to_look_for():
    for row in _rows():
        assert "." in row["field"] or "[" in row["field"], row["field"]
        assert row["raw"].strip(), row["field"]


def test_the_key_matches_the_sheet_and_holds_the_pre_registered_mix():
    if not KEY.exists():
        pytest.skip("key is git-ignored corpus output, not present here")
    key = list(csv.DictReader(KEY.open(encoding="utf-8-sig")))
    rows = _rows()
    assert {r["box_num"] for r in key} == {r["box_num"] for r in rows}
    assert Counter(r["source"] for r in key) == {
        "text_layer": 15, "template": 12, "template_row": 6}


def test_every_grade_is_in_the_vocabulary():
    for row in _rows():
        grade = row["grade"].strip()
        if grade:
            assert grade in GRADES, f"box {row['box_num']}: {grade!r}"


def test_a_partly_graded_sheet_is_reported_rather_than_scored():
    """The scorer refuses a half-filled sheet. A rule applied to 20 of 33
    boxes is a different rule from the one that was pre-registered."""
    rows = _rows()
    filled = [r for r in rows if r["grade"].strip()]
    if filled and len(filled) != len(rows):
        pytest.fail(f"sheet is partly graded: {len(filled)}/{len(rows)}. "
                    "Finish it or clear it; do not score it.")
