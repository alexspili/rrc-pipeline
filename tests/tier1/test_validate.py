"""Tier 1: deterministic checks over one extracted document.

Pure, and deliberately built from record 1501720 and from synthetic values
rather than from any document in the ground-truth set, so that no true value
for a blind eval document lands in the repository.

The severity split is the load-bearing part. An ERROR is impossible on any form
of any era. A WARNING is suspicious and its false-positive rate on this corpus
has not been measured, which is the DEFECTS #10 lesson: a rule written from the
handful of documents somebody read does not survive 1950s to 2008 paper.
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.extract import (CompletionReport, Region, Row, Status, Value)
from pipeline.validate import (ApiNumber, Finding, Severity, check_api_number,
                               check_dates, check_depths, parse_api,
                               parse_date, parse_depth, validate)

BRAZORIA = {"BRAZORIA": "039", "CHAMBERS": "071"}


def val(text, page=1):
    return Value(status=Status.PRESENT, value=text, raw=text,
                 region=Region(page=page, box=(0.1, 0.2, 0.3, 0.25)))


def doc(identity=None, completion=None, tables=None, test=None):
    return CompletionReport(
        record_id="1501720", file_index=0, pages=(1, 2), form_class="g1",
        form_revision=val("Rev. 4/1/83"),
        identity=identity or {}, completion=completion or {},
        tables=tables or {}, test=test or {})


# ------------------------------------------------------------------ parsing

def test_an_api_number_parses_however_it_is_punctuated():
    """Real spellings from the two forms in record 1501720."""
    assert parse_api("42- 039-31674") == ApiNumber("42", "039", "31674")
    assert parse_api("42-309-31674") == ApiNumber("42", "309", "31674")
    assert parse_api("42 039 31674") == ApiNumber("42", "039", "31674")
    assert parse_api("no number here") is None
    assert parse_api(None) is None


def test_depths_parse_through_the_marks_on_the_page():
    assert parse_depth("11000'") == 11000
    assert parse_depth("10,200") == 10200
    assert parse_depth("6954 (Cal)") == 6954
    assert parse_depth("Surface") is None
    assert parse_depth(None) is None


@pytest.mark.parametrize("text,expected", [
    ("1977-09-22", date(1977, 9, 22)),
    ("9/22/77", date(1977, 9, 22)),
    ("9-22-77", date(1977, 9, 22)),
    ("May 4, 1977", date(1977, 5, 4)),
    ("11/18/08", date(2008, 11, 18)),
    ("2/18/2008", date(2008, 2, 18)),
])
def test_dates_parse_in_the_spellings_the_forms_use(text, expected):
    assert parse_date(text) == expected


def test_the_century_pivot_is_stated_not_assumed():
    """This corpus is paper filed from the 1950s to 2008. On a corpus reaching
    further forward the pivot would be wrong, which is why it is a named
    constant and not a magic number.
    """
    assert parse_date("1/1/30").year == 2030
    assert parse_date("1/1/31").year == 1931
    assert parse_date("13/1/1977") is None
    assert parse_date("not a date") is None


# -------------------------------------------------------- the API cross-check

def test_the_transposed_county_digit_is_caught():
    """The demo defect, from record 1501720: the G-1 face reads 42-039-31674
    and the G-5 in the same file reads 42-309-31674. Brazoria is 039. The
    county the form names is what catches it, with no second form needed.
    """
    findings = check_api_number(
        doc(identity={"api_number": val("42-309-31674"),
                      "county": val("Brazoria")}), BRAZORIA)
    assert [f.rule for f in findings] == ["api.county_prefix"]
    assert findings[0].severity is Severity.ERROR
    assert "039" in findings[0].message


def test_the_matching_county_passes():
    assert check_api_number(
        doc(identity={"api_number": val("42- 039-31674"),
                      "county": val("Brazoria")}), BRAZORIA) == []


def test_an_unknown_county_is_not_an_error():
    """The map comes from the manifest and covers the counties it covers. A
    county missing from it is a gap in the map, not a defect in the document.
    """
    assert check_api_number(
        doc(identity={"api_number": val("42-039-31674"),
                      "county": val("Nowhere")}), BRAZORIA) == []


def test_a_non_texas_state_code_is_an_error():
    findings = check_api_number(
        doc(identity={"api_number": val("35-039-31674")}), BRAZORIA)
    assert [f.rule for f in findings] == ["api.state"]


def test_an_unparseable_api_number_is_an_error():
    findings = check_api_number(
        doc(identity={"api_number": val("see attached")}), BRAZORIA)
    assert [f.rule for f in findings] == ["api.structure"]


def test_a_form_without_an_api_number_is_not_a_finding():
    """A 1975 Form W-2 has no API number field at all. The absence is a fact
    about the form, which is exactly what the status enum records, and running
    a rule against it would manufacture a defect out of a form revision.
    """
    absent = Value(status=Status.NOT_ON_THIS_FORM)
    assert check_api_number(doc(identity={"api_number": absent}),
                            BRAZORIA) == []
    assert check_api_number(doc(), BRAZORIA) == []


# ------------------------------------------------------------------- dates

def test_a_permit_issued_after_drilling_started_is_an_error():
    findings = check_dates(doc(completion={
        "date_permit_issued": val("9/1/77"),
        "drilling_commenced": val("8-16-77")}))
    assert [f.rule for f in findings] == \
        ["date.date_permit_issued_before_drilling_commenced"]
    assert findings[0].severity is Severity.ERROR


def test_drilling_that_finishes_before_it_starts_is_an_error():
    findings = check_dates(doc(completion={
        "drilling_commenced": val("9-22-77"),
        "drilling_completed": val("8-16-77")}))
    assert [f.rule for f in findings] == \
        ["date.drilling_commenced_before_drilling_completed"]


def test_a_well_ordered_date_sequence_passes():
    """Synthetic, for the same reason as the depths below: the natural fixture
    is a document in the ground-truth set.
    """
    assert check_dates(doc(
        identity={"completion_date": val("6/30/81")},
        completion={"date_permit_issued": val("Feb 2, 1981"),
                    "drilling_commenced": val("4-11-81"),
                    "drilling_completed": val("6-30-81")},
        test={"date_of_test": val("8-05-81")})) == []


def test_a_test_dated_before_completion_is_a_warning_not_an_error():
    """Record 1501720 dates its test 2/18/2008 and its completion 11/18/08,
    nine months later and after the RRC's own received stamp. HANDOFF records
    that document as carrying real date errors, so this should fire. It is a
    warning because a retest or recompletion may legitimately reorder these
    and nobody has measured how often that happens on this corpus.
    """
    findings = check_dates(doc(
        identity={"completion_date": val("11/18/08")},
        test={"date_of_test": val("2/18/2008")}))
    assert [f.rule for f in findings] == ["date.test_before_completion"]
    assert findings[0].severity is Severity.WARNING


# ------------------------------------------------------------------ depths

def casing(depth):
    return Row(cells={"depth_set": val(depth, page=1)})


def test_a_plug_back_below_total_depth_is_an_error():
    findings = check_depths(doc(completion={
        "total_depth": val("11000'"), "plug_back_depth": val("11400'")}))
    assert [f.rule for f in findings] == ["depth.below_total"]


def test_a_well_formed_depth_set_passes():
    """Synthetic, and synthetic on purpose. The obvious fixture was record
    1493495's Section II, and that record is document 1 of the ground-truth
    set: writing its true depths into a committed test would put the answers
    to a blind eval document in the repository.
    """
    assert check_depths(doc(
        completion={"total_depth": val("11000'"),
                    "plug_back_depth": val("10200'"),
                    "top_of_pay": val("9800'")},
        tables={"casing_strings": (casing("300'"), casing("3100'"),
                                   casing("10900'")),
                "tubing": (Row(cells={"depth_set": val("9500'"),
                                      "packer_set": val("9450'")}),),
                "producing_intervals": (Row(cells={"from": val("9810"),
                                                   "to": val("9860'")}),)})) == []


def test_a_packer_below_the_tubing_shoe_is_an_error():
    findings = check_depths(doc(
        completion={"total_depth": val("11000'")},
        tables={"tubing": (Row(cells={"depth_set": val("9500'"),
                                      "packer_set": val("9600'")}),)}))
    assert [f.rule for f in findings] == ["depth.packer_below_tubing"]


def test_an_inverted_perforation_interval_is_an_error():
    findings = check_depths(doc(
        tables={"producing_intervals": (Row(cells={"from": val("9860'"),
                                                   "to": val("9810'")}),)}))
    assert [f.rule for f in findings] == ["depth.interval_inverted"]


def test_casing_set_out_of_order_is_a_warning():
    """Strings are normally run shallowest first, and a table read out of
    order looks identical to a well completed unusually. Unmeasured, so it is
    surfaced rather than counted.
    """
    findings = check_depths(doc(
        completion={"total_depth": val("11000'")},
        tables={"casing_strings": (casing("3100'"), casing("300'"))}))
    assert [f.rule for f in findings] == ["depth.casing_order"]
    assert findings[0].severity is Severity.WARNING


def test_a_casing_string_below_total_depth_is_an_error():
    findings = check_depths(doc(
        completion={"total_depth": val("11000'")},
        tables={"casing_strings": (casing("11400'"),)}))
    assert [f.rule for f in findings] == ["depth.below_total"]


# --------------------------------------------------------------- the whole

def test_validate_puts_errors_before_warnings():
    findings = validate(doc(
        identity={"api_number": val("42-309-31674"),
                  "county": val("Brazoria"), "completion_date": val("11/18/08")},
        completion={"total_depth": val("11000'")},
        test={"date_of_test": val("2/18/2008")}), BRAZORIA)
    assert [f.severity for f in findings] == [Severity.ERROR, Severity.WARNING]


def test_a_document_with_nothing_checkable_yields_nothing():
    assert validate(doc(), BRAZORIA) == []


def test_a_finding_reads_as_a_sentence():
    finding = Finding("api.county_prefix", Severity.ERROR, "county code 309 "
                      "is not Brazoria (039)", ("identity.api_number",))
    assert str(finding).startswith("error: api.county_prefix: ")
    assert "identity.api_number" in str(finding)
