"""Tier 2: the held-out sitting is actually held out.

DEFECTS #56. The first draw put four pairs Alex had already judged onto a
blinded sheet, and sixteen rows of thirty came from records whose page images
he had already looked at. The frame excluded the records that had informed the
CODE and never asked which had informed the JUDGE.
"""

from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "make_paper_sheet.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _sheet_script():
    spec = importlib.util.spec_from_file_location("make_paper_sheet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def judged_records() -> set:
    out = set()
    for path in sorted(FIXTURES.glob("attachment_verify*.csv")):
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for row in csv.DictReader(io.StringIO(raw)):
            if row.get("record_id"):
                out.add(row["record_id"].strip())
    return out


def test_the_sitting_excludes_records_alex_has_seen():
    """Every record on any verification sheet, plus the ones shown in
    conversation. Derived from the sheets so the list cannot drift.
    """
    excluded = _sheet_script().seen_by_alex()
    missing = judged_records() - excluded
    assert not missing, f"records Alex judged but not excluded: {sorted(missing)}"


def test_the_exclusion_covers_the_records_whose_marks_were_inspected():
    module = _sheet_script()
    assert set(module.INSPECTED) <= module.seen_by_alex()


def test_the_exclusion_list_is_derived_not_hardcoded():
    """A remembered list goes stale the first time a sheet is added."""
    text = SCRIPT.read_text()
    assert "attachment_verify*.csv" in text


def test_a_built_sheet_contains_no_record_alex_has_seen():
    """The end-to-end check. Skips until a sheet exists."""
    sheet = FIXTURES / "paper_sitting.csv"
    verdicts = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"
    if not (sheet.exists() and verdicts.exists()):
        pytest.skip("no sitting built yet")
    import json
    sealed = json.loads(verdicts.read_text())["verdicts"]
    excluded = _sheet_script().seen_by_alex()
    offenders = sorted({v["record_id"] for v in sealed.values()
                        if v["record_id"] in excluded})
    assert not offenders, f"sitting rows from records Alex has seen: {offenders}"


# ------------------------------ the development / held-out split, 2026-09-06

SPLIT = FIXTURES / "paper_record_split.csv"


def _split_rows():
    if not SPLIT.exists():
        pytest.skip("split not written yet")
    return list(csv.DictReader(io.StringIO(SPLIT.read_text())))


def test_every_record_alex_has_seen_is_in_the_development_half():
    """The split's one load-bearing property. A record whose pages he has
    looked at can never supply a positive again (DEFECTS #56), so it is worth
    nothing held out and everything in development. Derived from the sheets,
    not remembered, so it cannot drift.
    """
    rows = _split_rows()
    half = {r["record_id"]: r["half"] for r in rows}
    seen = judged_records() & set(half)
    assert seen, "the derivation found no judged records, which cannot be right"
    wrong = sorted(r for r in seen if half[r] != "development")
    assert wrong == [], f"held out but already seen: {wrong}"


def test_the_split_covers_every_record_exactly_once():
    rows = _split_rows()
    ids = [r["record_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert set(r["half"] for r in rows) <= {"development", "held_out",
                                            "sitting_frame"}


def test_the_district_02_records_are_reserved_for_the_sitting():
    """Added 2026-09-07 with the district 02 fetch. Those records are neither
    development nor held-out negatives: they are the frame for the blind
    sitting the fetch exists to make possible, and tuning on one would spend
    the thing that was just bought.

    The file is extended, never rewritten, so a record's half stays whatever
    it was decided to be before anybody looked at it.
    """
    rows = _split_rows()
    frame = [r for r in rows if r["half"] == "sitting_frame"]
    assert frame, "no sitting frame recorded"
    assert all("fetched after the split" in r["reason"] for r in frame)

    original = [r for r in rows if r["half"] in ("development", "held_out")]
    assert len(original) == 202, (
        "the district 03 halves must not have moved; extending is allowed "
        "and rewriting is not")
