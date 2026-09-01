"""Tier 1: a template writer never destroys a filled sheet.

Origin: DEFECTS #26. `scripts/smoke_extract.py` rewrites the ground-truth
template at the end of every run, and the run was repeated after the sheet had
been keyed by hand. It overwrote 405 labels with blanks. They came back from
the commit, which is the only reason this is an entry and not a disaster.
"""

from __future__ import annotations

import csv

import pytest

from pipeline.guard import RefusedToOverwrite, filled_rows, refuse_if_filled

COLUMNS = ["seq", "record_id", "pages", "field", "value", "status", "note"]


def sheet(tmp_path, statuses):
    path = tmp_path / "truth.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for i, status in enumerate(statuses, 1):
            writer.writerow({"seq": 1, "record_id": "1493495", "pages": "9 10",
                             "field": f"identity.f{i}", "value": "",
                             "status": status, "note": ""})
    return path


def test_a_filled_sheet_is_never_overwritten(tmp_path):
    path = sheet(tmp_path, ["present", "blank", ""])
    with pytest.raises(RefusedToOverwrite, match="2 of 3"):
        refuse_if_filled(path, "status")
    assert len(list(csv.DictReader(path.open()))) == 3


def test_one_filled_row_is_enough_to_refuse(tmp_path):
    """Not a threshold. A single keyed row is somebody's work."""
    with pytest.raises(RefusedToOverwrite):
        refuse_if_filled(sheet(tmp_path, ["", "", "illegible"]), "status")


def test_a_blank_sheet_may_be_rewritten(tmp_path):
    refuse_if_filled(sheet(tmp_path, ["", "", ""]), "status")


def test_a_sheet_that_does_not_exist_yet_may_be_written(tmp_path):
    refuse_if_filled(tmp_path / "nothing.csv", "status")


def test_the_count_is_reported_so_the_message_is_actionable(tmp_path):
    path = sheet(tmp_path, ["present", "present", ""])
    assert filled_rows(path, "status") == 2
    with pytest.raises(RefusedToOverwrite, match="2 of 3"):
        refuse_if_filled(path, "status")


def test_a_missing_column_is_an_error_not_a_free_pass(tmp_path):
    """A guard that silently passes when it cannot find the column it checks
    is worse than no guard: it reports safety it did not verify.
    """
    path = sheet(tmp_path, ["present"])
    with pytest.raises(ValueError, match="no column"):
        refuse_if_filled(path, "verdict")
