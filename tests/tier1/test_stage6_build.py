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
    grid_a = [(1, (0.1, 0.50, 0.9, 0.55), "SIZE"),
              (2, (0.1, 0.55, 0.9, 0.60), "9-5/8")]
    grid_b = [(1, (0.1, 0.51, 0.9, 0.56), "SIZE"),
              (2, (0.1, 0.56, 0.9, 0.61), "16 in")]
    odd = [(1, (0.1, 0.50, 0.9, 0.60), "SIZE")]
    rows, header_rows = row_edges([grid_a, grid_b, odd], floor=2)
    assert len(rows) == 2
    assert abs(rows[0][1] - 0.505) < 1e-9
    # row 1's text recurs across pages (printed), row 2's varies (filling)
    assert header_rows == 1


def test_row_edges_refuse_when_too_few_pages_agree():
    grid = [(1, (0.1, 0.5, 0.9, 0.55), "SIZE")]
    assert row_edges([grid], floor=2) is None


def test_a_table_inside_a_larger_block_is_a_match():
    """The stage-five block runs from its heading to the next heading, so
    it is legitimately larger than the ruled grid inside it; symmetric
    IoU sat at 0.2 on all 16 rev4183 reverses and no rows pooled. The
    criterion is containment: most of the TABLE inside the block."""
    from scripts.stage6_templates import table_matches
    block = (0.1, 0.5, 0.9, 0.9)
    table = (0.15, 0.55, 0.85, 0.65)     # small grid inside the block
    assert table_matches(table, block)
    outside = (0.15, 0.05, 0.85, 0.15)
    assert not table_matches(outside, block)
    straddling = (0.15, 0.45, 0.85, 0.55)  # only half inside
    assert not table_matches(straddling, block)
