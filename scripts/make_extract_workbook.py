#!/usr/bin/env python3
"""Build the extraction ground-truth workbook from the CSV template.

The CSV at tests/fixtures/extract_truth.csv stays the source of truth and the
thing that gets committed. This is a working aid: same rows, same column order,
plus a validated dropdown on `status` so a value cannot be mistyped in the
first place rather than being caught afterwards.

The dropdown is generated from pipeline.extract.Status, not typed out here. A
second copy of a vocabulary drifts; tests/tier2/test_label_workbook.py exists
because that already happened once with the page classes.

Writes to data/labelset/, which is git-ignored. Export back over the committed
CSV path when done.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook                              # noqa: E402
from openpyxl.formatting.rule import FormulaRule           # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill   # noqa: E402
from openpyxl.utils import get_column_letter               # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from pipeline.extract import Status                        # noqa: E402

CSV_PATH = ROOT / "tests" / "fixtures" / "extract_truth.csv"
OUT = ROOT / "data" / "labelset" / "extract_truth.xlsx"

HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
LOCKED_FILL = PatternFill("solid", fgColor="F4F4F4")
BAND_FILL = PatternFill("solid", fgColor="EFF4FA")
ERROR_FILL = PatternFill("solid", fgColor="FFC7CE")
DONE_FILL = PatternFill("solid", fgColor="E2EFDA")

PREFILLED = ("seq", "record_id", "pages", "field")

MEANING = {
    Status.PRESENT: "something is written in this field and you can read it",
    Status.BLANK: "the field exists on this form and nobody filled it in",
    Status.ILLEGIBLE: "something is written and you cannot make it out",
    Status.NOT_ON_THIS_FORM:
        "this form revision has no such field at all. Not the same as blank",
    Status.PAGE_NOT_IN_DOCUMENT:
        "the form has this field, on a page this document does not include. "
        "A W-2 face with no reverse imaged: the completion data is not absent "
        "from the form, it is on paper nobody scanned",
}


def main() -> None:
    if not CSV_PATH.exists():
        sys.exit(f"missing {CSV_PATH}; run `make smoke` first")
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    columns = list(rows[0].keys()) + ["check"]

    book = Workbook()
    sheet = book.active
    sheet.title = "truth"

    vocab = book.create_sheet("vocabulary")
    vocab["A1"], vocab["B1"] = "status", "meaning"
    vocab["A1"].font = vocab["B1"].font = Font(bold=True)
    for i, status in enumerate(Status, start=2):
        vocab.cell(i, 1, status.value)
        vocab.cell(i, 2, MEANING[status])
    vocab.column_dimensions["A"].width = 20
    vocab.column_dimensions["B"].width = 70
    n_status = len(Status) + 1

    for c, name in enumerate(columns, start=1):
        cell = sheet.cell(1, c, name)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL

    # Everything is text: a record id like 1493495 is fine, but a value like
    # 9-22-77 or 2-3/8 must never be reinterpreted as a date or a fraction.
    # That is the whole reason for handing over a workbook rather than the CSV.
    for r, row in enumerate(rows, start=2):
        banded = int(row["seq"]) % 2 == 0
        for c, name in enumerate(columns, start=1):
            if name == "check":
                continue
            cell = sheet.cell(r, c, row.get(name, ""))
            cell.alignment = Alignment(horizontal="left")
            cell.number_format = "@"
            if name in PREFILLED:
                cell.fill = BAND_FILL if banded else LOCKED_FILL

    col = {name: get_column_letter(i) for i, name in enumerate(columns, start=1)}
    last = len(rows) + 1

    validation = DataValidation(
        type="list", formula1=f"=vocabulary!$A$2:$A${n_status}",
        allow_blank=True, showDropDown=False, errorStyle="stop")
    validation.error = ("Not a status. Pick from the list; the vocabulary "
                        "sheet says what each one means.")
    validation.errorTitle = "Unknown status"
    sheet.add_data_validation(validation)
    validation.add(f"{col['status']}2:{col['status']}{last}")

    for r in range(2, last + 1):
        formula = (
            f'=IF({col["status"]}{r}="","",'
            f'IF({col["status"]}{r}="present",'
            f'  IF({col["value"]}{r}="","present needs a value","ok"),'
            f'  IF({col["value"]}{r}<>"","only a present row carries a value",'
            f'     "ok")))')
        sheet.cell(r, len(columns), formula)

    check = f"{col['check']}2:{col['check']}{last}"
    sheet.conditional_formatting.add(check, FormulaRule(
        formula=[f'AND({col["check"]}2<>"",{col["check"]}2<>"ok")'],
        fill=ERROR_FILL))
    sheet.conditional_formatting.add(check, FormulaRule(
        formula=[f'{col["check"]}2="ok"'], fill=DONE_FILL))

    sheet.freeze_panes = "E2"
    for name, width in {"seq": 6, "record_id": 11, "pages": 9, "field": 30,
                        "value": 34, "status": 20, "note": 34,
                        "check": 30}.items():
        if name in col:
            sheet.column_dimensions[col[name]].width = width

    OUT.parent.mkdir(parents=True, exist_ok=True)
    book.save(OUT)

    print(f"{OUT}  ({OUT.stat().st_size:,} bytes, {len(rows)} rows)")
    print(f"  dropdown on status ({len(Status)} values), meanings on the "
          "vocabulary sheet")
    print("  documents are banded so one document reads as one block")
    print("  check column flags a present row with no value, and the reverse")
    print(f"\nWhen finished, export as CSV over:\n  {CSV_PATH}")


if __name__ == "__main__":
    main()
