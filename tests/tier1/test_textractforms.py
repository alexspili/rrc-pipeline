"""pipeline/textractforms.py: the AnalyzeDocument parser.

Synthetic fixtures shaped from the documented response; the stage-six
bounded probe verifies a real response against the same shape before the
batch is sent.
"""

import pytest

from pipeline.textractforms import key_values, tables
from pipeline.textractwords import TextractShape


def block(block_type, block_id, box=(0.1, 0.2, 0.05, 0.01), **extra):
    left, top, width, height = box
    return {"BlockType": block_type, "Id": block_id,
            "Geometry": {"BoundingBox": {"Left": left, "Top": top,
                                         "Width": width, "Height": height}},
            **extra}


def word(block_id, text, box=(0.1, 0.2, 0.05, 0.01)):
    return block("WORD", block_id, box, Text=text)


def response(blocks):
    return {"DocumentMetadata": {"Pages": 1}, "Blocks": blocks}


def kv_response():
    return response([
        block("KEY_VALUE_SET", "k1", (0.1, 0.2, 0.10, 0.01),
              EntityTypes=["KEY"],
              Relationships=[{"Type": "VALUE", "Ids": ["v1"]},
                             {"Type": "CHILD", "Ids": ["w1", "w2"]}]),
        block("KEY_VALUE_SET", "v1", (0.25, 0.2, 0.08, 0.01),
              EntityTypes=["VALUE"],
              Relationships=[{"Type": "CHILD", "Ids": ["w3"]}]),
        word("w1", "LEASE"), word("w2", "NAME"),
        word("w3", "Newberry", (0.25, 0.2, 0.08, 0.01)),
    ])


def test_key_value_pair_with_geometry_and_texts():
    (pair,), = [key_values(kv_response())]
    assert pair.key_text == "LEASE NAME"
    assert pair.key_box == (0.1, 0.2, 0.2, 0.21000000000000002)
    assert pair.value_text == "Newberry"
    assert pair.value_box[0] == 0.25


def test_key_without_value_link_yields_none_value():
    resp = response([
        block("KEY_VALUE_SET", "k1", EntityTypes=["KEY"],
              Relationships=[{"Type": "CHILD", "Ids": ["w1"]}]),
        word("w1", "ADDRESS")])
    (pair,) = key_values(resp)
    assert pair.key_text == "ADDRESS"
    assert pair.value_box is None and pair.value_text is None


def test_value_entities_are_not_listed_as_keys():
    assert len(key_values(kv_response())) == 1


def test_selection_element_reads_as_status():
    resp = response([
        block("KEY_VALUE_SET", "k1", EntityTypes=["KEY"],
              Relationships=[{"Type": "VALUE", "Ids": ["v1"]},
                             {"Type": "CHILD", "Ids": ["w1"]}]),
        block("KEY_VALUE_SET", "v1", EntityTypes=["VALUE"],
              Relationships=[{"Type": "CHILD", "Ids": ["s1"]}]),
        word("w1", "Retest"),
        block("SELECTION_ELEMENT", "s1", SelectionStatus="SELECTED")])
    (pair,) = key_values(resp)
    assert pair.value_text == "[SELECTED]"


def test_table_with_cells_and_row_count():
    resp = response([
        block("TABLE", "t1", (0.1, 0.5, 0.8, 0.2),
              Relationships=[{"Type": "CHILD", "Ids": ["c1", "c2"]}]),
        block("CELL", "c1", (0.1, 0.5, 0.4, 0.1), RowIndex=1,
              ColumnIndex=1,
              Relationships=[{"Type": "CHILD", "Ids": ["w1"]}]),
        block("CELL", "c2", (0.1, 0.6, 0.4, 0.1), RowIndex=2,
              ColumnIndex=1),
        word("w1", "CASING")])
    (table,) = tables(resp)
    assert table.rows == 2
    assert table.cells[0].text == "CASING"
    assert table.cells[1].box[1] == 0.6


def test_bad_geometry_raises_not_clamps():
    resp = response([
        block("KEY_VALUE_SET", "k1", (0.9, 0.2, 0.2, 0.01),
              EntityTypes=["KEY"])])
    with pytest.raises(TextractShape):
        key_values(resp)


def test_edge_float_noise_is_clamped_like_stage_five():
    resp = response([
        block("KEY_VALUE_SET", "k1", (0.95, 0.2, 0.0500000093, 0.01),
              EntityTypes=["KEY"])])
    (pair,) = key_values(resp)
    assert pair.key_box[2] == 1.0
