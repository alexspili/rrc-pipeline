"""Tier 1: the geometry-confabulation detector.

Origin: DEFECTS #29. The extraction model returns bounding boxes that parse
cleanly and point at the wrong place. Its fingerprint, measured on document 1
of the ground truth, is a table row whose cell boxes abut perfectly, edge to
edge, and share one identical y band: a schematic of a form, not a reading of
a page. Real reads carry gaps and jitter.

The detector is a permanent validation output rather than a one-off, because
a regression back into schematic geometry would otherwise be silent.
"""

from __future__ import annotations

from pipeline.extract import CompletionReport, Region, Row, Status, Value
from pipeline.validate import Severity, check_geometry


def cell(left, top, right, bottom, text="x", page=10):
    return Value(status=Status.PRESENT, value=text, raw=text,
                 region=Region(page=page, box=(left, top, right, bottom)))


def doc(tables):
    return CompletionReport(
        record_id="1493495", file_index=0, pages=(9, 10), form_class="w2",
        form_revision=Value(status=Status.BLANK), tables=tables)


#: The real casing row from document 1, exactly as the model returned it:
#: eight cells, each box starting where the previous one ends, one y band.
SCHEMATIC = [(0.06, 0.49, 0.15, 0.52), (0.15, 0.49, 0.22, 0.52),
             (0.22, 0.49, 0.30, 0.52), (0.30, 0.49, 0.38, 0.52),
             (0.38, 0.49, 0.48, 0.52), (0.48, 0.49, 0.60, 0.52),
             (0.60, 0.49, 0.70, 0.52), (0.70, 0.49, 0.80, 0.52)]


def test_the_real_schematic_row_from_document_1_is_flagged():
    row = Row(cells={f"c{i}": cell(*b) for i, b in enumerate(SCHEMATIC)})
    findings = check_geometry(doc({"casing_strings": (row,)}))
    assert [f.rule for f in findings] == ["geometry.schematic_grid"]
    assert findings[0].severity is Severity.WARNING
    assert "casing_strings" in findings[0].message


def test_jittered_boxes_are_not_flagged():
    """What a genuine reading looks like: gaps between cells, y bands that do
    not agree to the third decimal place.
    """
    row = Row(cells={
        "a": cell(0.06, 0.492, 0.13, 0.523),
        "b": cell(0.16, 0.488, 0.21, 0.519),
        "c": cell(0.24, 0.495, 0.29, 0.526),
        "d": cell(0.33, 0.490, 0.37, 0.521),
    })
    assert check_geometry(doc({"casing_strings": (row,)})) == []


def test_two_abutting_cells_are_not_enough_to_call_it_schematic():
    """Two adjacent cells genuinely can share an edge on a printed table."""
    row = Row(cells={"a": cell(0.06, 0.49, 0.15, 0.52),
                     "b": cell(0.15, 0.49, 0.22, 0.52)})
    assert check_geometry(doc({"casing_strings": (row,)})) == []


def test_unboxed_cells_do_not_count_toward_the_signature():
    row = Row(cells={"a": cell(0.06, 0.49, 0.15, 0.52),
                     "b": cell(0.15, 0.49, 0.22, 0.52),
                     "c": Value(status=Status.BLANK)})
    assert check_geometry(doc({"tubing": (row,)})) == []


def test_each_schematic_row_is_one_finding():
    rows = tuple(
        Row(cells={f"c{i}": cell(b[0], b[1] + off, b[2], b[3] + off)
                   for i, b in enumerate(SCHEMATIC[:4])})
        for off in (0.0, 0.1))
    findings = check_geometry(doc({"casing_strings": rows}))
    assert len(findings) == 2


def test_a_document_without_tables_yields_nothing():
    assert check_geometry(doc({})) == []
