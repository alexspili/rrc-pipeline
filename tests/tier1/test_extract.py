"""Tier 1: an extracted value knows where it came from, or admits it cannot.

Pure. The schema was probed against a real document before it was coded, so
several cases here are the probe's own output rather than invented shapes.
"""

from __future__ import annotations

import pytest

from pipeline import extract as ex
from pipeline.extract import (Correction, Region, Row, Status, Value,
                              parse_report, parse_value)


def region(page=1, box=(0.1, 0.2, 0.3, 0.25)):
    return Region(page=page, box=box)


def present(text="Sun Oil Company", **kw):
    kw.setdefault("region", region())
    return Value(status=Status.PRESENT, value=text, raw=text, **kw)


# ------------------------------------------------- a box locates something

def test_a_present_value_must_say_where_it_was_read():
    with pytest.raises(ValueError, match="must say where it was read from"):
        Value(status=Status.PRESENT, value="9200'", raw="9200'")


ABSENT = [s for s in Status if s is not Status.PRESENT]


@pytest.mark.parametrize("status", ABSENT)
def test_an_absent_value_carries_no_box(status):
    """Approved before coding: box is null, never [0, 0, 0, 0]. The probe
    returned the degenerate box on a field the form does not have, which reads
    as the page's top-left corner and would draw a highlight there.
    """
    assert Value(status=status).region is None
    with pytest.raises(ValueError, match="nothing to point at"):
        Value(status=status, region=region())


@pytest.mark.parametrize("status", ABSENT)
def test_an_absent_value_carries_no_text(status):
    with pytest.raises(ValueError, match="carries no text"):
        Value(status=status, value="9200'")


def test_the_degenerate_box_the_probe_returned_is_read_as_absent():
    """Real output from scripts/probe_sonnet.py, on the api_number field of a
    1975 Form W-2, which has no API number field at all.
    """
    value = parse_value({"value": None, "raw": None,
                         "status": "not_on_this_form", "page": 1,
                         "box": [0, 0, 0, 0], "correction": None})
    assert value.status is Status.NOT_ON_THIS_FORM
    assert value.region is None


def test_a_box_must_be_fractions_with_area():
    with pytest.raises(ValueError, match="fractions of the page"):
        Region(page=1, box=(0.1, 0.2, 1.4, 0.3))
    with pytest.raises(ValueError, match="positive area"):
        Region(page=1, box=(0.4, 0.2, 0.4, 0.3))
    with pytest.raises(ValueError, match="four numbers"):
        Region(page=1, box=(0.1, 0.2, 0.3))


def test_pages_are_one_based():
    with pytest.raises(ValueError, match="1-based"):
        Region(page=0, box=(0.1, 0.2, 0.3, 0.4))


# ------------------------------------- the four statuses are four facts

def test_the_status_vocabulary_is_closed():
    with pytest.raises(ValueError, match="is not one of"):
        parse_value({"status": "missing"})
    with pytest.raises(ValueError, match="has no status"):
        parse_value({"value": "9200'"})


def test_not_on_this_form_is_not_blank():
    """The distinction the enum exists for. A 1975 Form W-2 has no API number
    field; a 1983 Form G-1 does. An empty one on the G-1 is blank. Scoring
    that mixes them measures nothing.
    """
    assert Status.NOT_ON_THIS_FORM is not Status.BLANK
    absent = parse_value({"status": "not_on_this_form"})
    empty = parse_value({"status": "blank"})
    assert absent.status is not empty.status


# ------------------------------------------------------------ corrections

def test_a_struck_through_value_keeps_both_readings():
    """Both completion faces read while designing this schema carry one."""
    value = parse_value({
        "value": "RED FISH REEF NORTH (F-8)",
        "raw": "RED FISH REEF NORTH (F-8)", "status": "present",
        "page": 1, "box": [0.05, 0.2, 0.4, 0.24],
        "correction": {"raw": "Wildcat", "box": [0.05, 0.2, 0.15, 0.23]}})
    assert value.corrected
    assert value.correction.raw == "Wildcat"
    assert value.correction.region.page == 1
    assert value.value == "RED FISH REEF NORTH (F-8)"


def test_a_correction_needs_a_value_that_was_read():
    with pytest.raises(ValueError, match="belongs to a value that was read"
                                         "|actually read"):
        Value(status=Status.BLANK, correction=Correction(raw="Wildcat"))


# ------------------------------------------------------- tables and rows

def test_a_table_cell_carries_provenance_like_any_other_value():
    row = Row(cells={"casing_size": present('9-5/8"'),
                     "depth_set": present("2020'")})
    assert row.get("depth_set").region is not None


def test_a_row_cannot_hold_a_bare_scalar():
    with pytest.raises(ValueError, match="is not a Value"):
        Row(cells={"depth_set": "2020'"})


# ---------------------------------------------------------- the document

def report(**kw):
    kw.setdefault("record_id", "1493495")
    kw.setdefault("file_index", 0)
    kw.setdefault("pages", (9, 10))
    kw.setdefault("form_class", "w2")
    kw.setdefault("form_revision", present("Rev. 6/30/75", region=region(9)))
    return ex.CompletionReport(**kw)


def test_v1_refuses_a_field_outside_its_schema():
    """The cut order says identity, dates, depths and casing, with the
    per-form test tables left to v2. A schema that quietly accepts an extra
    field is how v1 grows into v2 without anybody deciding to.
    """
    with pytest.raises(ValueError, match="not in the v1 schema"):
        report(identity={"gas_gravity": present(".5809", region=region(9))})
    with pytest.raises(ValueError, match="not in the v1 schema"):
        report(test={"absolute_open_flow": present("5948", region=region(9))})


def test_v1_takes_one_field_from_the_test_block():
    assert ex.TEST_FIELDS == ("date_of_test",)


def test_a_value_cannot_cite_a_page_the_document_does_not_have():
    """Reassembly pairs a face with its sections. A value pointing at a page
    outside the document means the pairing is wrong, and the viewer would
    highlight a page nobody is looking at.
    """
    with pytest.raises(ValueError, match="not one of this document's pages"):
        report(identity={"lease_name": present("State Tract 130",
                                               region=region(4))})


def test_a_document_needs_at_least_one_page():
    with pytest.raises(ValueError, match="at least one page"):
        report(pages=())


def test_values_walks_scalars_and_table_cells_alike():
    doc = report(
        identity={"lease_name": present("State Tract 130", region=region(9))},
        completion={"total_depth": present("9200'", region=region(10)),
                    "elevation": Value(status=Status.BLANK)},
        tables={"casing_strings": (Row(cells={
            "casing_size": present('16"', region=region(10))}),)})
    assert len(list(doc.values())) == 5      # 1 + 2 + revision + 1 cell
    assert doc.present == 4
    assert doc.located == 4


# --------------------------------------------------------------- parsing

FENCED = '''```json
{"document": {"form_class": "w2",
  "form_revision": {"value": "1975-06-30", "raw": "Rev. 6/30/75",
    "status": "present", "page": 1, "box": [0.83, 0.09, 0.97, 0.13]}},
 "identity": {
   "lease_name": {"value": "State Tract 130", "raw": "State Tract 130",
     "status": "present", "page": 1, "box": [0.4, 0.2, 0.7, 0.23]},
   "api_number": {"value": null, "raw": null, "status": "not_on_this_form",
     "page": 1, "box": [0, 0, 0, 0]}},
 "completion": {
   "total_depth": {"value": "9200'", "raw": "9200'", "status": "present",
     "page": 2, "box": [0.2, 0.3, 0.3, 0.33]},
   "casing_strings": [
     {"casing_size": {"value": "16\\"", "raw": "16\\"", "status": "present",
       "page": 2, "box": [0.05, 0.42, 0.15, 0.45]}}]},
 "test": {"date_of_test": {"value": "1977-11-14", "raw": "11-14-77",
   "status": "present", "page": 1, "box": [0.05, 0.41, 0.2, 0.44]}}}
```'''


def test_a_fenced_response_parses_through_the_one_json_reader():
    """The probe fenced its output. `pageclass._json_object` already tolerates
    that and refuses everything else; a second parser would be a second thing
    to keep correct.
    """
    doc = parse_report(FENCED, record_id="1493495", file_index=0, pages=(1, 2))
    assert doc.form_class == "w2"
    assert doc.identity["lease_name"].value == "State Tract 130"
    assert doc.identity["api_number"].status is Status.NOT_ON_THIS_FORM
    assert doc.identity["api_number"].region is None
    assert doc.completion["total_depth"].region.page == 2
    assert doc.tables["casing_strings"][0].get("casing_size").value == '16"'
    assert doc.test["date_of_test"].raw == "11-14-77"


def test_parsing_drops_a_field_the_v1_schema_does_not_have():
    body = ('{"document": {"form_class": "g1"}, '
            '"identity": {"gas_gravity": {"status": "blank"}}}')
    doc = parse_report(body, record_id="1", file_index=0, pages=(1,))
    assert "gas_gravity" not in doc.identity


def test_a_response_without_a_form_class_is_refused():
    with pytest.raises(ValueError, match="no document.form_class"):
        parse_report('{"identity": {}}', record_id="1", file_index=0,
                     pages=(1,))


# ------------------------------------------ standing rule 9, on this module

def test_a_one_row_table_may_arrive_as_a_bare_object():
    """The W-2 prints tubing as a single row, and modelling it as a lone
    object dropped all three of its values on the first real document parsed.
    Both shapes now parse to the same thing.
    """
    as_object = ('{"document": {"form_class": "w2"}, "completion": {"tubing": '
                 '{"size": {"value": "2-3/8", "raw": "2-3/8", '
                 '"status": "present", "page": 2, "box": [0.1, 0.6, 0.2, 0.63]}}}}')
    as_list = as_object.replace('"tubing": {', '"tubing": [{').replace(
        '}}}}', '}}]}}')
    for body in (as_object, as_list):
        doc = parse_report(body, record_id="1", file_index=0, pages=(1, 2))
        assert doc.tables["tubing"][0].get("size").value == "2-3/8"


def test_what_the_schema_has_no_home_for_is_counted_not_discarded():
    """Standing rule 9 in code. A drop nobody counts is a drop nobody can
    argue with, which is exactly how `tubing` went missing.
    """
    body = ('{"document": {"form_class": "g1"}, '
            '"identity": {"gas_gravity": {"status": "blank"}}, '
            '"completion": {"absolute_open_flow": {"status": "blank"}}}')
    doc = parse_report(body, record_id="1", file_index=0, pages=(1,))
    assert doc.dropped == ("completion.absolute_open_flow",
                           "identity.gas_gravity")


def test_nothing_is_dropped_when_the_response_fits_the_schema():
    doc = parse_report(FENCED, record_id="1493495", file_index=0, pages=(1, 2))
    assert doc.dropped == ()


# --------------------------- what the first smoke run found, as fixtures

def test_a_page_index_is_translated_to_a_page_of_the_file():
    """The model is shown "Page 1 of 2" and answers with that index; the
    document knows those pages are 9 and 10 of the file. Conflating them made
    every value in the first smoke run cite a page its document did not have.
    """
    body = ('{"document": {"form_class": "w2"}, "identity": {"lease_name": '
            '{"value": "State Tract 130", "raw": "State Tract 130", '
            '"status": "present", "page": 2, "box": [0.1, 0.2, 0.3, 0.25]}}}')
    doc = parse_report(body, record_id="1493495", file_index=0, pages=(9, 10))
    assert doc.identity["lease_name"].region.page == 10


def test_a_page_index_outside_the_document_yields_no_region():
    body = ('{"document": {"form_class": "w2"}, "identity": {"lease_name": '
            '{"value": "x", "raw": "x", "status": "present", "page": 7, '
            '"box": [0.1, 0.2, 0.3, 0.25]}}}')
    with pytest.raises(ValueError, match="must say where it was read from"):
        parse_report(body, record_id="1", file_index=0, pages=(9, 10))


def test_an_empty_table_arrives_as_a_value_object():
    """Real output from two smoke documents. The prompt says every value is an
    object and also that tables are arrays; a table with nothing in it
    satisfies the first rule. Read as no rows, not as one row whose cells are
    "status", "page" and "box".
    """
    body = ('{"document": {"form_class": "w2"}, "completion": '
            '{"liner_strings": {"value": [], "raw": "", "status": "blank", '
            '"page": 1, "box": null, "correction": null}}}')
    doc = parse_report(body, record_id="1", file_index=0, pages=(5,))
    assert "liner_strings" not in doc.tables


def test_a_one_row_table_is_still_a_row_not_a_value():
    body = ('{"document": {"form_class": "w2"}, "completion": {"tubing": '
            '{"size": {"value": "2-3/8", "raw": "2-3/8", "status": "present", '
            '"page": 1, "box": [0.1, 0.6, 0.2, 0.63]}}}}')
    doc = parse_report(body, record_id="1", file_index=0, pages=(5,))
    assert doc.tables["tubing"][0].get("size").value == "2-3/8"


def test_form_class_parses_whether_bare_or_wrapped():
    """It came back as a bare string on 4 of 10 smoke documents and as a value
    object on the other 6, because the prompt asked for both shapes in one
    block. The prompt is fixed; the parser stays tolerant.
    """
    for document in ('{"form_class": "w2"}',
                     '{"form_class": {"value": "w2", "raw": "Form W-2", '
                     '"status": "present", "page": 1, '
                     '"box": [0.8, 0.05, 0.95, 0.09]}}'):
        doc = parse_report('{"document": %s}' % document,
                           record_id="1", file_index=0, pages=(1,))
        assert doc.form_class == "w2"


def test_form_class_spelling_is_normalised():
    """The smoke run returned "g1" on two documents and "g-1" on two others.
    Left alone they are two different classes to every grouping and count
    downstream.
    """
    for spelling in ("g1", "g-1", "G-1", " g1 "):
        body = '{"document": {"form_class": "%s"}}' % spelling.strip()
        doc = parse_report(body, record_id="1", file_index=0, pages=(1,))
        assert doc.form_class == "g1", spelling


def test_a_form_class_outside_the_taxonomy_is_refused():
    """R4's principle at the extraction layer. The smoke run answered "w15" on
    a document the census called a W-2 face, and the stage-2 labels say the
    page really is a W-15 cementing report. That answer is worth surfacing, so
    it must parse; an answer that is not a class at all must not.
    """
    body = '{"document": {"form_class": "w15"}}'
    assert parse_report(body, record_id="1", file_index=0,
                        pages=(1,)).form_class == "w15"
    with pytest.raises(ValueError, match="not a page class"):
        parse_report('{"document": {"form_class": "completion report"}}',
                     record_id="1", file_index=0, pages=(1,))


# ------------------------------- a page that was never imaged is its own fact

def test_a_field_on_a_page_nobody_imaged_has_its_own_status():
    """Three facts, and until now two statuses. The form has no such field;
    the field is empty; the field is on a page this document does not include.

    9 of the 15 ground-truth documents are face-only, so this is 90 of 405
    rows. HANDOFF already records that only 107 of the 486 pages pointing to a
    reverse side are actually followed by one.
    """
    value = parse_value({"status": "page_not_in_document"})
    assert value.status is Status.PAGE_NOT_IN_DOCUMENT
    assert value.region is None and value.value is None


def test_the_missing_page_status_is_not_the_missing_field_status():
    """Marking a W-2's total depth not_on_this_form would assert the 1975 form
    has no total depth field, which is false and is exactly the conflation the
    enum exists to prevent.
    """
    assert Status.PAGE_NOT_IN_DOCUMENT is not Status.NOT_ON_THIS_FORM
    assert Status.PAGE_NOT_IN_DOCUMENT is not Status.BLANK
