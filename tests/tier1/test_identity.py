"""Tier 1 for pipeline.identity's parser: pure, no model, no PDFs.

Origin: DEFECTS #38. The parser attached the model's text to a value whatever
the status said, and the `Value` constructor refused it. The extractor has
handled this since it was written; the new reader was written without
carrying the rule across.
"""

import pytest

from pipeline import identity
from pipeline.extract import Status


def body(**fields):
    import json
    return json.dumps({name: spec for name, spec in fields.items()})


def test_a_present_value_keeps_its_text_and_gets_a_page_level_region():
    values = identity.parse(body(
        operator_name={"status": "present", "raw": "SKELLY OIL COMPANY"}), 5).values
    value = values["operator_name"]
    assert value.status is Status.PRESENT
    assert value.raw == "SKELLY OIL COMPANY"
    assert value.region is not None
    assert value.region.page == 5
    assert value.region.source == "page"
    assert value.region.box == (0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize("status", ["blank", "illegible", "not_on_this_form"])
def test_a_non_present_value_carries_no_text(status):
    """DEFECTS #38. The model returned illegible with raw '2:-73-67'."""
    values = identity.parse(body(
        completion_date={"status": status, "raw": "2:-73-67"}), 5).values
    value = values["completion_date"]
    assert value.status is Status(status)
    assert value.raw is None and value.value is None
    assert value.region is None


def test_a_present_value_with_no_text_becomes_illegible():
    values = identity.parse(body(
        lease_name={"status": "present", "raw": None}), 5).values
    assert values["lease_name"].status is Status.ILLEGIBLE
    assert values["lease_name"].raw is None


def test_a_field_the_model_omitted_is_not_on_this_form():
    values = identity.parse(body(), 5).values
    assert set(values) == set(identity.FIELDS)
    assert all(v.status is Status.NOT_ON_THIS_FORM for v in values.values())


def test_identity_for_gives_reassembly_only_the_present_values():
    read = identity.identity_for(identity.parse(body(
        operator_name={"status": "present", "raw": "Sun Oil Company"},
        lease_name={"status": "blank", "raw": None}), 5))
    assert read["operator_name"] == "Sun Oil Company"
    assert read["lease_name"] is None


# --------------------------------------------------------------- DEFECTS #42

def test_a_value_carries_the_printed_label_it_came_from():
    read = identity.parse(body(
        lease_name={"status": "present", "raw": "State Tract 130",
                    "found_in": "32. Location of Well, Relative to Lease "
                                "Boundaries"}), 10)
    assert read.values["lease_name"].raw == "State Tract 130"
    assert read.found_in["lease_name"].startswith("32.")


def test_found_in_is_recorded_even_when_the_value_looks_ordinary():
    """The whole failure was that a wrong-field read looks exactly like a
    right-field one. So the label is recorded on every present value, not
    only on the ones that look odd."""
    read = identity.parse(body(
        completion_date={"status": "present", "raw": "9-22-77",
                         "found_in": "30. ... Operations Completed"}), 10)
    assert read.found_in["completion_date"] == "30. ... Operations Completed"


def test_a_non_present_value_has_no_source_to_report():
    read = identity.parse(body(
        completion_date={"status": "not_on_this_form", "raw": None,
                         "found_in": "14. Completion Date"}), 10)
    assert read.found_in["completion_date"] is None


def test_a_missing_found_in_is_none_and_not_an_error():
    """found_in is a claim the model may simply not make. Its absence is not
    a parse failure; it is one less thing a human can check."""
    read = identity.parse(body(
        operator_name={"status": "present", "raw": "Sun Oil Company"}), 10)
    assert read.values["operator_name"].raw == "Sun Oil Company"
    assert read.found_in["operator_name"] is None


def test_the_prompt_asks_for_the_lease_name_where_a_section_prints_it():
    """Record 1493495 page 10 prints it inside field 32, not in a LEASE NAME
    box, and the 1966 revision prints the same field the same way."""
    after = identity.SYSTEM.split("lease_name", 1)[1][:600]
    assert "32" in after and "Line of The" in after
