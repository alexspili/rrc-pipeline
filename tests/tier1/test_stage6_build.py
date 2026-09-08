"""The stage-six build's pure rules: matching, pooling, rows.

The discipline under test: a tie is an abstention, pooling needs both the
floor and the spread, and a region cannot score by drawing large.
"""

from pipeline.formlabels import LabelSpec
from pipeline.template import MAX_REGION_HEIGHT, MAX_REGION_WIDTH
from pipeline.textractforms import KeyValue
from scripts.stage6_templates import (field_region, match_field,
                                      pool_boxes, row_edges)


def kv(text, left=0.1, top=0.2):
    return KeyValue(key_text=text, key_box=(left, top, left + 0.1,
                                            top + 0.01),
                    value_text=None, value_box=None)


def test_the_one_matching_key_is_found():
    pairs = [kv("10. County"), kv("4. ADDRESS")]
    assert match_field(pairs, LabelSpec(("county",))).key_text \
        == "10. County"


def test_every_spec_token_must_match_inside_one_key():
    pairs = [kv("6 LOCATION (Section, Block, and Survey)")]
    assert match_field(pairs, LabelSpec(("location", "block",
                                         "survey"))) is not None
    assert match_field(pairs, LabelSpec(("location", "wildcat"))) is None


def test_two_matching_keys_are_an_abstention_not_a_choice():
    pairs = [kv("14. Completion Date"), kv("Date of Test")]
    assert match_field(pairs, LabelSpec(("date",))) is None


def test_garbled_key_still_matches_at_the_declared_ratio():
    assert match_field([kv("10. Ceunty")], LabelSpec(("county",))) \
        is not None


def test_pooling_needs_the_floor():
    assert pool_boxes([(0.1, 0.2, 0.2, 0.21)], floor=2) is None


def test_pooling_refuses_a_wide_spread():
    boxes = [(0.1, 0.2, 0.2, 0.21), (0.2, 0.2, 0.3, 0.21)]
    assert pool_boxes(boxes, floor=2) is None
    tight = [(0.1, 0.2, 0.2, 0.21), (0.105, 0.2, 0.205, 0.21)]
    assert pool_boxes(tight, floor=2) is not None


def test_field_region_is_capped():
    region = field_region((0.1, 0.1, 0.2, 0.12),
                          (0.1, 0.1, 0.95, 0.9))
    assert region[2] - region[0] <= MAX_REGION_WIDTH + 1e-9
    assert region[3] - region[1] <= MAX_REGION_HEIGHT + 1e-9


def test_row_edges_pool_on_the_modal_row_count():
    grid_a = [(1, (0.1, 0.50, 0.9, 0.55)), (2, (0.1, 0.55, 0.9, 0.60))]
    grid_b = [(1, (0.1, 0.51, 0.9, 0.56)), (2, (0.1, 0.56, 0.9, 0.61))]
    odd = [(1, (0.1, 0.50, 0.9, 0.60))]
    rows = row_edges([grid_a, grid_b, odd], floor=2)
    assert len(rows) == 2
    assert abs(rows[0][1] - 0.505) < 1e-9


def test_row_edges_refuse_when_too_few_pages_agree():
    grid = [(1, (0.1, 0.5, 0.9, 0.55))]
    assert row_edges([grid], floor=2) is None
