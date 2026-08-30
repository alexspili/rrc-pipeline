"""Tier 2: the hand-labelled stage-1 set is well-formed.

Skips every assertion while the file is still blank, so it is quiet until
there is something to check and loud the moment a value is mistyped. A label
typo does not crash anything downstream; it silently scores a correct
prediction as wrong, which is the worst failure mode an eval set has.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline import pageclass as pc

LABELS = Path(__file__).resolve().parents[1] / "fixtures" / "labels_stage1.csv"


def _rows():
    if not LABELS.exists():
        pytest.skip("stage-1 label set not generated yet: make label")
    rows = list(csv.DictReader(LABELS.open()))
    if not any(r["form_class"].strip() for r in rows):
        pytest.skip("stage-1 label set not filled in yet")
    return rows


def test_the_sample_is_the_agreed_size():
    rows = _rows()
    assert len(rows) == 60


def test_every_row_is_labelled():
    unlabelled = [r["page_id"] for r in _rows() if not r["form_class"].strip()]
    assert not unlabelled, f"unlabelled rows: {', '.join(unlabelled)}"


def test_every_value_is_in_the_vocabulary():
    """Same enums the classifier is scored against. A label the parser would
    reject cannot be ground truth for it.
    """
    problems = []
    for row in _rows():
        page_id = row["page_id"]
        try:
            form_class = pc.PageClass(row["form_class"].strip())
        except ValueError:
            problems.append(f"{page_id}: form_class={row['form_class']!r}")
            continue
        part = row["part"].strip() or None
        try:
            part = pc.Part(part) if part else None
        except ValueError:
            problems.append(f"{page_id}: part={row['part']!r}")
            continue
        try:
            orientation = pc.Orientation(row["orientation"].strip())
        except ValueError:
            problems.append(f"{page_id}: orientation={row['orientation']!r}")
            continue
        try:
            pc.PageLabel(
                record_id=row["record_id"], file_index=int(row["file_index"]),
                page=int(row["page"]), form_class=form_class, part=part,
                orientation=orientation, confidence=pc.Confidence.HIGH,
                oversize=row["oversize"] == "yes")
        except ValueError as exc:
            problems.append(f"{page_id}: {exc}")
    assert not problems, "\n  ".join([""] + problems)


def test_page_ids_match_their_coordinates():
    for row in _rows():
        assert pc.parse_page_id(row["page_id"]) == (
            row["record_id"], int(row["file_index"]), int(row["page"]))
