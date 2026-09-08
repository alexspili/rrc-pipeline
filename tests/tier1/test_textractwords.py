"""pipeline/textractwords.py: the DetectDocumentText parser.

The fixture dicts here are synthetic, shaped from the documented response
(Blocks of BlockType WORD carrying Geometry.BoundingBox ratios). The
stage-five bounded probe verifies a real response against the same shape
before the corpus read; these tests pin what the parser refuses.
"""

import pytest

from pipeline.textractwords import (TextractShape, words_from_response,
                                    words_only)


def response(blocks, pages=1):
    return {"DocumentMetadata": {"Pages": pages}, "Blocks": blocks}


def word(text, left=0.1, top=0.2, width=0.05, height=0.01, conf=99.0):
    return {"BlockType": "WORD", "Text": text, "Confidence": conf,
            "Geometry": {"BoundingBox": {"Left": left, "Top": top,
                                         "Width": width, "Height": height}}}


def test_word_becomes_textlayer_tuple():
    words = words_from_response(response([word("ELEVATION")]))
    (box, confidence), = words
    assert box == (0.1, 0.2, 0.15000000000000002, 0.21000000000000002,
                   "ELEVATION")
    assert confidence == 99.0


def test_page_and_line_blocks_are_skipped():
    blocks = [{"BlockType": "PAGE"}, {"BlockType": "LINE", "Text": "A B"},
              word("DEPTH")]
    assert [w[4] for w in words_only(response(blocks))] == ["DEPTH"]


def test_multi_page_response_refused():
    with pytest.raises(TextractShape):
        words_from_response(response([word("X")], pages=2))


def test_coordinate_past_the_right_edge_refused():
    with pytest.raises(TextractShape):
        words_from_response(response([word("X", left=0.98, width=0.05)]))


def test_negative_coordinate_refused():
    with pytest.raises(TextractShape):
        words_from_response(response([word("X", top=-0.01)]))


def test_word_without_geometry_refused():
    broken = {"BlockType": "WORD", "Text": "X", "Confidence": 99.0}
    with pytest.raises(TextractShape):
        words_from_response(response([broken]))


def test_word_without_confidence_refused():
    broken = word("X")
    del broken["Confidence"]
    with pytest.raises(TextractShape):
        words_from_response(response([broken]))


def test_degenerate_box_refused():
    with pytest.raises(TextractShape):
        words_from_response(response([word("X", width=0.0)]))
