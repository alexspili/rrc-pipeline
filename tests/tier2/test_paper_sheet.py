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
