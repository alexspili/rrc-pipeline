"""Tier 2: the extraction ground-truth sheet is well-formed.

Quiet while the sheet is blank, loud the moment a value is mistyped. A typo
here does not crash anything downstream; it scores a correct extraction as
wrong, which is the worst failure mode an eval set has.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline import extract as ex

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "extract_truth.csv"
SCRIPT = ROOT / "scripts" / "make_extract_workbook.py"

FIELDS = (["document.form_revision"]
          + [f"identity.{f}" for f in ex.IDENTITY_FIELDS]
          + [f"completion.{f}" for f in ex.COMPLETION_FIELDS]
          + [f"test.{f}" for f in ex.TEST_FIELDS])


def _rows():
    if not SHEET.exists():
        pytest.skip("ground-truth sheet not drawn yet")
    return list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))


def _filled():
    rows = _rows()
    if not any(r["status"].strip() for r in rows):
        pytest.skip("ground-truth sheet not filled in yet")
    return rows


# ------------------------------------------------------------------- shape

def test_the_sheet_is_fifteen_documents_of_the_whole_field_set():
    rows = _rows()
    documents = {(r["seq"], r["record_id"], r["pages"]) for r in rows}
    assert len(documents) == 15
    assert len(rows) == 15 * len(FIELDS) == 405


def test_every_field_name_is_one_the_schema_has():
    """The sheet and the schema are two lists of the same fields, and two
    lists drift. A row naming a field parse_report cannot produce would score
    a value nothing can supply.
    """
    unknown = sorted({r["field"] for r in _rows()} - set(FIELDS))
    assert not unknown, f"fields not in the extraction schema: {unknown}"


def test_every_document_carries_every_field_exactly_once():
    seen = {}
    for row in _rows():
        seen.setdefault(row["seq"], []).append(row["field"])
    for seq, fields in seen.items():
        assert sorted(fields) == sorted(FIELDS), f"document {seq}"


def test_the_sheet_does_not_leak_the_extraction_output():
    """Ground truth is keyed from page images. A prefilled value column, or a
    column carrying what the model said, would make the labels agreement
    rather than truth.
    """
    leaks = {"form_class", "predicted", "extracted", "model_value", "box"}
    assert not leaks & set(_rows()[0])


# ------------------------------------------------------------------ labels

def test_every_status_is_in_the_vocabulary():
    allowed = {s.value for s in ex.Status}
    bad = [(r["seq"], r["field"], r["status"]) for r in _filled()
           if r["status"].strip() not in allowed]
    assert not bad, f"statuses not in {sorted(allowed)}: {bad[:8]}"


def test_every_row_has_a_status():
    missing = [(r["seq"], r["field"]) for r in _filled()
               if not r["status"].strip()]
    assert not missing, f"rows with no status: {missing[:8]}"


def test_a_present_row_carries_a_value_and_no_other_row_does():
    """The same invariant the type enforces on the model's side. Ground truth
    that breaks it cannot be compared against output that cannot break it.
    """
    problems = []
    for row in _filled():
        status, value = row["status"].strip(), row["value"].strip()
        if status == ex.Status.PRESENT.value and not value:
            problems.append(f"{row['seq']}/{row['field']}: present, no value")
        if status and status != ex.Status.PRESENT.value and value:
            problems.append(f"{row['seq']}/{row['field']}: {status} with a value")
    assert not problems, "\n  ".join([""] + problems[:10])


def test_the_unsure_notes_stay_within_the_protocol_budget():
    """The protocol says stop at about twenty in 405. Past that the field list
    or the page images are the problem, not the keying.
    """
    unsure = [r for r in _filled() if "unsure" in r["note"].lower()]
    assert len(unsure) <= 40, (
        f"{len(unsure)} rows noted unsure. The protocol's budget is about 20; "
        "past 40 the sheet is measuring the instrument, not the extraction.")


# ---------------------------------------------------------------- workbook

def test_the_workbook_dropdown_is_the_status_enum():
    """A second copy of a vocabulary drifts. This one is generated from the
    enum; the test is what keeps it that way.
    """
    openpyxl = pytest.importorskip("openpyxl")
    import subprocess
    import sys as _sys
    if not SHEET.exists():
        pytest.skip("ground-truth sheet not drawn yet")
    subprocess.run([_sys.executable, str(SCRIPT)], check=True,
                   capture_output=True, cwd=ROOT)
    out = ROOT / "data" / "labelset" / "extract_truth.xlsx"
    if not out.exists():
        pytest.skip("workbook not produced")
    book = openpyxl.load_workbook(out)
    vocab = book["vocabulary"]
    offered = {vocab[f"A{i}"].value for i in range(2, len(ex.Status) + 2)}
    assert offered == {s.value for s in ex.Status}

    sheet = book["truth"]
    header = [c.value for c in sheet[1]]
    validated = {rng[0] for v in sheet.data_validations.dataValidation
                 for rng in str(v.sqref).split()}
    letter = openpyxl.utils.get_column_letter(header.index("status") + 1)
    assert letter in validated, "status has no dropdown"


def test_identifiers_are_text_so_a_spreadsheet_cannot_reinterpret_them():
    """A value like 9-22-77 or 2-3/8 reads as a date or a fraction in a
    spreadsheet app. Every cell is written as an explicit string.
    """
    openpyxl = pytest.importorskip("openpyxl")
    out = ROOT / "data" / "labelset" / "extract_truth.xlsx"
    if not out.exists():
        pytest.skip("workbook not built yet")
    sheet = openpyxl.load_workbook(out)["truth"]
    for row in range(2, 8):
        for column in range(1, 8):
            assert sheet.cell(row, column).number_format == "@"
