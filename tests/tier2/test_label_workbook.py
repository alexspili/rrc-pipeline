"""Tier 2: the labelling workbook stays in step with the CSV and the enums.

The workbook is a convenience, but it is the thing a label is actually typed
into, and its dropdowns are a second copy of the vocabulary. A second copy
drifts. If the enums gain a class and the workbook does not, that class simply
cannot be selected and will be labelled as something else, silently and by a
human who trusted the dropdown.

The workbook itself lives under data/ and is not committed; this builds a
fresh one into a temp directory and inspects it.
"""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline import pageclass as pc

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "tests" / "fixtures" / "labels_stage1.csv"
SCRIPT = ROOT / "scripts" / "make_label_workbook.py"

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture(scope="module")
def workbook():
    if not CSV.exists():
        pytest.skip("label template absent; run `make label`")
    subprocess.run([sys.executable, str(SCRIPT)], check=True,
                   capture_output=True, cwd=ROOT)
    out = ROOT / "data" / "labelset" / "labels_stage1.xlsx"
    if not out.exists():
        pytest.skip("workbook not produced")
    return openpyxl.load_workbook(out)


def test_columns_match_the_csv_so_an_export_drops_straight_in(workbook):
    """The CSV is the source of truth. An export from this workbook has to
    land on it without a column shuffle.
    """
    sheet = workbook["labels"]
    header = [cell.value for cell in sheet[1]]
    expected = next(csv.reader(CSV.open()))
    assert header[:-1] == expected
    assert header[-1] == "check", "the only extra column may be the formula one"


def test_every_row_of_the_sample_is_present(workbook):
    sheet = workbook["labels"]
    assert sheet.max_row - 1 == len(list(csv.DictReader(CSV.open()))) == 60


def test_dropdowns_offer_exactly_the_vocabulary(workbook):
    """The list a labeller can choose from and the list the parser accepts are
    the same list, or ground truth contains values the pipeline rejects.
    """
    vocab = workbook["vocabulary"]

    def column(letter, expected_n):
        return {vocab[f"{letter}{i}"].value
                for i in range(2, expected_n + 2)} - {None}

    assert column("A", len(pc.PageClass)) == {c.value for c in pc.PageClass}
    assert column("D", len(pc.Part)) == {p.value for p in pc.Part}
    assert column("E", len(pc.Orientation)) == {o.value for o in pc.Orientation}
    assert column("G", len(pc.CENSUS_ONLY)) == {c.value for c in pc.CENSUS_ONLY}


def test_every_class_carries_its_gloss(workbook):
    """A bare token like `l1` in a dropdown is useless without the form's name
    beside it.
    """
    vocab = workbook["vocabulary"]
    seen = {vocab[f"A{i}"].value: vocab[f"B{i}"].value
            for i in range(2, len(pc.PageClass) + 2)}
    for cls in pc.PageClass:
        assert seen.get(cls.value), f"no gloss for {cls.value}"


def test_the_three_label_columns_are_validated(workbook):
    sheet = workbook["labels"]
    header = [cell.value for cell in sheet[1]]
    validated = set()
    for validation in sheet.data_validations.dataValidation:
        for rng in str(validation.sqref).split():
            validated.add(rng[0])
    for name in ("form_class", "part", "orientation"):
        letter = openpyxl.utils.get_column_letter(header.index(name) + 1)
        assert letter in validated, f"{name} has no dropdown"


def test_identifiers_are_text_so_a_spreadsheet_cannot_reinterpret_them(workbook):
    """`1493418-0-12` reads as a formula or a date in a spreadsheet app. The
    whole point of handing over a workbook rather than the raw CSV is that this
    cannot happen.
    """
    sheet = workbook["labels"]
    for row in range(2, 8):
        cell = sheet.cell(row, 2)
        assert isinstance(cell.value, str)
        assert cell.number_format == "@"
        assert cell.value.count("-") == 2
