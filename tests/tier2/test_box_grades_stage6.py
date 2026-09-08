"""Tier 2: the stage-five sheet is well-formed, blinded, and matches its key.

Same posture as the stage-four validator: quiet while blank, loud on a typo,
and a test that the sheet does not carry the answer, because the blind is
the only thing standing between the grader and a mechanism he already has
an opinion about.
"""

from __future__ import annotations

import csv
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "box_grades_stage6.csv"
KEY = ROOT / "tests" / "fixtures" / "box_grades_stage6_key.csv"

GRADES = {"hit", "near", "miss"}
SOURCES = {"forms_kv", "forms_row", "template", "template_row",
           "model_filler"}


def _rows():
    if not SHEET.exists():
        pytest.skip("stage-five sheet not generated: "
                    "scripts/stage6_probe.py --sheet")
    return list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))


def test_the_sheet_does_not_carry_the_answer():
    rows = _rows()
    assert "source" not in rows[0]
    assert "orig_box_num" not in rows[0]
    blob = SHEET.read_text().lower()
    for source in SOURCES:
        assert source not in blob, f"{source} leaked into the blinded sheet"


def test_the_sheet_is_one_document_and_boxes_are_contiguous():
    rows = _rows()
    assert {r["record_id"] for r in rows} == {"1493608"}
    numbers = sorted(int(r["box_num"]) for r in rows)
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_row_names_a_field_and_carries_a_value_to_look_for():
    for row in _rows():
        assert "." in row["field"] or "[" in row["field"], row["field"]
        assert row["raw"].strip(), row["field"]


def test_the_answer_key_is_committed_not_ignored():
    """DEFECTS #36's lesson, inherited: the key cannot be regenerated once
    the sheet is graded, and it carries no personal data."""
    if not SHEET.exists():
        pytest.skip("sheet not generated")
    assert KEY.exists(), f"{KEY} is missing"
    ignored = subprocess.run(["git", "check-ignore", str(KEY)],
                             capture_output=True, cwd=ROOT).returncode == 0
    assert not ignored, "the answer key is git-ignored and cannot be recovered"


def test_the_key_matches_the_sheet_and_the_snap_tier_is_absent():
    """Snap is never regraded in stage six: it stands on its stage-four
    grades and cancels in the paired test. A text_layer row here would
    mean the sitting is grading the wrong mechanism."""
    if not KEY.exists():
        pytest.skip("key not present")
    key = list(csv.DictReader(KEY.open(encoding="utf-8-sig")))
    rows = _rows()
    assert {r["box_num"] for r in key} == {r["box_num"] for r in rows}
    sources = Counter(r["source"] for r in key)
    assert set(sources) <= SOURCES
    assert sources["model_filler"] == 5


def test_every_grade_is_in_the_vocabulary():
    for row in _rows():
        grade = row["grade"].strip()
        if grade:
            assert grade in GRADES, f"box {row['box_num']}: {grade!r}"


def test_a_partly_graded_sheet_is_reported_rather_than_scored():
    rows = _rows()
    filled = [r for r in rows if r["grade"].strip()]
    if filled and len(filled) != len(rows):
        pytest.fail(f"sheet is partly graded: {len(filled)}/{len(rows)}. "
                    "Finish it or clear it; do not score it.")
