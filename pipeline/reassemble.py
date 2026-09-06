#!/usr/bin/env python3
"""Group the pages of one completion report, so extraction gets a document.

Pure domain. No I/O, no model calls, no corpus. Everything here is a function
over page records, so all of it is tier-1 testable.

**Pair in both directions, and settle candidates by agreement on the identity
fields both pages carry, never by position.** Position narrows the candidate
list to one file; agreement decides. The two are not interchangeable and the
order matters.

Why that is the rule rather than a preference, measured on the census: 249
files hold 238 completion faces, and **64 of the 112 files that hold a face
hold more than one**. One file holds fifteen. So "which report does this page
belong to" is the ordinary case, and nothing based on nearness can answer it.
DEFECTS #25 is the same finding from the other end: a forward-only
placeholder produced three broken documents out of fifteen.

Four rules are enforced here rather than asked for.

  Comparison is exact after normalising, never fuzzy. The corpus already
  carries operator names inside lease names, and a fuzzy match that quietly
  pairs two different wells is the one failure this module must never make.
  Cross-document name drift is the disagreement detector's problem, not
  this module's.

  A contradiction rejects a pair outright, whatever else agrees. Two pages
  naming different operators are not one document and no amount of other
  evidence outvotes that.

  A tie attaches to nothing. Breaking it by nearness would smuggle position
  back in as the decider.

  Candidates never cross a file boundary. A record can hold five files and
  page 3 of one has nothing to do with page 3 of another (DEFECTS #28).

  A page the classifier calls a face may still be somebody's child, but only
  when its own values came out of back-page boxes. Stage 2 measured face
  precision at 44%, so the label cannot be taken as fact (DEFECTS #37); but
  allowing every face to be a child let two filings for one well become one
  document, four times out of four in the verification sitting (DEFECTS #44).
  The reader's own report of which printed box each value came from is what
  separates the two cases, and it is read as text: the same box is numbered
  24 on a G-1 and 31 or 32 on a W-2 (DEFECTS #59).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

#: The fields both a face and its section can carry, and any of which can
#: reject a pair by disagreeing.
IDENTITY_FIELDS = ("operator_name", "lease_name", "well_number",
                   "completion_date", "rrc_district", "purpose_of_filing")

#: Carried by some sections and useful as corroboration, but never able to
#: reject a pair: a face and its section can legitimately disagree when one
#: of them carries a correction.
BONUS_FIELDS = ("total_depth",)

#: Agreements needed to attach. One is ordinary coincidence: every well on a
#: lease shares a lease name and well numbers repeat across leases. Two
#: independent agreements is where coincidence starts to be unlikely.
#: Pre-registered at two and measured against the ground truth before the
#: semantics are called settled.
MIN_AGREEMENTS = 2

AGREES, DISAGREES, UNKNOWN = "agrees", "disagrees", "unknown"

#: Printed boxes that only a completion report's FIRST page carries. A page
#: citing these is a real face and may never become somebody's child.
FACE_BOXES = ("lease name", "operator's name", "well no", "well number",
              "rrc district", "field name")

#: Printed boxes that only a back or section page carries. A page citing these
#: is a back page whatever the classifier called it. Matched as text, never by
#: field number: the location box is 24 on a G-1 and 31 or 32 on a W-2, so a
#: number-keyed rule would be family-specific (DEFECTS #59).
BACK_BOXES = ("notice of intention", "location of well", "location of the well",
              "total depth", "casing record", "data on well completion")

#: The section heading names the form family, and it is the form design rather
#: than a correlation: a G-1 carries Sections I and II on its face and Section
#: III on the back; a W-2 carries Section I on the face and Section II on the
#: back. Measured across 55 read pages with **no crossover** (DEFECTS #60).
#:
#: Alex found this by asking whether a W-2 back page ever starts with Section
#: III. It does not. The classifier had been reading the heading correctly into
#: `part` and then contradicting it in `form_class` on 31 of 65 such pages.
SECTION_FAMILY = {"sec_ii": "w2", "sec_iii": "g1"}

#: The printed field number on a back page also names the family. G-1 numbers
#: Notice of Intention 19 and Location of Well 24; W-2 numbers them 26 and
#: 31 or 32, the 31/32 split being the revision difference inside W-2
#: (DEFECTS #59, which corrects a claim this repo asserted in seven places).
#:
#: **Total Depth is deliberately absent.** Ten of the eleven field numbers
#: found outside the known sets across 528 read pages were Total Depth boxes,
#: because many other forms carry one. Dropping it costs no coverage on any
#: page measured.
BACK_BOX_FAMILY = {("notice", 19): "g1", ("notice", 26): "w2",
                   ("location", 24): "g1", ("location", 31): "w2",
                   ("location", 32): "w2"}

_BACK_BOX_KEYS = (("notice of intention", "notice"),
                  ("location of well", "location"),
                  ("location of the well", "location"))

_LEADING_NUMBER = re.compile(r"^\s*(\d{1,2})\s*[.\s]")


#: Things an operator writes to mean "there is no value here". A page that
#: declines to answer is silent, not in disagreement, and letting it
#: contradict lets it veto a true pairing (DEFECTS #39). Declared and listed:
#: the whole field must be one of these, so "Nonesuch Lease" is a lease.
NON_VALUES = frozenset({"na", "n", "none", "nil", "notapplicable", "unknown",
                        "blank", "nonvalue", "no", "0"})

#: Months, for the received stamp. It is stamped rather than printed, so it
#: arrives as "AUG 18 2009", "JUN 09 2009" or "MAR 1990" with no day at all.
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

_ALNUM = re.compile(r"[^0-9a-z]")
_DATE = re.compile(r"(\d{1,4})\D+(\d{1,2})\D+(\d{1,4})")


def normalise(field: str, value: str | None) -> str | None:
    """Field-aware normalisation. Declared per field, and nothing else.

    This is the whole of what "exact after normalising" is allowed to do.
    Anything that would let two different strings compare equal on a
    similarity judgement rather than on a stated transformation belongs in
    the disagreement detector.
    """
    if value is None:
        return None
    text = _ALNUM.sub("", value.casefold())
    if not text or text in NON_VALUES:
        return None
    if field == "rrc_district":
        # "03" and "3" are one district. Districts are numeric on every form.
        return text.lstrip("0") or "0"
    if field == "completion_date":
        # A two-digit and a four-digit year are one date. Reduced to
        # month/day/year-mod-100 rather than parsed, because the point is
        # comparability between two pages, not a calendar.
        match = _DATE.search(value)
        if match:
            a, b, c = (int(part) for part in match.groups())
            return f"{a % 100}-{b % 100}-{c % 100}"
        return text
    if field == "received_office":
        return text or None
    if field == "received_date":
        # Compared at month and year only, which is the precision BOTH sides
        # reliably carry. Measured on the four-page probe: two stamps came
        # back as a full date and two as month and year, and comparing
        # "aug182009" against "aug2009" would be a false disagreement, which
        # on a veto field means refusing a pair that belongs together.
        low = value.casefold()
        month = next((n for m, n in _MONTHS.items() if m in low), None)
        year = re.search(r"(19|20)\d{2}", value)
        if month and year:
            return f"{month}-{year.group(0)}"
        digits = re.findall(r"\d+", value)
        return "-".join(digits[-2:]) if len(digits) >= 2 else None
    if field == "total_depth":
        digits = re.sub(r"\D", "", value)
        return digits.lstrip("0") or None if digits else None
    return text


@dataclass(frozen=True)
class PageRecord:
    """One page, as the census and the identity reader see it."""

    record_id: str
    file_index: int
    page: int
    form_class: str
    part: str | None = None
    identity: dict[str, str | None] = dc_field(default_factory=dict)

    #: field -> the printed label the reader says the value came from. A
    #: claim by the model about its own reading, not proof (DEFECTS #42), and
    #: the only thing that tells a real face from a mislabelled one.
    sources: dict[str, str | None] = dc_field(default_factory=dict)

    #: (office, date) for every received stamp on the page.
    stamps: tuple[tuple[str, str], ...] = ()

    @property
    def file_key(self) -> tuple[str, int]:
        return (self.record_id, self.file_index)

    @property
    def is_face(self) -> bool:
        return self.form_class in ("w2", "g1") and self.part == "face"

    @property
    def may_be_a_child(self) -> bool:
        """Whether this page is allowed to attach to another.

        A page the classifier calls a section always may: that is what it was
        always for. A page it calls a face may only when the page's own cited
        boxes say it is really a back page. With nothing cited, the answer is
        no, because the safe answer is the one that cannot invent a document.
        """
        if not self.is_face:
            return True
        return looks_like_a_back_page(self.sources)

    @property
    def is_candidate(self) -> bool:
        if self.form_class == "other_form":
            return True
        return (self.form_class in ("w2", "g1")
                and self.part in ("continuation", "sec_ii", "sec_iii"))


@dataclass(frozen=True)
class Document:
    face: PageRecord
    pages: tuple[PageRecord, ...]
    evidence: tuple[tuple[int, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class Unattached:
    page: PageRecord
    #: no_face | below_threshold | tie | contradicted | not_a_candidate
    #: | different_form
    #:
    #: `not_a_candidate` is the module declining to have an opinion: the page
    #: is neither a face nor something that could be a child, so no rule here
    #: ever looked at it. It exists because those pages used to leave the
    #: count without leaving a trace (DEFECTS #49). They are almost all the
    #: printed instruction backs of forms.
    reason: str


def family_of(record) -> str | None:
    """Which form family this page belongs to, or None.

    Three sources, in order of how directly they read the paper:

      the section heading the classifier recorded in `part`
      the printed field number the reader cited in `sources`
      for a face, the `form_class` the classifier assigned

    A face prints its form number in the corner, which is what the classifier
    reads and where it was measured at 94% precision for G-1. A back page
    usually prints no form number at all, which is why `form_class` is
    untrustworthy there (DEFECTS #37) and why the first two exist.

    **Abstains rather than guessing**, and abstains when the two back-page
    signals disagree. That has never been observed in 55 pages, and if it
    happens the honest answer is that we do not know.
    """
    heading = SECTION_FAMILY.get(record.part)

    votes = set()
    for label in (record.sources or {}).values():
        if not label:
            continue
        match = _LEADING_NUMBER.match(str(label))
        if not match:
            continue
        low = str(label).casefold()
        for needle, box in _BACK_BOX_KEYS:
            if needle in low:
                family = BACK_BOX_FAMILY.get((box, int(match.group(1))))
                if family:
                    votes.add(family)
                break
    numbered = votes.pop() if len(votes) == 1 else None

    if heading and numbered and heading != numbered:
        return None
    if heading or numbered:
        return heading or numbered
    return record.form_class if record.part == "face" else None


def families_conflict(parent, child) -> bool:
    """Two pages of different forms are not one document.

    The check DEFECTS #44 left open, and could not take before, because it was
    keyed to a `form_class` that is wrong on back pages: on the judged data
    that version would have deleted 7 correct attachments to remove 9 wrong.
    Read from the paper instead it keeps 6 of the 7 and removes 5 of the 9.

    Abstention cuts one way only. Not knowing a page's family is never
    evidence that it belongs somewhere else.
    """
    one, two = family_of(parent), family_of(child)
    return bool(one and two and one != two)


def looks_like_a_back_page(sources) -> bool:
    """Do this page's values come out of back-page boxes?

    Read as text rather than by field number, because the same printed box is
    numbered 24 on a G-1 and 31 or 32 on a W-2, so a number-keyed rule
    would need to know the family first (DEFECTS #59). A page citing any face box is a face,
    whatever else it cites: the identity block is the thing only a first page
    has.
    """
    labels = [str(label).casefold() for label in (sources or {}).values()
              if label]
    if any(box in label for label in labels for box in FACE_BOXES):
        return False
    return any(box in label for label in labels for box in BACK_BOXES)


def may_pair(parent: PageRecord, child: PageRecord) -> bool:
    """Whether these two pages could be one document at all.

    One rule, arrived at from three directions in the second verification
    sitting: **two pages are one document only when they are the same form
    family, one is a real face, and the other is not.**

    Every check here is about what a page IS, not about what it says. The
    identity fields describe a well, and every round of this module's history
    has been another way that fails to describe a document: two filings of one
    form, then two sides that are both backs, then two different forms about
    one well (DEFECTS #43, #44, #46).

    **The form-family half of that sentence is NOT implemented, and the reason
    is worth more than the rule would have been.** It would have been keyed to
    the classifier's `form_class`, and the two cases it must separate are
    indistinguishable there. Record 1495193 pages 7 and 8 are `w2` and `g1`
    and are one document, which is DEFECTS #25's pin and the reason this
    module exists. Record 1912687 pages 2 and 8 are `g1` and `w2` and are not.
    A family rule built on that label rejects the pin. `form_class` is
    untrustworthy for exactly the reason `part` is, and #37 was the lesson
    about trusting `part`.

    So the W-2 Section III that attached to a G-1 face stays attached, and is
    recorded as a measured limitation rather than closed with a rule that
    would break something load-bearing.
    """
    if looks_like_a_back_page(parent.sources):
        return False
    if child.part != "face":
        return True
    # The classifier calls the child a face. Only its own cited boxes may
    # overrule that, and they must actually say back page. `is_face` is not
    # the test here: it is gated on form_class, so a page the classifier
    # called the FACE of some other form passed straight through it and a
    # P-4's first page attached to a W-2 (DEFECTS #46).
    return looks_like_a_back_page(child.sources)


def compare_stamps(a, b) -> str:
    """Received stamps, compared office by office.

    A page carries several stamps because a filing is stamped by the district
    office and again by Central Records months later. Comparing "the" stamp
    compares whichever one each reading happened to pick, which on record
    1912687 made two pages agree on Houston while a human comparing Austin
    against Houston read them as different filings (DEFECTS #45).

    So only offices BOTH pages name are compared. One page carrying an extra
    stamp says nothing: a Central Records stamp lands on a packet's top page
    and not on the pages behind it, which is a fact about stapling rather than
    about which filing a page belongs to.
    """
    left = {normalise("received_office", o): normalise("received_date", d)
            for o, d in a}
    right = {normalise("received_office", o): normalise("received_date", d)
             for o, d in b}
    shared = {o for o in left if o and o in right and right[o] and left[o]}
    if not shared:
        return UNKNOWN
    if any(left[o] != right[o] for o in shared):
        return DISAGREES
    return AGREES


def compare(a: PageRecord, b: PageRecord) -> dict[str, str]:
    """Field by field: agrees, disagrees, or unknown."""
    out = {"received_stamps": compare_stamps(a.stamps, b.stamps)}
    for field in IDENTITY_FIELDS + BONUS_FIELDS:
        left = normalise(field, a.identity.get(field))
        right = normalise(field, b.identity.get(field))
        if left is None or right is None:
            out[field] = UNKNOWN
        elif left == right:
            out[field] = AGREES
        else:
            out[field] = DISAGREES
    return out


def score(a: PageRecord, b: PageRecord) -> tuple[int, bool]:
    """(fields that agree, whether anything that can reject them does)."""
    verdicts = compare(a, b)
    agreements = sum(1 for v in verdicts.values() if v == AGREES)
    contradicted = any(verdicts[f] == DISAGREES
                       for f in IDENTITY_FIELDS + ("received_stamps",))
    return agreements, contradicted


def agreeing_fields(a: PageRecord, b: PageRecord) -> tuple[str, ...]:
    return tuple(f for f, v in compare(a, b).items() if v == AGREES)


def richness(page: PageRecord) -> int:
    """How many identity fields the page actually carries.

    The parent of a pair is the richer page. A real face carries the identity
    block and a mislabelled section carries less, so this is a measurement of
    the thing the label was supposed to tell us (DEFECTS #37).
    """
    return sum(1 for field in IDENTITY_FIELDS + BONUS_FIELDS
               if normalise(field, page.identity.get(field)) is not None)


def _rank(page: PageRecord) -> tuple[int, int]:
    """Richest first, then earliest. The fallback matters: richness ties, and
    without one the mirrored pairs have no answer."""
    return (-richness(page), page.page)


def group(pages, min_agreements: int = MIN_AGREEMENTS, confirms=None):
    """Group one file's pages into documents, and say what was left over.

    Takes the pages of a single file. Mixing files is a caller error and is
    refused rather than silently producing cross-file documents.

    Faces are resolved in rank order and a face may only become the child of
    a face ranked above it. That makes a mirrored pair impossible by
    construction rather than by a tie-break applied afterwards, and it keeps
    documents flat: a page that becomes a child holds no children of its own,
    so the face of a document is never ambiguous.
    """
    pages = list(pages)
    keys = {p.file_key for p in pages}
    if len(keys) > 1:
        raise ValueError(
            f"group() takes the pages of one file, got {sorted(keys)}")

    ranked_faces = sorted((p for p in pages if p.is_face), key=_rank)
    candidates = [p for p in pages if p.is_candidate and not p.is_face]
    parents: list[PageRecord] = []
    attached: dict[int, list[tuple[PageRecord, tuple[str, ...]]]] = {}

    # Pages this module has no opinion about are named rather than dropped.
    # They used to fall out of the two expressions above and land nowhere, so
    # the run's totals came up twenty short of the pages it had read and paid
    # for (DEFECTS #49). Declining to judge a page is a result; losing it is
    # not.
    unattached: list[Unattached] = [
        Unattached(p, "not_a_candidate")
        for p in pages if not p.is_face and not p.is_candidate]

    def place(candidate, pool):
        """Attach to the one eligible parent, or say why not.

        Two kinds of evidence, and they do different jobs. Identity fields
        describe the WELL, and a file holds several filings for one well, so
        their agreement is guaranteed and can only ever exclude. `confirms`
        carries evidence about the SHEET — the marks on the paper — which is
        the only thing that can confirm. Measured 2026-09-06 on 16 pairs Alex
        judged one sheet: identity attached none of them and the paper
        confirmed four.

        The identity veto is kept over a confirmation, deliberately (his
        ruling of 2026-09-05): a contradiction means the reader got a field
        wrong on one of the pages, and refusing is the safe reading.
        """
        pool = [f for f in pool if may_pair(f, candidate)]
        if not pool:
            return "no_face"
        eligible, contradicted_any, different_form = [], False, False
        for face in pool:
            if not may_pair(face, candidate):
                continue
            if families_conflict(face, candidate):
                different_form = True
                continue
            agreements, contradicted = score(candidate, face)
            if contradicted:
                contradicted_any = True
                continue
            confirmed = bool(confirms and confirms(face, candidate))
            if confirmed or agreements >= min_agreements:
                eligible.append(((1 if confirmed else 0, agreements), face))
        if not eligible:
            if contradicted_any:
                return "contradicted"
            return "different_form" if different_form else "below_threshold"
        # Paper first, then field agreement: physical evidence about this
        # sheet outranks agreement about this well.
        best = max(a for a, _ in eligible)
        winners = [f for a, f in eligible if a == best]
        if len(winners) > 1:
            return "tie"
        attached[id(winners[0])].append(
            (candidate, agreeing_fields(candidate, winners[0])))
        return None

    # Faces first, in rank order, so a face can only fall to a richer one.
    for face in ranked_faces:
        if not face.may_be_a_child:
            parents.append(face)
            attached[id(face)] = []
            continue
        reason = place(face, parents) if parents else "no_face"
        if reason is None:
            continue
        parents.append(face)
        attached[id(face)] = []

    for candidate in candidates:
        reason = place(candidate, parents)
        if reason is not None:
            unattached.append(Unattached(candidate, reason))

    faces = parents
    documents = []
    for face in faces:
        joined = attached[id(face)]
        ordered = tuple(sorted([face] + [p for p, _ in joined],
                               key=lambda p: p.page))
        documents.append(Document(
            face=face, pages=ordered,
            evidence=tuple((p.page, fields) for p, fields in joined)))
    return documents, unattached


def contradicted_but_agreeing(pages, min_agreements: int = MIN_AGREEMENTS):
    """Pairs the veto rejected while at least `min_agreements` others agreed.

    Requested before the semantics are called settled. Every row is either
    the veto doing its job, or two pages of one document split apart by an
    abbreviation that a typist wrote differently. Those look identical from
    here and only reading the paper separates them, so this is output for a
    human rather than a number.
    """
    out = []
    for candidate in (p for p in pages if p.is_candidate and not p.is_face):
        for face in (p for p in pages if p.is_face):
            verdicts = compare(candidate, face)
            disagreed = tuple(f for f in IDENTITY_FIELDS
                              if verdicts[f] == DISAGREES)
            agreed = tuple(f for f, v in verdicts.items() if v == AGREES)
            if disagreed and len(agreed) >= min_agreements:
                out.append((candidate, face, disagreed, agreed))
    return out
