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
  24, 31 and 32 on three revisions of this form.
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
#: field number: the location box is 24, 31 and 32 on three revisions.
BACK_BOXES = ("notice of intention", "location of well", "location of the well",
              "total depth", "casing record", "data on well completion")

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
    reason: str          # no_face | below_threshold | tie | contradicted


def looks_like_a_back_page(sources) -> bool:
    """Do this page's values come out of back-page boxes?

    Read as text rather than by field number, because the same printed box is
    numbered 24, 31 and 32 on three revisions and a number-keyed rule is
    silently wrong on two of them. A page citing any face box is a face,
    whatever else it cites: the identity block is the thing only a first page
    has.
    """
    labels = [str(label).casefold() for label in (sources or {}).values()
              if label]
    if any(box in label for label in labels for box in FACE_BOXES):
        return False
    return any(box in label for label in labels for box in BACK_BOXES)


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


def group(pages, min_agreements: int = MIN_AGREEMENTS):
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
    unattached: list[Unattached] = []

    def place(candidate, pool):
        """Attach to the one eligible parent, or say why not."""
        if not pool:
            return "no_face"
        eligible, contradicted_any = [], False
        for face in pool:
            agreements, contradicted = score(candidate, face)
            if contradicted:
                contradicted_any = True
                continue
            if agreements >= min_agreements:
                eligible.append((agreements, face))
        if not eligible:
            return "contradicted" if contradicted_any else "below_threshold"
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
