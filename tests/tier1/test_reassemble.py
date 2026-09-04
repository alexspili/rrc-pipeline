"""Tier 1 for pipeline.reassemble: pure, no corpus, no model.

The first test is DEFECTS #25's pending pin, which has been waiting since
2026-09-01: on record 1495193, pages 7 and 8 must resolve to one document and
pages 7 and 9 must not.

The load-bearing tests are the abstentions. This module's anti-goal is stated
in docs/modules/reassemble.md: it must not improve its numbers by attaching
more pages, because a wrong attachment puts one well's casing record under
another well's identity and every downstream check would then be validating a
document that never existed.
"""

import pytest

from pipeline import reassemble as ra


def page(number, part=None, form_class="w2", record="1495193", file_index=0,
         **identity):
    return ra.PageRecord(record_id=record, file_index=file_index,
                         page=number, form_class=form_class, part=part,
                         identity=identity)


SUN = dict(operator_name="Sun Oil Company", lease_name="State Tract 130",
           completion_date="9-22-77")
GULF = dict(operator_name="Gulf Oil Corporation", lease_name="Cockburn",
            completion_date="3-11-68")


# --------------------------------------------------------- DEFECTS #25's pin

def test_a_section_before_its_face_groups_with_it_and_not_with_the_next():
    """Record 1495193: page 8 is a section of the report whose face is page
    7, and the census called page 8 a face of its own. Page 9 is a different
    report. A forward-only heuristic put page 8 with page 9."""
    face7 = page(7, "face", **SUN)
    section8 = page(8, "sec_ii", **SUN)
    face9 = page(9, "face", **GULF)
    documents, unattached = ra.group([face7, section8, face9])

    grouped = {d.face.page: [p.page for p in d.pages] for d in documents}
    assert grouped[7] == [7, 8]
    assert grouped[9] == [9]
    assert not unattached


# ------------------------------------------------- agreement, not proximity

def test_agreement_decides_and_position_does_not():
    """Record 1511465's shape: three faces and one section. The section goes
    to the face it agrees with, not to the one it sits next to."""
    near = page(7, "face", **GULF)
    section = page(8, "sec_ii", **SUN)
    far = page(30, "face", **SUN)
    documents, unattached = ra.group([near, section, far])
    grouped = {d.face.page: [p.page for p in d.pages] for d in documents}
    assert grouped[30] == [8, 30]
    assert grouped[7] == [7]
    assert not unattached


def test_two_pages_agreeing_on_nothing_do_not_group():
    face = page(7, "face", **SUN)
    section = page(8, "sec_ii")
    documents, unattached = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7]
    assert unattached[0].reason == "below_threshold"


def test_one_agreeing_field_is_not_enough():
    """Every well on a lease shares a lease name."""
    face = page(7, "face", lease_name="State Tract 130",
                operator_name="Sun Oil Company", well_number="1")
    section = page(8, "sec_ii", lease_name="State Tract 130")
    _, unattached = ra.group([face, section])
    assert unattached[0].reason == "below_threshold"


# ------------------------------------------------------------ the abstentions

def test_a_contradiction_rejects_a_pair_however_much_else_agrees():
    """Two pages naming different operators are not one document."""
    face = page(7, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130", completion_date="9-22-77",
                well_number="1")
    section = page(8, "sec_ii", operator_name="Gulf Oil Corporation",
                   lease_name="State Tract 130", completion_date="9-22-77",
                   well_number="1")
    agreements, contradicted = ra.score(section, face)
    assert agreements == 3 and contradicted
    _, unattached = ra.group([face, section])
    assert unattached[0].reason == "contradicted"


def test_a_tie_between_two_faces_attaches_to_neither():
    """Breaking it by nearness would put position back in as the decider."""
    first = page(7, "face", **SUN)
    second = page(20, "face", **SUN)
    section = page(8, "sec_ii", **SUN)
    documents, unattached = ra.group([first, second, section])
    assert all(len(d.pages) == 1 for d in documents)
    assert unattached[0].reason == "tie"


def test_a_unique_best_score_still_wins():
    strong = page(7, "face", **SUN, well_number="1")
    weak = page(20, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130")
    section = page(8, "sec_ii", **SUN, well_number="1")
    documents, unattached = ra.group([strong, weak, section])
    grouped = {d.face.page: [p.page for p in d.pages] for d in documents}
    assert grouped[7] == [7, 8] and grouped[20] == [20]
    assert not unattached


def test_one_page_never_attaches_to_two_faces():
    faces = [page(7, "face", **SUN, well_number="1"),
             page(20, "face", **SUN)]
    section = page(8, "sec_ii", **SUN, well_number="1")
    documents, _ = ra.group(faces + [section])
    homes = [d.face.page for d in documents if section in d.pages]
    assert len(homes) == 1


def test_an_unmatched_page_is_reported_and_never_dropped():
    section = page(8, "sec_ii", **SUN)
    documents, unattached = ra.group([section])
    assert documents == []
    assert [u.page.page for u in unattached] == [8]
    assert unattached[0].reason == "no_face"


def test_a_face_with_no_candidates_is_a_one_page_document():
    """The common case: most of this archive was imaged front only."""
    documents, unattached = ra.group([page(7, "face", **SUN)])
    assert [p.page for p in documents[0].pages] == [7]
    assert not unattached


# ------------------------------------------------------------- file boundary

def test_candidates_never_cross_a_file_boundary():
    """A record can hold five files and page 3 of one has nothing to do with
    page 3 of another (DEFECTS #28)."""
    with pytest.raises(ValueError):
        ra.group([page(3, "face", file_index=0, **SUN),
                  page(3, "sec_ii", file_index=1, **SUN)])


# ------------------------------------------------------------- normalisation

def test_comparison_is_exact_after_normalising_and_never_fuzzy():
    """`SKELLY OIL COMPANY` and `Skelly Oil Co.` do not match. The module
    abstains where a similarity judgement would guess, because a fuzzy match
    that pairs two different wells is the failure this must never make."""
    face = page(7, "face", operator_name="SKELLY OIL COMPANY",
                lease_name="F. G. Cobb B")
    section = page(8, "sec_ii", operator_name="Skelly Oil Co.",
                   lease_name="F. G. Cobb B")
    verdicts = ra.compare(section, face)
    assert verdicts["operator_name"] == ra.DISAGREES
    assert verdicts["lease_name"] == ra.AGREES


def test_punctuation_and_case_are_not_a_disagreement():
    face = page(7, "face", operator_name="SKELLY OIL COMPANY")
    section = page(8, "sec_ii", operator_name="Skelly  Oil, Company.")
    assert ra.compare(section, face)["operator_name"] == ra.AGREES


def test_a_two_digit_year_and_a_four_digit_year_are_one_date():
    face = page(7, "face", completion_date="4-15-75")
    section = page(8, "sec_ii", completion_date="4/15/1975")
    assert ra.compare(section, face)["completion_date"] == ra.AGREES


def test_a_leading_zero_district_is_one_district():
    face = page(7, "face", rrc_district="03")
    section = page(8, "sec_ii", rrc_district="3")
    assert ra.compare(section, face)["rrc_district"] == ra.AGREES


def test_a_missing_field_on_either_side_is_unknown_not_a_disagreement():
    face = page(7, "face", operator_name="Sun Oil Company")
    section = page(8, "sec_ii")
    verdicts = ra.compare(section, face)
    assert verdicts["operator_name"] == ra.UNKNOWN
    assert ra.DISAGREES not in verdicts.values()


# --------------------------------------------------------------- total depth

def test_total_depth_can_raise_a_score():
    face = page(7, "face", operator_name="Sun Oil Company",
                total_depth="9200")
    section = page(8, "sec_ii", operator_name="Sun Oil Company",
                   total_depth="9200'")
    agreements, contradicted = ra.score(section, face)
    assert agreements == 2 and not contradicted
    documents, unattached = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


def test_total_depth_can_never_reject_a_pair():
    """A face and its section can differ where one carries a correction."""
    face = page(7, "face", **SUN, total_depth="9200")
    section = page(8, "sec_ii", **SUN, total_depth="9250")
    agreements, contradicted = ra.score(section, face)
    assert not contradicted
    documents, _ = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]


# ------------------------------------------------------------ the diagnostic

def test_the_contradicted_but_agreeing_list_reports_what_the_veto_rejected():
    """Alex asked for this before the semantics are called settled: every
    such pair is either the veto working or one document split by an
    abbreviation, and only the paper separates them."""
    face = page(7, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130", completion_date="9-22-77")
    section = page(8, "sec_ii", operator_name="Sun Oil Co",
                   lease_name="State Tract 130", completion_date="9-22-77")
    rows = ra.contradicted_but_agreeing([face, section])
    assert len(rows) == 1
    candidate, matched, disagreed, agreed = rows[0]
    assert candidate.page == 8 and matched.page == 7
    assert disagreed == ("operator_name",)
    assert set(agreed) == {"lease_name", "completion_date"}


def test_the_diagnostic_is_silent_when_nothing_is_contradicted():
    face = page(7, "face", **SUN)
    section = page(8, "sec_ii", **SUN)
    assert ra.contradicted_but_agreeing([face, section]) == []


# ------------------------------------------------------------------ evidence

def test_a_document_records_which_fields_bought_each_attachment():
    face = page(7, "face", **SUN)
    section = page(8, "sec_ii", **SUN)
    documents, _ = ra.group([face, section])
    assert documents[0].evidence == (
        (8, ("operator_name", "lease_name", "completion_date")),)


def test_the_identity_reader_reads_exactly_the_fields_reassembly_compares():
    """Two modules, one vocabulary. A field added to one and not the other
    would be compared as unknown forever and nobody would see it."""
    from pipeline.identity import FIELDS
    assert set(FIELDS) == set(ra.IDENTITY_FIELDS) | set(ra.BONUS_FIELDS)


# --------------------------------------------------------------- DEFECTS #39

def test_a_written_non_value_cannot_contradict():
    """An operator wrote "N.A." in the completion date box, and the reader
    correctly reported what is written. A page that declines to answer must
    not be able to veto a true pairing."""
    face = page(7, "face", operator_name="U.S. Enercorp, Ltd.",
                lease_name="Kotzur", completion_date="5/19/06")
    section = page(8, "sec_ii", operator_name="U.S. Enercorp, Ltd.",
                   lease_name="Kotzur", completion_date="N/A")
    verdicts = ra.compare(section, face)
    assert verdicts["completion_date"] == ra.UNKNOWN
    _, contradicted = ra.score(section, face)
    assert not contradicted
    documents, unattached = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


@pytest.mark.parametrize("written", ["N/A", "n/a", "N.A.", "none", "None",
                                     "---", "unknown", "NIL"])
def test_the_non_value_list_is_declared_and_not_a_similarity_judgement(written):
    assert ra.normalise("completion_date", written) is None
    assert ra.normalise("lease_name", written) is None


def test_a_real_value_that_merely_contains_a_non_value_word_survives():
    """"None" is a non-value. "Nonesuch Lease" is a lease."""
    assert ra.normalise("lease_name", "Nonesuch Lease") is not None
    assert ra.normalise("operator_name", "Nations Energy") is not None


# --------------------------------------------------------------- DEFECTS #37

def test_a_mislabelled_face_attaches_to_a_richer_face():
    """Record 1495193: page 8 is a section, the census called it a `g1` face,
    and the module offered only non-faces as candidates so it could never
    attach. The classifier is right about faces 44% of the time."""
    face = page(7, "face", operator_name="U. S. Resources, Inc.",
                lease_name="Debbie", well_number="1", rrc_district="03")
    mislabelled = page(8, "face", form_class="g1",
                       operator_name="U. S. Resources, Inc.",
                       lease_name="Debbie")
    documents, unattached = ra.group([face, mislabelled])
    assert len(documents) == 1
    assert documents[0].face.page == 7
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


def test_the_richer_of_a_mirrored_pair_is_the_parent():
    """Each wants the other. The page carrying more identity fields is the
    real face; a mislabelled section carries less."""
    rich = page(11, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130", well_number="1",
                completion_date="9-22-77", rrc_district="03")
    poor = page(9, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130")
    documents, _ = ra.group([rich, poor])
    assert len(documents) == 1
    assert documents[0].face.page == 11
    assert [p.page for p in documents[0].pages] == [9, 11]


def test_a_richness_tie_falls_back_to_page_order():
    first = page(9, "face", **SUN)
    second = page(11, "face", **SUN)
    documents, _ = ra.group([first, second])
    assert len(documents) == 1 and documents[0].face.page == 9


def test_a_face_that_becomes_a_child_holds_no_children_of_its_own():
    """Documents stay flat. A chain would make the face of a document
    ambiguous, which is what the ranking exists to prevent."""
    rich = page(1, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130", well_number="1",
                completion_date="9-22-77", rrc_district="03")
    middle = page(2, "face", operator_name="Sun Oil Company",
                  lease_name="State Tract 130", well_number="1")
    poor = page(3, "sec_ii", operator_name="Sun Oil Company",
                lease_name="State Tract 130")
    documents, _ = ra.group([rich, middle, poor])
    assert len(documents) == 1
    assert documents[0].face.page == 1
    assert [p.page for p in documents[0].pages] == [1, 2, 3]


def test_two_genuine_faces_that_agree_on_nothing_stay_two_documents():
    documents, unattached = ra.group([page(7, "face", **SUN),
                                      page(20, "face", **GULF)])
    assert sorted(d.face.page for d in documents) == [7, 20]
    assert all(len(d.pages) == 1 for d in documents)
    assert not unattached
