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
        operator_name={"status": "present", "raw": "SKELLY OIL COMPANY"}), 5)
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
        completion_date={"status": status, "raw": "2:-73-67"}), 5)
    value = values["completion_date"]
    assert value.status is Status(status)
    assert value.raw is None and value.value is None
    assert value.region is None


def test_a_present_value_with_no_text_becomes_illegible():
    values = identity.parse(body(
        lease_name={"status": "present", "raw": None}), 5)
    assert values["lease_name"].status is Status.ILLEGIBLE
    assert values["lease_name"].raw is None


def test_a_field_the_model_omitted_is_not_on_this_form():
    values = identity.parse(body(), 5)
    assert set(values) == set(identity.FIELDS)
    assert all(v.status is Status.NOT_ON_THIS_FORM for v in values.values())


def test_identity_for_gives_reassembly_only_the_present_values():
    values = identity.parse(body(
        operator_name={"status": "present", "raw": "Sun Oil Company"},
        lease_name={"status": "blank", "raw": None}), 5)
    read = identity.identity_for(values)
    assert read["operator_name"] == "Sun Oil Company"
    assert read["lease_name"] is None
