#!/usr/bin/env python3
"""Build a labelling workbook with dropdowns from the CSV template.

The CSV at tests/fixtures/labels_stage1.csv stays the source of truth and the
thing that gets committed. This is a working aid: same rows, same column
order, plus validated dropdowns so a class name cannot be mistyped in the
first place rather than being caught by the tier-2 validator afterwards.

It also solves a hazard the CSV has on its own. Spreadsheet apps read
`1493418-0-12` as a formula or a date; here every identifier is written as an
explicit string, so opening this file cannot corrupt a page id.

Writes to data/labelset/, which is git-ignored. Convert back to CSV over the
committed path when done:

    tests/fixtures/labels_stage1.csv

The trailing `check` column is a live formula, not data. It is ignored by
everything downstream, so leaving it in the exported CSV is harmless.
"""

from __future__ import annotations

import argparse
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

from pipeline import pageclass as pc                       # noqa: E402

#: Stage 1 is the uniform 60-page set, stage 2 the stratified 143-page one.
#: One builder rather than two: the dropdowns are a second copy of the
#: vocabulary, and the point of tests/tier2/test_label_workbook.py is that a
#: second copy drifts. A third would drift twice.
STAGES = {
    1: (ROOT / "tests" / "fixtures" / "labels_stage1.csv",
        ROOT / "data" / "labelset" / "labels_stage1.xlsx"),
    2: (ROOT / "tests" / "fixtures" / "labels_stage2.csv",
        ROOT / "data" / "labelset" / "labels_stage2.xlsx"),
}

HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
LOCKED_FILL = PatternFill("solid", fgColor="F4F4F4")
ERROR_FILL = PatternFill("solid", fgColor="FFC7CE")
DONE_FILL = PatternFill("solid", fgColor="E2EFDA")

PREFILLED = ("seq", "page_id", "record_id", "file_index", "page",
             "native_w", "native_h", "oversize")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=int, choices=sorted(STAGES), default=1)
    stage = parser.parse_args().stage
    CSV, OUT = STAGES[stage]

    if not CSV.exists():
        sys.exit(f"missing {CSV}; run `make label` first"
                 if stage == 1 else f"missing {CSV}; run `make label2` first")
    rows = list(csv.DictReader(CSV.open(encoding='utf-8-sig')))
    columns = list(rows[0].keys()) + ["check"]

    book = Workbook()
    sheet = book.active
    sheet.title = "labels"

    # --- vocabulary sheet: the dropdown sources, plus what each class means
    vocab = book.create_sheet("vocabulary")
    vocab["A1"], vocab["B1"] = "form_class", "meaning"
    vocab["A1"].font = vocab["B1"].font = Font(bold=True)
    # COMPLETION_FACES, not EXTRACTION_TARGETS. The two abstention classes are
    # completion faces without being named forms, so grouping by the narrower
    # set drops them from the workbook entirely and they become unselectable.
    ordered = ([c for c in pc.PageClass if c in pc.COMPLETION_FACES]
               + [c for c in pc.PageClass if c in pc.IDENTITY_BEARING]
               + [c for c in pc.PageClass if c in pc.CENSUS_ONLY])
    for i, cls in enumerate(ordered, start=2):
        vocab.cell(i, 1, cls.value)
        vocab.cell(i, 2, pc.GLOSS[cls])
    vocab.cell(1, 4, "part").font = Font(bold=True)
    for i, part in enumerate(pc.Part, start=2):
        vocab.cell(i, 4, part.value)
    vocab.cell(1, 5, "orientation").font = Font(bold=True)
    for i, orient in enumerate(pc.Orientation, start=2):
        vocab.cell(i, 5, orient.value)
    # Classes that must NOT carry a part. Not the same as census-only:
    # other_form is census-only but may carry one, because a page can plainly
    # be a form back while its form number is unreadable.
    vocab.cell(1, 6, "form_number_legible").font = Font(bold=True)
    vocab.cell(2, 6, "y")
    vocab.cell(3, 6, "n")
    vocab.cell(1, 7, "part_forbidden").font = Font(bold=True)
    census = [c for c in pc.PageClass if c in pc.PART_FORBIDDEN]
    for i, cls in enumerate(census, start=2):
        vocab.cell(i, 7, cls.value)
    vocab.column_dimensions["A"].width = 20
    vocab.column_dimensions["B"].width = 58
    for col in "DEFG":
        vocab.column_dimensions[col].width = 20

    n_class, n_part = len(ordered) + 1, len(pc.Part) + 1
    n_orient, n_census = len(pc.Orientation) + 1, len(census) + 1

    # --- header
    for c, name in enumerate(columns, start=1):
        cell = sheet.cell(1, c, name)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL

    # --- data. Everything is written as text: an identifier like 1493418-0-12
    # must never be reinterpreted as a date.
    for r, row in enumerate(rows, start=2):
        for c, name in enumerate(columns, start=1):
            if name == "check":
                continue
            cell = sheet.cell(r, c, row.get(name, ""))
            cell.alignment = Alignment(horizontal="left")
            cell.number_format = "@"
            if name in PREFILLED:
                cell.fill = LOCKED_FILL

    col = {name: get_column_letter(i) for i, name in enumerate(columns, start=1)}
    last = len(rows) + 1

    # --- dropdowns
    # allow_blank throughout: the dropdown's job is to stop a typo, not to
    # enforce completeness. Refusing to let a cell be cleared just makes
    # correcting a row a fight. Missing values are caught by the check column
    # and by tests/tier2/test_labelset.py.
    for name, source in (
        ("form_class", f"vocabulary!$A$2:$A${n_class}"),
        ("part", f"vocabulary!$D$2:$D${n_part}"),
        ("orientation", f"vocabulary!$E$2:$E${n_orient}"),
        ("form_number_legible", "vocabulary!$F$2:$F$3"),
    ):
        if name not in col:
            continue          # stage 1 has no legibility column
        validation = DataValidation(
            type="list", formula1=f"={source}", allow_blank=True,
            showDropDown=False, errorStyle="stop")
        validation.error = (f"Not a valid {name}. Pick from the list; the "
                            "vocabulary sheet says what each one means.")
        validation.errorTitle = f"Unknown {name}"
        sheet.add_data_validation(validation)
        validation.add(f"{col[name]}2:{col[name]}{last}")

    # --- live check column, so a mistake shows now rather than at `make test`
    for r in range(2, last + 1):
        # The last thing checked, so that "ok" means every column is filled.
        done = '"ok"'
        if "form_number_legible" in col:
            done = (f'IF({col["form_number_legible"]}{r}="",'
                    f'"form_number_legible missing","ok")')
        formula = (
            f'=IF({col["form_class"]}{r}="","",'
            f'IF(COUNTIF(vocabulary!$G$2:$G${n_census},{col["form_class"]}{r})>0,'
            f'  IF({col["part"]}{r}="",{done},"part must be blank for this class"),'
            f'  IF(AND({col["part"]}{r}="",{col["form_class"]}{r}<>"other_form"),'
            f'    "part is required for a named form",'
            f'    IF({col["orientation"]}{r}="","orientation missing",{done}))))')
        sheet.cell(r, len(columns), formula)

    check = f"{col['check']}2:{col['check']}{last}"
    sheet.conditional_formatting.add(check, FormulaRule(
        formula=[f'AND({col["check"]}2<>"",{col["check"]}2<>"ok")'],
        fill=ERROR_FILL))
    sheet.conditional_formatting.add(check, FormulaRule(
        formula=[f'{col["check"]}2="ok"'], fill=DONE_FILL))

    # --- layout
    sheet.freeze_panes = "A2"
    widths = {"seq": 6, "page_id": 16, "record_id": 11, "file_index": 10,
              "page": 7, "native_w": 10, "native_h": 10, "oversize": 10,
              "form_class": 20, "part": 20, "orientation": 14,
              "form_number_legible": 20, "note": 34, "check": 32}
    for name, width in widths.items():
        if name in col:
            sheet.column_dimensions[col[name]].width = width

    OUT.parent.mkdir(parents=True, exist_ok=True)
    book.save(OUT)

    print(f"{OUT}  ({OUT.stat().st_size:,} bytes, {len(rows)} rows)")
    print(f"  dropdowns on form_class ({len(ordered)} values), "
          f"part ({len(pc.Part)}), orientation ({len(pc.Orientation)})")
    print("  vocabulary sheet carries the meaning of every class")
    print("  check column flags a missing or misplaced part as you type")
    print(f"\nWhen finished, export as CSV over:\n  {CSV}")


if __name__ == "__main__":
    main()
