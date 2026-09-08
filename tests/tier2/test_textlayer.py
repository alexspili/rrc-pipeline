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

from pipeline.textlayer import line_run, page_words

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.jsonl"

# Every test here reads real corpus pages; a clean clone has none, and
# greeted its first reader with 24 tracebacks instead of skips (DEFECTS #75).
pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(),
    reason="needs the fetched corpus; data/ is never committed")

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


# ---------------------------------------------- the display band, on paper

def _snapped(page: int):
    """The graded text-layer boxes on one page of record 1493608."""
    import csv
    key = ROOT / "tests" / "fixtures" / "box_grades_probe_key.csv"
    if not key.exists():
        pytest.skip("answer key not present")
    rows = [r for r in csv.DictReader(key.open(encoding="utf-8-sig"))
            if r["source"] == "text_layer" and int(r["page"]) == page]
    return {r["field"]: tuple(float(v) for v in r["box"].split())
            for r in rows}


def _band_text(pdf, page, box):
    words = page_words(pdf, page)
    band = line_run(words, box)
    inside = [w[4] for w in words
              if band[0] <= (w[0] + w[2]) / 2 <= band[2]
              and band[1] <= (w[1] + w[3]) / 2 <= band[3]]
    return band, " ".join(inside)


def test_the_display_band_contains_its_snapped_word_on_every_graded_box():
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    for page in (5, 6):
        for field, box in _snapped(page).items():
            band, _ = _band_text(pdf, page, box)
            assert band[0] <= box[0] and band[2] >= box[2], field
            assert band[1] <= box[1] and band[3] >= box[3], field


def test_the_four_recoverable_partial_captures_are_now_whole():
    """The grader wrote "only part of it is captured" five times. Four of the
    five are recoverable from this text layer."""
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    page5, page6 = _snapped(5), _snapped(6)
    _, operator = _band_text(pdf, 5, page5["identity.operator_name"])
    assert "COMPANY" in operator                      # was SKELLY alone
    _, address = _band_text(pdf, 5, page5["identity.operator_address"])
    assert "Houston" in address                       # was 1938 alone
    _, survey = _band_text(pdf, 5, page5["identity.location_survey"])
    assert "Blk" in survey                            # was Maria alone
    _, contractor = _band_text(pdf, 6,
                               page6["completion.drilling_contractor"])
    assert "INC" in contractor                        # was SERVICE alone


def test_a_value_printed_on_two_lines_gets_one_lines_worth_of_band():
    """Standing rule 9: the residue is pinned, not omitted.

    `logs_run` reads "Cement Bond Log & Neutron" and then "Lifetime Log" on
    the line below. The band recovers the first line and stops.

    The reason matters and I got it wrong once before this test caught it. It
    is not that "Lifetime" is missing from the text layer; it is there, at
    cy 0.3308 against "Neutron" at cy 0.3154. That is 1.9 median word heights
    apart, comfortably outside the same-line window, so the band is doing
    exactly what it is specified to do.

    This is a boundary of the single-line rule rather than a gap in the data,
    and the two are worth telling apart: a data gap is unfixable from this
    layer, while a multi-line value is a rule that could be extended and
    deliberately was not. Extending it is out of scope permanently, and the
    cost of not extending it is recorded here.
    """
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    words = page_words(pdf, 5)
    band, logs = _band_text(pdf, 5, _snapped(5)["identity.logs_run"])
    assert "Neutron" in logs
    assert "Lifetime" not in logs

    lifetime = next(w for w in words if "ifetime" in w[4])
    neutron = next(w for w in words if "Neutron" in w[4])
    apart = abs((lifetime[1] + lifetime[3]) / 2
                - (neutron[1] + neutron[3]) / 2)
    assert apart > tl_line_tolerance(words), (
        "the second line is now within the same-line window, so this is no "
        "longer a two-line value and the entry needs revisiting")


def tl_line_tolerance(words):
    from pipeline.textlayer import LINE_TOL, line_height
    return LINE_TOL * line_height(words)


def test_the_wrong_field_snap_now_shows_a_reader_that_it_is_wrong():
    """DEFECTS #32. The band cannot fix the match, and is not meant to. It
    puts enough of the page around it that the caption disagrees visibly."""
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    _, text = _band_text(pdf, 5, _snapped(5)["identity.field_name"])
    assert "8400" in text and "Frio" in text
    assert "Bay City" not in text


def test_the_band_never_sweeps_the_page_width():
    """A band that runs into the next field is worse than the word it
    replaced, because it looks like it knows something. Measured maximum on
    this document is the survey field at 0.627, which is genuinely that wide.
    """
    pdf = _pdf("1493608", 0)
    if not pdf.exists():
        pytest.skip(f"{pdf} is git-ignored corpus, not present here")
    for page in (5, 6):
        for field, box in _snapped(page).items():
            band, _ = _band_text(pdf, page, box)
            assert band[2] - band[0] < 0.70, field
