"""Tier 2 for pipeline.textlayer: the coordinate-space assumption, pinned.

`scripts/snap_coverage.py` has carried this as a docstring caveat since it
was written: word boxes are fractions of the PDF page box, model and template
boxes are fractions of the embedded scan image, and the two spaces align only
because the scan fills the page on this corpus. A page where it did not would
shear every distance in registration and in the snap tier's disambiguation,
silently, and every number downstream would be wrong by an amount nobody
could see.

Standing rule 9's shape: a comment states the residue, a test measures it.
The probe made this load-bearing, because registration multiplies the error
rather than merely offsetting it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.textlayer import page_words

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.jsonl"

#: The four graded documents plus the 1966 template fuel. If the assumption
#: holds anywhere it has to hold here, because these are the pages every
#: provenance number in docs/modules/extract.md was measured on.
PAGES = [("1493608", 0, 5), ("1493608", 0, 6), ("1494690", 0, 9),
         ("1494690", 0, 10), ("1494774", 0, 4), ("1495350", 0, 4),
         ("1495195", 0, 15), ("1912687", 0, 2), ("1495193", 0, 8)]


def _pdf(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["record_id"] == record_id:
            return RAW / record_id / entry["files"][file_index]["name"]
    raise LookupError(record_id)


@pytest.mark.parametrize("record_id,file_index,page", PAGES)
def test_the_scan_fills_the_page_box(record_id, file_index, page):
    """Word boxes must span most of the page in both axes.

    A scan pasted into a corner of a larger page box would put every word in
    a sub-rectangle, and this is what would show it.
    """
    pdf = _pdf(record_id, file_index)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    words = page_words(pdf, page)
    assert len(words) > 50, "too few words to judge the page box"
    assert min(w[0] for w in words) < 0.25
    assert max(w[2] for w in words) > 0.75
    assert min(w[1] for w in words) < 0.25
    assert max(w[3] for w in words) > 0.75


@pytest.mark.parametrize("record_id,file_index,page", PAGES)
def test_every_word_box_is_a_fraction_with_positive_area(
        record_id, file_index, page):
    pdf = _pdf(record_id, file_index)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    for x0, y0, x1, y1, text in page_words(pdf, page):
        assert 0.0 <= x0 <= 1.0 and 0.0 <= y0 <= 1.0
        assert 0.0 <= x1 <= 1.0 and 0.0 <= y1 <= 1.0
        assert x1 > x0 and y1 > y0


# --------------------------------------------------------------- DEFECTS #32

def test_the_ocr_drops_one_of_two_printed_instances_of_frio():
    """Pins a known limitation, not desired behaviour.

    Record 1493608 page 5 prints the word "Frio" twice: in field 1, the field
    name, as `Bay City (8000' Frio)` near y 0.17, and in field 12, the
    workover remark, as `8400' Frio now isolated` near y 0.30.

    The OCR reads only the second one. So a uniqueness test run against this
    text layer sees one match and asserts geometry on it, and the snap for
    `identity.field_name` lands two thirds of a page below its field. The
    safety rule that only unique matches may assert geometry is satisfied by
    a word that is not unique on the paper: the layer's omissions manufacture
    uniqueness.

    This is out of scope permanently, so the test exists to make the
    limitation visible and to fail loudly if the layer ever changes. Anyone
    who improves the OCR must change this test on purpose.
    """
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    frio = [w for w in page_words(pdf, 5) if "frio" in w[4].casefold()]
    assert len(frio) == 1, (
        "the text layer now carries a second 'Frio'; DEFECTS #32's premise "
        f"has changed and the entry needs revisiting: {frio}")
    centre_y = (frio[0][1] + frio[0][3]) / 2
    assert 0.28 < centre_y < 0.33, (
        f"the surviving 'Frio' is at y {centre_y:.3f}; #32 recorded it in "
        "field 12 near 0.30, not in field 1 near 0.17")
