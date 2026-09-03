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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

#: The fields both a face and its section can carry, and any of which can
#: reject a pair by disagreeing.
IDENTITY_FIELDS = ("operator_name", "lease_name", "well_number",
                   "completion_date", "rrc_district")

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
    if not text:
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

    @property
    def file_key(self) -> tuple[str, int]:
        return (self.record_id, self.file_index)

    @property
    def is_face(self) -> bool:
        return self.form_class in ("w2", "g1") and self.part == "face"

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


def compare(a: PageRecord, b: PageRecord) -> dict[str, str]:
    """Field by field: agrees, disagrees, or unknown."""
    out = {}
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
    agreements = sum(1 for v in verdicts.values() if v is AGREES
                     or v == AGREES)
    contradicted = any(verdicts[f] == DISAGREES for f in IDENTITY_FIELDS)
    return agreements, contradicted


def agreeing_fields(a: PageRecord, b: PageRecord) -> tuple[str, ...]:
    return tuple(f for f, v in compare(a, b).items() if v == AGREES)


def group(pages, min_agreements: int = MIN_AGREEMENTS):
    """Group one file's pages into documents, and say what was left over.

    Takes the pages of a single file. Mixing files is a caller error and is
    refused rather than silently producing cross-file documents.
    """
    pages = list(pages)
    keys = {p.file_key for p in pages}
    if len(keys) > 1:
        raise ValueError(
            f"group() takes the pages of one file, got {sorted(keys)}")

    faces = [p for p in pages if p.is_face]
    candidates = [p for p in pages if p.is_candidate and not p.is_face]
    attached: dict[int, list[tuple[PageRecord, tuple[str, ...]]]] = {
        id(f): [] for f in faces}
    unattached: list[Unattached] = []

    for candidate in candidates:
        if not faces:
            unattached.append(Unattached(candidate, "no_face"))
            continue
        eligible, contradicted_any = [], False
        for face in faces:
            agreements, contradicted = score(candidate, face)
            if contradicted:
                contradicted_any = True
                continue
            if agreements >= min_agreements:
                eligible.append((agreements, face))
        if not eligible:
            unattached.append(Unattached(
                candidate,
                "contradicted" if contradicted_any else "below_threshold"))
            continue
        best = max(a for a, _ in eligible)
        winners = [f for a, f in eligible if a == best]
        if len(winners) > 1:
            unattached.append(Unattached(candidate, "tie"))
            continue
        attached[id(winners[0])].append(
            (candidate, agreeing_fields(candidate, winners[0])))

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
