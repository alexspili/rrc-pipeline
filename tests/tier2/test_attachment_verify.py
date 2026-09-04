"""Tier 2: the verification sheet matches the sample the protocol fixed.

This sitting gates the corpus spend, so the thing worth testing is that the
sample is the one that was pre-registered and not one that drifted while the
script was being written.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "attachment_verify.csv"
VERDICTS = {"yes", "no", "cannot-tell"}


def _rows():
    """Read the sheet whatever the grader's editor saved it as.

    Alex's notes came back with Mac Roman dashes, which made the file
    unreadable to a strict utf-8 reader. A grading sheet that breaks on a
    dash in somebody's note is a bad sheet, and the fix belongs here rather
    than in a request that he change editors.
    """
    if not SHEET.exists():
        pytest.skip("sheet not generated: scripts/make_verify_sheet.py")
    import io
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(raw)))


def test_part_a_is_the_eight_pairs_the_protocol_fixed():
    part_a = [r for r in _rows() if r["part"] == "A"]
    assert len(part_a) == 8
    reasons = Counter(r["in_sample_because"] for r in part_a)
    assert reasons["ground truth"] == 2
    assert reasons["flagged highest risk"] == 2
    assert reasons["random, seed 20260903"] == 4


def test_the_two_ground_truth_pairs_are_the_confirmed_cases():
    items = {r["item"] for r in _rows()
             if r["in_sample_because"] == "ground truth"}
    assert items == {"1493495-0 p10+p9", "1495193-0 p8+p7"}


def test_the_two_risk_pairs_are_the_ones_named_in_the_run_two_write_up():
    items = {r["item"] for r in _rows()
             if r["in_sample_because"] == "flagged highest risk"}
    assert items == {"1495195-0 p87+p52", "1495195-0 p114+p89"}


def test_every_part_a_pair_names_two_pages_and_what_joined_them():
    for row in (r for r in _rows() if r["part"] == "A"):
        assert len(row["pages"].split()) == 2, row["item"]
        assert row["detail"].startswith("joined on "), row["item"]


def test_twelve_found_in_rows_are_marked_for_checking():
    marked = [r for r in _rows() if r["part"] == "B" and r["check"] == "CHECK"]
    assert len(marked) == 12


def test_the_crawford_pair_is_carried_into_part_c():
    """Outside the ground-truth set, the first pair ever flagged, and never
    resolved. It is here so it does not get lost again."""
    assert any(r["part"] == "C" and r["record_id"] == "1493399"
               for r in _rows())


def test_every_verdict_is_in_the_vocabulary():
    for row in _rows():
        verdict = row["verdict"].strip().lower()
        if verdict:
            assert verdict in VERDICTS, f"{row['item']}: {verdict!r}"


def test_a_partly_filled_part_a_is_not_scored():
    part_a = [r for r in _rows() if r["part"] == "A"]
    filled = [r for r in part_a if r["verdict"].strip()]
    if filled and len(filled) != len(part_a):
        pytest.fail(f"part A is partly judged: {len(filled)}/{len(part_a)}. "
                    "The gate is all eight; finish it or clear it.")


def test_the_sheet_survives_whatever_encoding_it_comes_back_in():
    """Origin: the graded sheet came back with Mac Roman dashes in the notes
    and a strict utf-8 read raised on it. The sheet is read tolerantly and
    the verdict column, which is all ASCII, is unaffected."""
    rows = _rows()
    assert rows and "verdict" in rows[0]
    for row in rows:
        assert row["verdict"].strip().lower() in VERDICTS | {""}, row["item"]


def test_part_a_is_fully_judged_and_the_gate_has_fired():
    """The sitting of 2026-09-04: five of eight wrong, so no corpus spend.
    Pinned so that a later change cannot quietly restate the outcome."""
    part_a = [r for r in _rows() if r["part"] == "A"]
    verdicts = [r["verdict"].strip().lower() for r in part_a]
    if not all(verdicts):
        pytest.skip("part A not yet judged")
    assert verdicts.count("no") == 5
    assert verdicts.count("yes") == 3
