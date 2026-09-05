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


#: The printed boxes a real first page cites, and the ones a back page cites.
#: DEFECTS #44: this is what separates a mislabelled face from a real one.
FACE_BOXES = {"lease_name": "2. LEASE NAME",
              "operator_name": "3. OPERATOR'S NAME"}
BACK_BOXES = {"operator_name": "26. Notice of Intention to Drill this Well "
                               "was filed in Name of",
              "lease_name": "32. Location of Well, Relative to Lease "
                            "Boundaries"}


def page(number, part=None, form_class="w2", record="1495193", file_index=0,
         sources=None, **identity):
    return ra.PageRecord(record_id=record, file_index=file_index,
                         page=number, form_class=form_class, part=part,
                         identity=identity, sources=sources or {})


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
    """Breaking it by nearness would put position back in as the decider.

    The two faces have to contradict each other, or DEFECTS #37's change
    merges them into one document and there is no tie left to test. Here they
    are two wells on one lease, which is what the veto is for.
    """
    first = page(7, "face", operator_name="Sun Oil Company",
                 lease_name="State Tract 130", well_number="1")
    second = page(20, "face", operator_name="Sun Oil Company",
                  lease_name="State Tract 130", well_number="2")
    section = page(8, "sec_ii", operator_name="Sun Oil Company",
                   lease_name="State Tract 130")
    documents, unattached = ra.group([first, second, section])
    assert sorted(d.face.page for d in documents) == [7, 20]
    assert all(len(d.pages) == 1 for d in documents)
    assert unattached[0].reason == "tie"


def test_a_unique_best_score_still_wins():
    """Same shape, but the section carries the well number, so one face wins
    outright and the other is contradicted rather than merely weaker."""
    strong = page(7, "face", operator_name="Sun Oil Company",
                  lease_name="State Tract 130", well_number="1",
                  completion_date="9-22-77")
    other = page(20, "face", operator_name="Sun Oil Company",
                 lease_name="State Tract 130", well_number="2")
    section = page(8, "sec_ii", operator_name="Sun Oil Company",
                   lease_name="State Tract 130", well_number="1",
                   completion_date="9-22-77")
    documents, unattached = ra.group([strong, other, section])
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
    mislabelled = page(8, "face", form_class="g1", sources=BACK_BOXES,
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
    poor = page(9, "face", sources=BACK_BOXES,
                operator_name="Sun Oil Company",
                lease_name="State Tract 130")
    documents, _ = ra.group([rich, poor])
    assert len(documents) == 1
    assert documents[0].face.page == 11
    assert [p.page for p in documents[0].pages] == [9, 11]


def test_two_back_like_faces_no_longer_reach_the_richness_tie_break():
    """The tie-break by page order is unreachable for this case now: neither
    page may be a parent, so there is nothing to rank (DEFECTS #46). Kept
    because the fixture used to produce one document and now produces two."""
    first = page(9, "face", sources=BACK_BOXES, **SUN)
    second = page(11, "face", sources=BACK_BOXES, **SUN)
    documents, _ = ra.group([first, second])
    assert sorted(d.face.page for d in documents) == [9, 11]


def test_a_face_that_becomes_a_child_holds_no_children_of_its_own():
    """Documents stay flat. A chain would make the face of a document
    ambiguous, which is what the ranking exists to prevent."""
    rich = page(1, "face", operator_name="Sun Oil Company",
                lease_name="State Tract 130", well_number="1",
                completion_date="9-22-77", rrc_district="03")
    middle = page(2, "face", sources=BACK_BOXES,
                  operator_name="Sun Oil Company",
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


# --------------------------------------------------------------- DEFECTS #44

FACE_SOURCES = {"operator_name": "3. OPERATOR'S NAME (Exactly as shown on P-5)",
                "lease_name": "2. LEASE NAME",
                "well_number": "9. Well No."}
BACK_SOURCES = {"operator_name": "26. Notice of Intention to Drill this Well "
                                 "was filed in Name of",
                "lease_name": "32. Location of Well, Relative to Lease "
                              "Boundaries"}


def sourced(number, part=None, form_class="w2", sources=None, **identity):
    return ra.PageRecord(record_id="1495195", file_index=0, page=number,
                         form_class=form_class, part=part,
                         identity=identity, sources=sources or {})


def test_a_real_face_may_not_become_a_child():
    """The sitting: every join of two real first-pages is wrong, four of four.
    Two filings for one well agree on everything, because it is one well."""
    initial = sourced(52, "face", sources=FACE_SOURCES, **SUN)
    retest = sourced(87, "face", sources=FACE_SOURCES, **SUN)
    documents, unattached = ra.group([initial, retest])
    assert sorted(d.face.page for d in documents) == [52, 87]
    assert all(len(d.pages) == 1 for d in documents)


def test_a_mislabelled_face_may_still_become_a_child():
    """The other half, and DEFECTS #37's pin. Record 1495193 page 8 is a
    section the census called a face, and its own cited boxes say so."""
    face = sourced(7, "face", sources=FACE_SOURCES, well_number="1", **SUN)
    section = sourced(8, "face", form_class="g1", sources=BACK_SOURCES, **SUN)
    documents, unattached = ra.group([face, section])
    assert len(documents) == 1
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


def test_a_page_the_classifier_calls_a_section_is_unaffected():
    """The rule is about faces. A section was always a candidate and stays
    one, whatever its cited boxes say, including none at all."""
    face = sourced(7, "face", sources=FACE_SOURCES, **SUN)
    section = sourced(8, "sec_ii", sources={}, **SUN)
    documents, _ = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]


def test_a_face_with_no_recorded_sources_may_not_become_a_child():
    """Abstention. With nothing to say it is really a back page, the safe
    answer is the one that cannot invent a document."""
    face = sourced(7, "face", sources=FACE_SOURCES, **SUN)
    unknown = sourced(8, "face", sources={}, **SUN)
    documents, _ = ra.group([face, unknown])
    assert sorted(d.face.page for d in documents) == [7, 8]


def test_the_face_test_reads_the_label_text_not_its_number():
    """The same printed box is 24, 31 and 32 on three revisions, so a
    number-keyed rule is silently wrong on two of them."""
    for label in ("24. Location of well, relative to nearest lease boundary",
                  "31. Location of Well, Relative to Nearest Lease Boundaries",
                  "32. Location of Well, Relative to Lease Boundaries"):
        assert ra.looks_like_a_back_page({"lease_name": label}), label
    assert not ra.looks_like_a_back_page({"lease_name": "2. LEASE NAME"})


# ---------------------------------------------- the two fields Alex used

def test_two_filings_for_one_well_are_not_one_document():
    """DEFECTS #43's pin. Everything an initial potential test and a retest
    share, they share because it is one well. The purpose is what differs."""
    initial = page(52, "face", sources=BACK_BOXES, **SUN,
                   purpose_of_filing="Initial Potential")
    retest = page(87, "face", sources=BACK_BOXES, **SUN,
                  purpose_of_filing="Retest")
    verdicts = ra.compare(retest, initial)
    assert verdicts["purpose_of_filing"] == ra.DISAGREES
    _, contradicted = ra.score(retest, initial)
    assert contradicted
    # A face that does not attach becomes its own document rather than an
    # unattached page: nothing is lost, there are simply two reports.
    documents, unattached = ra.group([initial, retest])
    assert sorted(d.face.page for d in documents) == [52, 87]
    assert all(len(d.pages) == 1 for d in documents)
    assert not unattached


def stamped(number, part=None, form_class="w2", sources=None, stamps=(),
            **identity):
    return ra.PageRecord(record_id="1912687", file_index=0, page=number,
                         form_class=form_class, part=part,
                         identity=identity, sources=sources or {},
                         stamps=stamps)


def test_a_back_page_carries_no_purpose_so_it_cannot_veto():
    """Purpose is printed on the face. A section says not_on_this_form, which
    compares as unknown and cannot reject a true pair."""
    face = page(7, "face", sources=FACE_BOXES, **SUN,
                purpose_of_filing="Initial Potential")
    section = page(8, "sec_ii", sources=BACK_BOXES, **SUN)
    assert ra.compare(section, face)["purpose_of_filing"] == ra.UNKNOWN
    documents, unattached = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


# --------------------------------------------------------------- DEFECTS #45

def test_stamps_are_compared_office_by_office():
    """Record 1912687 page 2 carries BOTH a Houston stamp from June and a
    Central Records Austin stamp from August. Page 6 carries only the Houston
    one. Comparing "the" stamp compares whichever each reading picked."""
    p2 = stamped(2, "face", stamps=(("Houston", "JUN 09 2009"),
                                    ("Central Records", "AUG 18 2009")))
    p6 = stamped(6, "face", stamps=(("Houston", "JUN 09 2009"),))
    assert ra.compare_stamps(p2.stamps, p6.stamps) == ra.AGREES


def test_an_office_only_one_page_names_says_nothing():
    """A Central Records stamp lands on a packet's top page and not on the
    pages behind it. That is a fact about stapling, not about filings."""
    top = stamped(2, "face", stamps=(("Houston", "JUN 09 2009"),
                                     ("Central Records", "AUG 18 2009")))
    behind = stamped(6, "face", stamps=(("Houston", "JUN 09 2009"),))
    assert ra.compare_stamps(top.stamps, behind.stamps) == ra.AGREES
    none = stamped(9, "face", stamps=())
    assert ra.compare_stamps(top.stamps, none.stamps) == ra.UNKNOWN


def test_one_office_with_two_dates_rejects_the_pair():
    """The real signal: the same office received these on different days, so
    they are different filings."""
    a = stamped(52, "face", stamps=(("Houston", "JUN 09 2009"),))
    b = stamped(87, "face", stamps=(("Houston", "AUG 18 2009"),))
    assert ra.compare_stamps(a.stamps, b.stamps) == ra.DISAGREES
    _, contradicted = ra.score(b, a)
    assert contradicted


def test_stamps_are_compared_at_month_and_year():
    """Measured on the probe: some stamps read as a full date and some as
    month and year only. Comparing those as strings would be a false
    disagreement, which on a veto field refuses a pair that belongs."""
    assert ra.normalise("received_date", "AUG 18 2009") == "8-2009"
    assert ra.normalise("received_date", "MAR 1990") == "3-1990"
    # pinned rather than hidden: two filings stamped in one month look alike
    assert (ra.normalise("received_date", "MAR 05 1990")
            == ra.normalise("received_date", "MAR 27 1990"))


def test_office_names_are_compared_after_normalising():
    assert (ra.normalise("received_office", "Houston")
            == ra.normalise("received_office", "HOUSTON,"))
    assert (ra.normalise("received_office", "Central Records")
            != ra.normalise("received_office", "Houston"))


def test_the_reader_and_reassembly_still_agree_on_the_field_list():
    from pipeline.identity import FIELDS
    assert set(FIELDS) == set(ra.IDENTITY_FIELDS) | set(ra.BONUS_FIELDS)


# --------------------------------------------------------------- DEFECTS #46

def classed(number, form_class, part, sources, **identity):
    return ra.PageRecord(record_id="x", file_index=0, page=number,
                         form_class=form_class, part=part,
                         identity=identity, sources=sources)


def test_a_back_page_may_not_be_a_parent():
    """Second sitting: 1495195 p88+p53 and 1511465 p8+p10, both judged wrong
    with the note "both are back sides". #44 stopped a real face becoming a
    child and never asked the same question in the other direction."""
    parent = classed(53, "w2", "face", BACK_BOXES, **SUN)
    child = classed(88, "w2", "continuation", BACK_BOXES, **SUN)
    documents, unattached = ra.group([parent, child])
    assert all(len(d.pages) == 1 for d in documents)
    assert unattached and unattached[0].reason == "no_face"


def test_a_child_crossing_form_families_is_a_known_limitation():
    """1912687 p8+p2: a W-2 Section III attached to a G-1 face, judged wrong,
    and NOT fixed. Pinned as a limitation rather than closed.

    A family rule would be keyed to the classifier's form_class, and the two
    cases it must separate are indistinguishable there: 1495193 pages 7 and 8
    are also w2 and g1 and ARE one document, which is DEFECTS #25's pin. The
    rule that closes this failure breaks the reason the module exists.
    """
    g1_face = classed(2, "g1", "face", FACE_BOXES, **SUN)
    w2_back = classed(8, "w2", "sec_iii", BACK_BOXES, **SUN)
    documents, _ = ra.group([g1_face, w2_back])
    assert [p.page for p in documents[0].pages] == [2, 8], (
        "this attaches, and that is the recorded limitation")


def test_the_pin_survives_the_rule_that_would_have_closed_that_limitation():
    """The other side of it. Record 1495193 pages 7 and 8 are w2 and g1 by
    the census and are one document off the paper."""
    face = classed(7, "w2", "face", FACE_BOXES, **SUN)
    section = classed(8, "g1", "face", BACK_BOXES, **SUN)
    documents, unattached = ra.group([face, section])
    assert [p.page for p in documents[0].pages] == [7, 8]
    assert not unattached


def test_a_page_of_another_form_may_not_attach():
    """1494690 p3+p7 and 1760703 p24+p6: the face of a P-4 attached to a
    completion report that shares its operator, lease, district and even its
    received stamp, because they are about the same well."""
    face = classed(7, "w2", "face", FACE_BOXES, **SUN)
    other = classed(3, "other_form", "face", FACE_BOXES, **SUN)
    documents, _ = ra.group([face, other])
    assert [p.page for p in documents[0].pages] == [7]

    # and the harder one: a page whose cited boxes say nothing recognisable.
    # 1760703 p24 cited only "COMPANY". is_face would have let it through
    # because other_form is not a completion class.
    vague = classed(24, "other_form", "face", {"operator_name": "COMPANY"},
                    **SUN)
    documents, _ = ra.group([face, vague])
    assert [p.page for p in documents[0].pages] == [7]


def test_the_two_pairs_the_sitting_verified_still_attach():
    """1495195 p6+p5 and 1504957 p7+p6. A rule that rejects everything is not
    a fix, and this is the regression that says so."""
    for parent_class, child_class, child_part in (("w2", "w2", "face"),
                                                  ("w2", "w2", "continuation")):
        parent = classed(5, parent_class, "face", FACE_BOXES, **SUN)
        child = classed(6, child_class, child_part, BACK_BOXES, **SUN)
        documents, unattached = ra.group([parent, child])
        assert [p.page for p in documents[0].pages] == [5, 6]
        assert not unattached


def test_a_document_is_a_real_face_plus_pages_that_are_not():
    """The whole rule in one assertion, since it is one rule and not three."""
    assert ra.may_pair(
        classed(5, "w2", "face", FACE_BOXES),
        classed(6, "w2", "continuation", BACK_BOXES))
    assert not ra.may_pair(                       # parent is a back page
        classed(5, "w2", "face", BACK_BOXES),
        classed(6, "w2", "continuation", BACK_BOXES))
    assert not ra.may_pair(                       # child is a real face
        classed(5, "w2", "face", FACE_BOXES),
        classed(6, "w2", "face", FACE_BOXES))
    # The family half is deliberately absent; see the limitation test above.
    assert ra.may_pair(
        classed(5, "g1", "face", FACE_BOXES),
        classed(6, "w2", "sec_iii", BACK_BOXES))
