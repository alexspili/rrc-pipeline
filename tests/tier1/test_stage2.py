"""Tier 1: stage-2 strata are disjoint and decided before the draw.

Pure. Every case here is a rule from docs/labeling-protocol-stage2.md, so the
protocol and the code cannot drift apart without something going red.
"""

from __future__ import annotations

import pytest

from pipeline import stage2
from pipeline.pageclass import Part


def stratum(form_class=None, part=None, oversize=False, parse_failed=False,
            tokens=()):
    return stage2.assign_stratum(form_class, part, oversize, parse_failed,
                                 frozenset(tokens))


def test_a_completion_face_splits_on_whether_ocr_read_its_number():
    assert stratum("g1", "face") == stage2.G1_FACE_SILENT
    assert stratum("g1", "face", tokens={"G-1"}) == stage2.G1_FACE_CORROBORATED
    assert stratum("w2", "face") == stage2.W2_FACE_SILENT
    assert stratum("w2", "face", tokens={"W-2"}) == stage2.W2_FACE_CORROBORATED


def test_a_w2_face_whose_own_header_reads_w15_is_its_own_stratum():
    """Seven pages, drawn whole. Alex found this confusion by hand on records
    1995379 and 2396691 while verifying the census.
    """
    assert stratum("w2", "face", tokens={"W-15"}) == stage2.W2_FACE_W15_HEADER


def test_the_pages_own_number_wins_over_another_form_it_mentions():
    """A page whose header reads both W-2 and W-15 is corroborated, not
    suspect. The suspect cell is the one where OCR found a number and it was
    not the one the model chose.
    """
    assert (stratum("w2", "face", tokens={"W-2", "W-15"})
            == stage2.W2_FACE_CORROBORATED)


def test_an_unrelated_header_token_does_not_corroborate():
    """One predicted G-1 face carries a P-5 header and nothing else. P-5 is
    not evidence either way, so the page stays in the contested stratum.
    """
    assert stratum("g1", "face", tokens={"P-5"}) == stage2.G1_FACE_SILENT


def test_every_non_face_completion_page_lands_in_one_stratum():
    """Section II, Section III, continuations and printed backs carry no form
    number. Splitting them by predicted class would build the guess being
    measured into the design.
    """
    for part in (Part.SEC_II, Part.SEC_III, Part.CONTINUATION,
                 Part.BACK_INSTRUCTIONS, Part.UNKNOWN):
        for form_class in ("g1", "w2"):
            assert (stratum(form_class, part.value)
                    == stage2.COMPLETION_NON_FACE), (form_class, part)


def test_the_confusable_classes_are_the_ones_a_completion_face_hides_in():
    for form_class in ("w15", "g5", "l1", "ws1_sw1", "other_form"):
        assert stratum(form_class, "face") == stage2.CONFUSABLE


def test_an_unidentifiable_form_page_is_confusable_whatever_its_part():
    """`other_form` with no part is the class for a form page that names no
    form. Those are exactly the pages a completion section could be sitting in.
    """
    assert stratum("other_form", "unknown") == stage2.CONFUSABLE
    assert stratum("other_form", "continuation") == stage2.CONFUSABLE
    assert stratum("other_form", None) == stage2.CONFUSABLE


def test_pages_outside_the_frame_get_no_stratum():
    for form_class in ("p4", "letter_memo", "plat_map", "blank_or_artifact",
                       "separator_card", "w1", "w3", "w12", "schematic"):
        assert stratum(form_class, "face" if form_class in
                       ("p4", "w1", "w3", "w12") else None) is None


def test_a_parse_failure_outranks_everything():
    """A failed row has no prediction to stratify on, whatever else is true
    of the page.
    """
    assert stratum("g1", "face", parse_failed=True) == stage2.PARSE_FAILURE
    assert stratum(None, None, oversize=True,
                   parse_failed=True) == stage2.PARSE_FAILURE


def test_oversize_outranks_the_class_strata():
    """No oversize page is currently predicted a completion face, and
    tests/tier2 checks that. The precedence exists so that disjointness does
    not depend on it staying true.
    """
    assert stratum("g1", "face", oversize=True) == stage2.OVERSIZE
    assert stratum("plat_map", None, oversize=True) == stage2.OVERSIZE


def test_the_allocation_covers_every_stratum_the_assigner_can_return():
    returned = {
        stratum("g1", "face"), stratum("g1", "face", tokens={"G-1"}),
        stratum("w2", "face"), stratum("w2", "face", tokens={"W-2"}),
        stratum("w2", "face", tokens={"W-15"}), stratum("g1", "sec_ii"),
        stratum("w15", "face"), stratum(None, None, oversize=True),
        stratum(None, None, parse_failed=True),
    }
    assert returned == set(stage2.ALLOCATION)


def test_the_scored_strata_exclude_the_two_add_ons():
    assert stage2.OVERSIZE not in stage2.SCORED
    assert stage2.PARSE_FAILURE not in stage2.SCORED
    assert sum(stage2.ALLOCATION[s] for s in stage2.SCORED) == 105


@pytest.mark.parametrize("token", ["g-1", "G-1", "  G-1  ".strip()])
def test_token_case_does_not_decide_a_stratum(token):
    assert stratum("g1", "face", tokens={token}) == stage2.G1_FACE_CORROBORATED


def test_a_printed_back_of_an_unidentified_form_is_outside_the_frame():
    """G is a recall instrument for completion faces. A pre-printed reverse
    cannot be one, and the 73 `other_form` backs would be a fifth of the
    stratum's frame diluting 20 draws that have little enough power already.
    Predicted-completion backs are in F, where they belong.
    """
    assert stratum("other_form", "back_instructions") is None
    assert stratum("w15", "back_instructions") is None
