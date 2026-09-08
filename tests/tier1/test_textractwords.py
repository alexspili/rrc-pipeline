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


def test_float_noise_at_the_page_edge_is_clamped_not_refused():
    """DEFECTS #76: Textract returns edge-flush boxes whose Left+Width is
    a few parts per billion over 1.0. Three real pages were refused."""
    blocks = [word("X", left=0.95, width=0.0500000093)]
    (box, _), = words_from_response(response(blocks))
    assert box[2] == 1.0


def test_a_real_overrun_is_still_refused():
    with pytest.raises(TextractShape):
        words_from_response(response([word("X", left=0.95, width=0.06)]))


def test_wide_spread_anchor_is_gated_out_of_the_build():
    """DEFECTS #77: typed filling recurs across a one-district corpus and
    pooled through the 25% floor. The spread gate is what removes it."""
    from scripts.stage5_templates import MAX_ANCHOR_SPREAD, spread_gate

    class A:
        def __init__(self, spread):
            self.spread = spread

    anchors = {"witness": A((0.002, 0.002)),      # printed form
               "houston": A((0.305, 0.605)),      # operator addresses
               "chambers": A((0.288, 0.029))}     # typed county values
    kept = spread_gate(anchors, MAX_ANCHOR_SPREAD)
    assert set(kept) == {"witness"}


# ----------------------------------------------------------- alias harvest

from pipeline.textractwords import expand_anchors, harvest_aliases  # noqa: E402


def w(text, left, top, width=0.06, height=0.01):
    return (left, top, left + width, top + height, text)


def test_colocated_different_spelling_is_an_alias():
    aliases = harvest_aliases([w("ELEVATION", 0.1, 0.2)],
                              [w("ELEVATLON", 0.101, 0.2)])
    assert aliases == {"elevation": "elevatlon"}


def test_identical_spelling_is_not_an_alias():
    assert harvest_aliases([w("ELEVATION", 0.1, 0.2)],
                           [w("ELEVATION", 0.101, 0.2)]) == {}


def test_word_not_unique_on_its_page_never_pairs():
    textract = [w("ELEVATION", 0.1, 0.2), w("ELEVATION", 0.1, 0.8)]
    assert harvest_aliases(textract, [w("ELEVATLON", 0.101, 0.2)]) == {}


def test_two_embedded_words_over_one_clean_word_abstain():
    embedded = [w("ELEVATLON", 0.1, 0.2), w("ELEVAT1ON", 0.11, 0.2)]
    assert harvest_aliases([w("ELEVATION", 0.1, 0.2)], embedded) == {}


def test_distant_words_never_pair():
    assert harvest_aliases([w("ELEVATION", 0.1, 0.2)],
                           [w("ELEVATLON", 0.5, 0.8)]) == {}


def test_expand_maps_alias_to_its_anchors_entry():
    anchors = {"elevation": "ANCHOR"}
    out = expand_anchors(anchors, {"elevation": ["elevatlon"]})
    assert out["elevatlon"] == "ANCHOR"
    assert out["elevation"] == "ANCHOR"


def test_alias_claimed_by_two_anchors_is_dropped():
    anchors = {"elevation": "A", "eievation": "B"}
    out = expand_anchors(anchors, {"elevation": ["elevatlon"],
                                   "eievation": ["elevatlon"]})
    assert "elevatlon" not in out


def test_alias_shadowing_a_real_token_is_dropped():
    anchors = {"elevation": "A", "elevatlon": "B"}
    out = expand_anchors(anchors, {"elevation": ["elevatlon"]})
    assert out["elevatlon"] == "B"
