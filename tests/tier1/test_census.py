"""Tier 1: census aggregation. Pure function from labels to counts.

The census is the deliverable that decides whether this corpus is usable:
below roughly 80 records carrying a completion report, fetch.py reopens. So
the arithmetic that produces that number gets pinned before it is trusted.
"""

from __future__ import annotations

from pipeline import pageclass as pc


def _label(record_id, file_index, page, form_class, part=None, **kw):
    return pc.PageLabel(
        record_id=record_id, file_index=file_index, page=page,
        form_class=form_class, part=part,
        orientation=kw.get("orientation", pc.Orientation.UP),
        confidence=kw.get("confidence", pc.Confidence.HIGH),
        alt_class=kw.get("alt_class"), oversize=kw.get("oversize", False))


def test_counts_pages_and_records():
    census = pc.aggregate([
        _label("1", 0, 1, pc.PageClass.G1, pc.Part.FACE),
        _label("1", 0, 2, pc.PageClass.PLAT_MAP),
        _label("2", 0, 1, pc.PageClass.LETTER_MEMO),
    ])
    assert census.total_pages == 3
    assert census.total_records == 2
    assert census.pages_by_class[pc.PageClass.G1] == 1


def test_a_records_g1_may_span_two_files():
    """HANDOFF: records reference sibling files, and 1501720's G-1 face and
    Section III are non-contiguous with a P-4 between. A completion report is
    not confined to one file, so the per-record rollup cannot be per-file.
    """
    census = pc.aggregate([
        _label("1760703", 0, 2, pc.PageClass.G1, pc.Part.FACE),
        _label("1760703", 1, 5, pc.PageClass.G1, pc.Part.SEC_III),
    ])
    assert census.records_with_completion_report == 1
    assert census.pages_by_class[pc.PageClass.G1] == 2


def test_a_record_holding_both_a_g1_and_a_w2_counts_once():
    """records_with_completion_report is a union over records, not a sum over
    classes. Summing would report 2 records where 1 exists, and that number
    is the one deciding whether the corpus is sufficient.
    """
    census = pc.aggregate([
        _label("1", 0, 1, pc.PageClass.G1, pc.Part.FACE),
        _label("1", 0, 4, pc.PageClass.W2, pc.Part.FACE),
    ])
    assert census.total_records == 1
    assert census.records_with_completion_report == 1


def test_records_with_no_completion_report_are_counted():
    """profile_type POTENTIAL does not mean the file holds a completion
    report; four of four sampled old-operator files had none. The count of
    records without one is the census's headline, not an error case.
    """
    census = pc.aggregate([
        _label("1493418", 0, 1, pc.PageClass.WS1_SW1, pc.Part.FACE),
        _label("1494070", 0, 1, pc.PageClass.SEPARATOR_CARD),
    ])
    assert census.records_with_completion_report == 0
    assert census.total_records == 2


def test_amended_filings_are_documents_not_entities():
    """Origin: DEFECTS #2. One record held the same P-17 permit twice, as an
    original and an amendment. Document-level and entity-level counts are
    different numbers, so the census reports pages and records and declines to
    report a permit count it cannot derive.
    """
    census = pc.aggregate([
        _label("1", 0, 1, pc.PageClass.P17, pc.Part.FACE),
        _label("1", 0, 2, pc.PageClass.P17, pc.Part.FACE),
    ])
    assert census.pages_by_class[pc.PageClass.P17] == 2
    assert census.records_by_class[pc.PageClass.P17] == 1
    assert not hasattr(census, "permits")


def test_oversize_and_eligibility_are_tracked():
    census = pc.aggregate([
        _label("1", 0, 1, pc.PageClass.G1, pc.Part.FACE),
        _label("1", 0, 2, pc.PageClass.G1, pc.Part.FACE, oversize=True),
        _label("1", 0, 3, pc.PageClass.G1, pc.Part.BACK_INSTRUCTIONS),
    ])
    assert census.oversize_pages == 1
    assert census.extraction_eligible_pages == 1


def test_empty_input_is_an_empty_census_not_a_crash():
    census = pc.aggregate([])
    assert census.total_pages == 0
    assert census.total_records == 0
    assert census.records_with_completion_report == 0
