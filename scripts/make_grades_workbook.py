#!/usr/bin/env python3
"""Build the box-grading workbook from the CSV sheet.

Same reasoning as the other two workbooks: the CSV is the committed source of
truth, the workbook is the working aid, and the dropdowns are generated from
the same vocabulary the validator checks so a grade cannot be mistyped and a
second copy cannot drift.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook                              # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill   # noqa: E402
from openpyxl.utils import get_column_letter               # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

CSV_PATH = ROOT / "tests" / "fixtures" / "box_grades.csv"
OUT = ROOT / "data" / "labelset" / "extract_grades.xlsx"

#: Kept in one place with tests/tier2/test_box_grades.py's vocabulary.
GRADES = ["hit", "near", "miss"]
HANDWRITTEN = ["y", "n"]

HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
LOCKED_FILL = PatternFill("solid", fgColor="F4F4F4")
BAND_FILL = PatternFill("solid", fgColor="EFF4FA")

PREFILLED = ("record_id", "file_index", "pages", "page", "box_num", "field",
             "raw")


def main() -> None:
    if not CSV_PATH.exists():
        sys.exit(f"missing {CSV_PATH}; run scripts/overlay_boxes.py --sheet")
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    columns = list(rows[0].keys())

    book = Workbook()
    sheet = book.active
    sheet.title = "grades"

    vocab = book.create_sheet("vocabulary")
    vocab["A1"], vocab["B1"] = "grade", "meaning"
    vocab["A1"].font = vocab["B1"].font = Font(bold=True)
    meanings = {
        "hit": "the box overlaps the written value or its printed label",
        "near": "misses, but within about one field-row; the eye finds the "
                "value immediately from the box",
        "miss": "anywhere else",
    }
    for i, grade in enumerate(GRADES, start=2):
        vocab.cell(i, 1, grade)
        vocab.cell(i, 2, meanings[grade])
    vocab.cell(1, 4, "handwritten").font = Font(bold=True)
    for i, value in enumerate(HANDWRITTEN, start=2):
        vocab.cell(i, 4, value)
    vocab.column_dimensions["A"].width = 10
    vocab.column_dimensions["B"].width = 66

    for c, name in enumerate(columns, start=1):
        cell = sheet.cell(1, c, name)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL

    band = False
    previous = None
    for r, row in enumerate(rows, start=2):
        key = (row["record_id"], row["pages"])
        if key != previous:
            band, previous = not band, key
        for c, name in enumerate(columns, start=1):
            cell = sheet.cell(r, c, row.get(name, ""))
            cell.alignment = Alignment(horizontal="left")
            cell.number_format = "@"
            if name in PREFILLED:
                cell.fill = BAND_FILL if band else LOCKED_FILL

    col = {name: get_column_letter(i) for i, name in enumerate(columns, 1)}
    last = len(rows) + 1
    for name, source in (("grade", f"vocabulary!$A$2:$A${len(GRADES) + 1}"),
                         ("handwritten", "vocabulary!$D$2:$D$3")):
        validation = DataValidation(type="list", formula1=f"={source}",
                                    allow_blank=True, showDropDown=False,
                                    errorStyle="stop")
        validation.error = "Pick from the list."
        sheet.add_data_validation(validation)
        validation.add(f"{col[name]}2:{col[name]}{last}")

    sheet.freeze_panes = "A2"
    for name, width in {"record_id": 11, "file_index": 10, "pages": 8,
                        "page": 6, "box_num": 9, "field": 32, "raw": 30,
                        "grade": 10, "handwritten": 13, "note": 30}.items():
        if name in col:
            sheet.column_dimensions[col[name]].width = width

    OUT.parent.mkdir(parents=True, exist_ok=True)
    book.save(OUT)
    print(f"{OUT}  ({len(rows)} boxes)")
    print(f"\nWhen finished, export as CSV over:\n  {CSV_PATH}")


if __name__ == "__main__":
    main()
