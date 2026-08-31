"""Tier 1: a page cannot claim a form number it could not read.

The stage-2 measurement, in one sentence: of the 70 hand-labelled pages the
census called a G-1 or W-2 face, every one of the 20 whose printed form number
could not be read was misclassified. Not most. All of them.

That makes legibility the invariant behind the whole class, so it moves out of
the labelling sheet and into the type. CLAUDE.md rule 6: a rule enforced by a
constructor is worth more than a rule written in a prompt, because the prompt
can be ignored and the constructor cannot.
"""

from __future__ import annotations

import pytest

from pipeline import pageclass as pc
from pipeline.pageclass import (Confidence, Orientation, PageClass, PageLabel,
                                Part)


def label(form_class, part=Part.FACE, legible=None, **kw):
    return PageLabel(
        record_id="1501720", file_index=0, page=2,
        form_class=form_class, part=part, orientation=Orientation.UP,
        confidence=Confidence.HIGH, form_number_legible=legible, **kw)


# ------------------------------------------------- the invariant itself

@pytest.mark.parametrize("named", sorted(pc.EXTRACTION_TARGETS,
                                         key=lambda c: c.value))
def test_a_named_completion_report_needs_a_readable_number(named):
    with pytest.raises(ValueError, match="no form number can be read"):
        label(named, legible=False)


def test_the_same_page_is_constructible_as_an_abstention():
    """The error has somewhere to go. That is what makes the invariant a
    routing rule rather than a refusal.
    """
    page = label(PageClass.COMPLETION_FACE_UNKNOWN_FORM, legible=False)
    assert page.extraction_eligible


def test_a_readable_number_is_still_free_to_name_its_form():
    assert label(PageClass.G1, legible=True).form_class is PageClass.G1


def test_a_label_that_never_answered_the_question_still_builds():
    """Stage-1 labels and every census row written before 2026-08-31 predate
    the field. Making it required would invalidate the ground truth the
    project has already measured itself against.
    """
    assert label(PageClass.G1, legible=None).form_number_legible is None


# --------------------------------------- the two abstentions are distinct

def test_a_legacy_form_is_the_one_whose_number_you_can_read():
    """Form 2, Form 3 and GWT-1 are identified BY their printed number. An
    illegible page is not a legacy form, it is an unknown one.
    """
    assert label(PageClass.COMPLETION_FACE_LEGACY, legible=True)
    with pytest.raises(ValueError, match="cannot be illegible"):
        label(PageClass.COMPLETION_FACE_LEGACY, legible=False)


def test_an_unknown_form_is_the_one_whose_number_you_cannot():
    with pytest.raises(ValueError, match="If it can be read, name the form"):
        label(PageClass.COMPLETION_FACE_UNKNOWN_FORM, legible=True)


@pytest.mark.parametrize("cls", [PageClass.COMPLETION_FACE_UNKNOWN_FORM,
                                 PageClass.COMPLETION_FACE_LEGACY])
def test_both_abstentions_are_faces_and_only_faces(cls):
    legible = cls is PageClass.COMPLETION_FACE_LEGACY
    for part in (Part.SEC_II, Part.CONTINUATION, Part.BACK_INSTRUCTIONS,
                 Part.UNKNOWN):
        with pytest.raises(ValueError, match="is a face; part must be face"):
            label(cls, part=part, legible=legible)
    with pytest.raises(ValueError, match="part is required"):
        label(cls, part=None, legible=legible)


# ------------------------------------------------------------ the union

def test_the_record_level_union_counts_every_completion_class():
    """The reason abstention costs nothing at the record level. A record whose
    only completion page is an abstention still holds a completion report.
    """
    one_of_each = [
        label(PageClass.G1, legible=True),
        label(PageClass.COMPLETION_FACE_UNKNOWN_FORM, legible=False),
        label(PageClass.COMPLETION_FACE_LEGACY, legible=True),
    ]
    for page in one_of_each:
        census = pc.aggregate([page])
        assert census.records_with_completion_report == 1, page.form_class


def test_a_record_moving_from_a_guess_to_an_abstention_is_still_counted():
    """The whole argument for abstention in one assertion. Before: the census
    called this page a W-2 on no evidence. After: it declines to. The record
    is counted either way, so the verified 115 does not move.
    """
    before = pc.aggregate([label(PageClass.W2, legible=None)])
    after = pc.aggregate([label(PageClass.COMPLETION_FACE_UNKNOWN_FORM,
                                legible=False)])
    assert before.records_with_completion_report == 1
    assert after.records_with_completion_report == 1


def test_an_abstention_does_not_count_as_a_g1_or_a_w2():
    """The other half: it must not quietly keep inflating the per-form split
    it was created to stop inflating.
    """
    census = pc.aggregate([label(PageClass.COMPLETION_FACE_UNKNOWN_FORM,
                                 legible=False)])
    assert census.records_by_class[PageClass.G1] == 0
    assert census.records_by_class[PageClass.W2] == 0


# ------------------------------------------------------- model responses

def test_a_response_without_the_legibility_answer_is_refused():
    """A model that omits the field would otherwise get None and slip past the
    invariant, which is exactly the hole the invariant exists to close.
    """
    body = ('{"form_class": "g1", "part": "face", "orientation": "up", '
            '"confidence": "high", "alt_class": null}')
    with pytest.raises(ValueError, match="form_number_legible"):
        pc.parse_response(body, record_id="1501720", file_index=0, page=2,
                          oversize=False)


def test_a_non_boolean_legibility_answer_is_refused():
    body = ('{"form_class": "g1", "part": "face", "orientation": "up", '
            '"confidence": "high", "alt_class": null, '
            '"form_number_legible": "unknown"}')
    with pytest.raises(ValueError, match="is not true or false"):
        pc.parse_response(body, record_id="1501720", file_index=0, page=2,
                          oversize=False)


def test_a_guess_on_an_unreadable_page_is_refused_at_the_parser():
    """End to end: the model answering g1 on a page it admits it cannot read
    does not produce a label at all. It produces a parse failure, which the
    census already counts and reports.
    """
    body = ('{"form_class": "g1", "part": "face", "orientation": "up", '
            '"confidence": "high", "alt_class": null, '
            '"form_number_legible": false}')
    with pytest.raises(ValueError, match="no form number can be read"):
        pc.parse_response(body, record_id="1501720", file_index=0, page=2,
                          oversize=False)


# ------------------------------------------------------------- taxonomy

@pytest.mark.parametrize("token", ["FORM 2", "FORM 3", "GWT-1"])
def test_the_pre_numbering_forms_now_have_a_class(token):
    """Closes the taxonomy half of DEFECTS #17. The scanner learned to see
    these tokens on 2026-08-31; this is the class it hands them to.
    """
    assert pc.form_token_class(token) is PageClass.COMPLETION_FACE_LEGACY
