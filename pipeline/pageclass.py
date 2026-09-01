#!/usr/bin/env python3
"""Page-class domain for the RRC classifier: types, guards, ids, census.

Pure. No I/O, no network, no model calls. Everything here is tier-1 testable,
which is the point: the rules that matter are cheap to check and cannot be
skipped by a slow test nobody runs.

Two orthogonal axes describe a page. `form_class` says which form family it
belongs to; `part` says which page of that form it is. They are separate
because a completion report is not contiguous in the file: in record 1501720
the G-1 face is page 2 and its Section III is page 5, with a P-4 between.
Flattening the two into one label would have to re-encode the section axis
for every form family that has sections.

Two defects are enforced here as constructor invariants rather than as prose
in docs/modules:
  DEFECTS #1  an oversize page is never extraction-eligible.
  DEFECTS #2  document counts and record counts are different numbers, and
              the census does not derive a permit count from either.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import Enum


# ------------------------------------------------------------------- vocabulary

class PageClass(str, Enum):
    # Tier A. Extraction targets: full schema, Sonnet.
    G1 = "g1"                                # gas well completion report
    W2 = "w2"                                # oil well completion report

    # A completion report face we decline to name, and one whose name is
    # older than the numbering. Both are abstentions rather than guesses.
    # Origin: the stage-2 measurement and DEFECTS #17.
    COMPLETION_FACE_UNKNOWN_FORM = "completion_face_unknown_form"
    COMPLETION_FACE_LEGACY = "completion_face_legacy"

    # Tier B. Identity-bearing: identity fields only, cross-form disagreement.
    W1 = "w1"                                # drilling permit application
    W3 = "w3"                                # plugging record
    P4 = "p4"                                # producer's transporter auth
    P5 = "p5"                                # operator organization report
    P12 = "p12"                              # certificate of pooling authority
    P15 = "p15"                              # statement of productivity of acreage
    G5 = "g5"                                # gas well classification
    G6 = "g6"                                # exception to statewide rules 28/32
    GT1 = "gt1"                              # gas tax / gatherer's report
    L1 = "l1"                                # gas gathering and load report
    W12 = "w12"                              # directional survey / inclination
    W15 = "w15"                              # cementing report
    P17 = "p17"                              # permit application
    W4_FAMILY = "w4_family"                  # W-4 / W-4A / W-5 / W-6
    WS1_SW1 = "ws1_sw1"                      # pre-1970 form families

    # Tier C. Census only: never extracted.
    LETTER_MEMO = "letter_memo"
    PLAT_MAP = "plat_map"
    SCHEMATIC = "schematic"
    SEPARATOR_CARD = "separator_card"        # ID / separator / X-reference cards
    BLANK_OR_ARTIFACT = "blank_or_artifact"
    OTHER_FORM = "other_form"                # an RRC form not enumerated above
    OTHER_NONFORM = "other_nonform"          # not a form at all


#: The two completion reports we can name from a printed form number.
EXTRACTION_TARGETS = frozenset({PageClass.G1, PageClass.W2})

#: Every class meaning "this page is the face of a completion report".
#:
#: The census headline is a union over this set, which is why abstaining costs
#: nothing at the record level: a page moves between members of the union and
#: never out of it. 115 of 202 records was measured over G1 and W2 alone, and
#: the two abstention classes only take pages that were already being counted
#: as one of those, wrongly.
COMPLETION_FACES = EXTRACTION_TARGETS | frozenset({
    PageClass.COMPLETION_FACE_UNKNOWN_FORM,
    PageClass.COMPLETION_FACE_LEGACY,
})

IDENTITY_BEARING = frozenset({
    PageClass.W1, PageClass.W3, PageClass.P4, PageClass.P5, PageClass.P12,
    PageClass.P15, PageClass.G5, PageClass.G6, PageClass.GT1, PageClass.L1,
    PageClass.W12, PageClass.W15, PageClass.P17, PageClass.W4_FAMILY,
    PageClass.WS1_SW1,
})

#: One line per class, for the classifier prompt and the labelling protocol.
#: A bare token like "l1" tells a model nothing; the form's actual name does.
GLOSS = {
    PageClass.G1: "Form G-1, gas well completion or recompletion report",
    PageClass.W2: "Form W-2, oil well completion or recompletion report",
    PageClass.COMPLETION_FACE_UNKNOWN_FORM:
        "the face of a completion report whose printed form number you cannot "
        "read. Use this instead of guessing between G-1 and W-2",
    PageClass.COMPLETION_FACE_LEGACY:
        "the face of a completion report printed before the G-1 and W-2 "
        "numbering: Form 2, Form 3, GWT-1",
    PageClass.W1: "Form W-1, application for permit to drill",
    PageClass.W3: "Form W-3, plugging record",
    PageClass.P4: "Form P-4, producer's transportation authority",
    PageClass.P5: "Form P-5, operator organization report",
    PageClass.P12: "Form P-12, certificate of pooling authority",
    PageClass.P15: "Form P-15, statement of productivity of acreage assigned "
                   "to proration units",
    PageClass.G5: "Form G-5, gas well classification report",
    PageClass.G6: "Form G-6, application for exception to statewide rules "
                  "28 and/or 32",
    PageClass.GT1: "Form GT-1, gas gatherer or tax report",
    PageClass.L1: "Form L-1, gas gathering and load report",
    PageClass.W12: "Form W-12, directional survey or record of inclination",
    PageClass.W15: "Form W-15, cementing report",
    PageClass.P17: "Form P-17, permit application",
    PageClass.W4_FAMILY: "Form W-4, W-4A, W-5 or W-6",
    PageClass.WS1_SW1: "Form WS-1 well status report, or Form SW-1",
    PageClass.LETTER_MEMO: "a letter, memo or printed email",
    PageClass.PLAT_MAP: "a survey plat or map",
    PageClass.SCHEMATIC: "a wellbore diagram",
    PageClass.SEPARATOR_CARD: "a card or slip opening or dividing a file: a "
                              "large ID or file number, a separator, or a "
                              "cross-reference. Handwritten, stencilled or typed",
    PageClass.BLANK_OR_ARTIFACT: "a blank page or a scan with no content",
    PageClass.OTHER_FORM: "an RRC form whose number is not listed above",
    PageClass.OTHER_NONFORM: "not a form and none of the above",
}

#: Form numbers as printed, mapped to the class that owns them. Several forms
#: share a class; most classes own exactly one number.
FORM_TOKENS = {
    "G-1": PageClass.G1,
    "W-2": PageClass.W2,
    # W-1 and its supplemental sheets. W-1H is "Supplemental Horizontal Well
    # Information", page 2 of a drilling permit application; found by eye on
    # record 1906597, never by the OCR scan, whose reading of that header was
    # too mangled to match.
    "W-1": PageClass.W1, "W-1A": PageClass.W1,
    "W-1C": PageClass.W1, "W-1H": PageClass.W1,
    "W-3": PageClass.W3,
    "P-4": PageClass.P4,
    "P-5": PageClass.P5,
    "P-12": PageClass.P12,
    "P-15": PageClass.P15,
    "G-5": PageClass.G5,
    "G-6": PageClass.G6,
    "GT-1": PageClass.GT1,
    "L-1": PageClass.L1,
    "W-12": PageClass.W12,
    "W-15": PageClass.W15,
    "P-17": PageClass.P17,
    "W-4": PageClass.W4_FAMILY, "W-4A": PageClass.W4_FAMILY,
    "W-5": PageClass.W4_FAMILY, "W-6": PageClass.W4_FAMILY,
    "WS-1": PageClass.WS1_SW1, "SW-1": PageClass.WS1_SW1,
    # Older than the numbering. Origin: DEFECTS #17, found by hand labelling
    # and confirmed on the page by Alex, not by the scanner, which could not
    # see these spellings at all until the same day.
    "FORM 2": PageClass.COMPLETION_FACE_LEGACY,
    "FORM 3": PageClass.COMPLETION_FACE_LEGACY,
    "GWT-1": PageClass.COMPLETION_FACE_LEGACY,
}


def form_token_class(token: str) -> "PageClass | None":
    """The class owning a printed form number, or None if the taxonomy has no
    answer for it.

    Used by the tier-2 coverage test, which fails when a form common enough in
    the corpus lands here as None (DEFECTS #10). That test owns the threshold;
    this function only answers the question.
    """
    return FORM_TOKENS.get((token or "").upper().strip())


# Classes where `part` is meaningful. A plat has no Section III.
FORM_CLASSES = COMPLETION_FACES | IDENTITY_BEARING

CENSUS_ONLY = frozenset(PageClass) - FORM_CLASSES

#: A named form must say which of its pages this is.
PART_REQUIRED = FORM_CLASSES

#: `other_form` may carry a part but need not. It means "a form page I cannot
#: put a number to", and such a page is still a face, a back or a continuation.
#: Forbidding a part there forced the labeller to record "back_instructions" in
#: a free-text note, where nothing can score it. 8 of the first 60 labelled
#: pages were other_form and at least two were backs.
PART_ALLOWED = PART_REQUIRED | {PageClass.OTHER_FORM}

#: Everything else: a plat has no sections and never will.
PART_FORBIDDEN = frozenset(PageClass) - PART_ALLOWED


class Part(str, Enum):
    FACE = "face"
    SEC_II = "sec_ii"
    SEC_III = "sec_iii"
    CONTINUATION = "continuation"
    BACK_INSTRUCTIONS = "back_instructions"  # pre-printed reverse; carries no data
    UNKNOWN = "unknown"


# Parts that carry filled-in data. A printed form back does not, and looks
# like a face to a classifier: same header, same form number, no values.
DATA_BEARING_PARTS = frozenset({
    Part.FACE, Part.SEC_II, Part.SEC_III, Part.CONTINUATION,
})


class Orientation(str, Enum):
    UP = "up"
    CW90 = "cw90"
    CCW90 = "ccw90"
    DOWN = "down"


class Confidence(str, Enum):
    """Coarse and self-reported. Not a probability. Its meaning comes from the
    measured accuracy-per-bucket table on the labeled set, not from the model
    saying "high".
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------- geometry guard

#: Above this aspect ratio a long-edge downscale crushes the short edge.
#: The corpus tops out at 3.71 (11264x3040, record 1495350). DEFECTS #1's
#: original page was 1010x15167, ratio 15.0.
MAX_ASPECT_RATIO = 2.0

#: Anthropic downscales images whose long edge exceeds this.
DEFAULT_LONG_EDGE = 1568


def is_oversize(width: int, height: int) -> bool:
    """True when the page is not page-shaped. Orientation must not matter."""
    if width <= 0 or height <= 0:
        raise ValueError(f"bad page dimensions: {width}x{height}")
    return max(width, height) / min(width, height) > MAX_ASPECT_RATIO


def downscale_target(width: int, height: int,
                     cap: int = DEFAULT_LONG_EDGE) -> tuple[int, int]:
    """Target size with the long edge capped. Never upscales: enlarging a
    bilevel scan invents ink that was never on the paper.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"bad page dimensions: {width}x{height}")
    longest = max(width, height)
    if longest <= cap:
        return width, height
    scale = cap / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def estimate_image_tokens(width: int, height: int) -> int:
    """Published width*height/750 rule of thumb.

    UNVERIFIED against the API. scripts/probe_haiku.py replaces this with a
    measured count_tokens figure before any cost number reaches prose
    (CLAUDE.md rule 8: numbers are measured or absent).
    """
    return round(width * height / 750)


# -------------------------------------------------------------------- page ids

#: record id, file index within that record's manifest entry, 1-based page.
_PAGE_ID = re.compile(r"^(\d+)-(\d+)-([1-9]\d*)$")


def page_id(record_id: str, file_index: int, page: int) -> str:
    """Batch API custom_id for one page.

    File index rather than file name: names run ~30 characters
    ("Neubus0_17-1501720_3833992.pdf") and the custom_id budget is 64. The
    index resolves against the manifest's file order, which is stable.
    """
    made = f"{record_id}-{file_index}-{page}"
    if not _PAGE_ID.match(made):
        raise ValueError(f"cannot form a page id from {record_id!r}, "
                         f"{file_index!r}, {page!r}")
    if len(made) > 64:
        raise ValueError(f"page id exceeds the 64-char custom_id limit: {made}")
    return made


def parse_page_id(value: str) -> tuple[str, int, int]:
    m = _PAGE_ID.match(value or "")
    if not m:
        raise ValueError(f"not a page id: {value!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


# ------------------------------------------------------------------- cache keys

def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def cache_key(doc_hash: str, prompt_hash_: str) -> str:
    """CLAUDE.md rule 7: never re-infer an unchanged (document, prompt) pair.

    Our own result cache. Not Anthropic prompt caching, which will not engage
    on a prompt this short.
    """
    return f"{doc_hash}.{prompt_hash_}"


# ------------------------------------------------------------------- page label

@dataclass(frozen=True)
class PageLabel:
    record_id: str
    file_index: int
    page: int
    form_class: PageClass
    part: Part | None
    orientation: Orientation
    confidence: Confidence
    alt_class: PageClass | None = None
    oversize: bool = False

    #: Set when a deterministic step overruled the model. Both are reported
    #: rather than applied silently: a repair nobody counts is a repair nobody
    #: can argue with.
    resolved_from: PageClass | None = None
    resolution: str | None = None

    #: Whether a printed form number can be read on the page.
    #:
    #: None means the question was never asked. Stage-1 labels and every census
    #: row written before 2026-08-31 predate it, and those stay constructible.
    #: Any answer a model gives must carry it: parse_response requires it.
    form_number_legible: bool | None = None

    def __post_init__(self) -> None:
        if self.form_class in PART_REQUIRED and self.part is None:
            raise ValueError(
                f"{self.form_class.value} is a named form; part is required")
        if self.form_class in PART_FORBIDDEN and self.part is not None:
            raise ValueError(
                f"{self.form_class.value} has no sections; part must be None, "
                f"got {self.part.value}")

        # The stage-2 invariant. Of 70 hand-labelled pages the census called a
        # G-1 or W-2 face, all 20 whose printed number could not be read were
        # misclassified, without exception. The classifier was not confusing
        # two layouts; it was guessing where it had nothing to read. So the
        # guess stops being expressible rather than being discouraged in a
        # prompt (CLAUDE.md rule 6).
        if (self.form_class in EXTRACTION_TARGETS
                and self.form_number_legible is False):
            raise ValueError(
                f"{self.form_class.value} claims a specific form number on a "
                "page where no form number can be read. Use "
                f"{PageClass.COMPLETION_FACE_UNKNOWN_FORM.value} instead.")

        # The two abstention classes are faces by definition, and they are not
        # interchangeable: legacy means the number is readable and older than
        # the numbering, unknown_form means it cannot be read at all.
        if self.form_class in COMPLETION_FACES - EXTRACTION_TARGETS:
            if self.part is not Part.FACE:
                raise ValueError(
                    f"{self.form_class.value} is a face; part must be face, "
                    f"got {self.part.value if self.part else None}")
        if (self.form_class is PageClass.COMPLETION_FACE_LEGACY
                and self.form_number_legible is False):
            raise ValueError(
                "completion_face_legacy is identified by its printed number "
                "(Form 2, Form 3, GWT-1); it cannot be illegible. Use "
                f"{PageClass.COMPLETION_FACE_UNKNOWN_FORM.value}.")
        if (self.form_class is PageClass.COMPLETION_FACE_UNKNOWN_FORM
                and self.form_number_legible is True):
            raise ValueError(
                "completion_face_unknown_form is for a page whose form number "
                "cannot be read. If it can be read, name the form.")

    @property
    def identity_bearing(self) -> bool:
        return self.form_class in IDENTITY_BEARING

    @property
    def extraction_eligible(self) -> bool:
        """DEFECTS #1 as an invariant: a page whose short edge was crushed by
        the downscale is refused until tiling exists. A printed form back is
        refused because it holds no values to extract.
        """
        return (self.form_class in COMPLETION_FACES
                and not self.oversize
                and self.part in DATA_BEARING_PARTS)

    @property
    def id(self) -> str:
        return page_id(self.record_id, self.file_index, self.page)


# -------------------------------------------------------------- model response

_REQUIRED = ("form_class", "part", "orientation", "confidence", "alt_class",
             "form_number_legible")

#: The model named a form on a page it says carries no readable form number.
RESOLVED_ILLEGIBLE = "illegible_form_number"

#: The page's own printed header disagreed with the model, and won.
RESOLVED_HEADER = "header_token_w15"

#: The one token allowed to overrule the model, and why only this one.
#:
#: Measured against the stage-2 labels before the rule was written: all 12
#: labelled pages whose header carries W-15 are W-15 cementing reports, and it
#: overturns 7 pages the re-run called a completion face, correctly on all 7.
#:
#: The general rule, any header token naming another form wins, was measured on
#: the same labels and rejected. It would overturn two real G-1 faces whose
#: headers carry a P-5 token, because field 3 of a G-1 reads "OPERATOR'S NAME
#: (Exactly as shown on Form P-5, Organization Report)" and the OCR mangles the
#: wording formscan's cross-reference filter looks for. Records 1760703 page 6
#: and 1495392 page 6. Widening this set requires the same measurement again.
HEADER_OVERRIDES = {"W-15": PageClass.W15}


def reconcile_with_header(label: "PageLabel",
                          header_tokens: frozenset[str] | set[str]) -> "PageLabel":
    """Let the form number printed on the page outrank the model's guess.

    Pure, and applied to cached and fresh results alike. DEFECTS #14 was a
    guard that ran on one of those paths and not the other.
    """
    if label.form_class not in COMPLETION_FACES or label.part is not Part.FACE:
        return label
    for token in {t.upper() for t in header_tokens}:
        target = HEADER_OVERRIDES.get(token)
        if target is not None and target is not label.form_class:
            return replace(label, form_class=target,
                           resolved_from=label.form_class,
                           resolution=RESOLVED_HEADER)
    return label


def _enum(cls, value, field_name: str):
    if value is None:
        return None
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise ValueError(
            f"{field_name}={value!r} is not one of: {allowed}") from None


def _boolean(value, field_name: str) -> bool:
    """Strict, for the same reason _enum is: a model that answers "unknown"
    to a yes/no question has told us something, and coercing it to False would
    turn that into a silent abstention nobody chose.
    """
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name}={value!r} is not true or false")


def _json_object(body: str) -> dict:
    """Accept a bare JSON object, or one fenced or prefaced with prose. Accept
    nothing else. Repairing malformed output hides a prompt problem.
    """
    text = (body or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"no JSON object in response: {body[:120]!r}")
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in response: {exc}") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def parse_response(body: str, *, record_id: str, file_index: int,
                   page: int, oversize: bool) -> PageLabel:
    """Strict. An out-of-enum class is a prompt or model problem and surfaces
    as one; it does not quietly become other_nonform.
    """
    obj = _json_object(body)
    missing = [k for k in _REQUIRED if k not in obj]
    if missing:
        raise ValueError(f"response missing {', '.join(missing)}")

    form_class = _enum(PageClass, obj["form_class"], "form_class")
    part = _enum(Part, obj["part"], "part")
    legible = _boolean(obj["form_number_legible"], "form_number_legible")

    # DEFECTS #19. Two legal values that contradict each other, with exactly
    # one resolution the taxonomy already names. Routed rather than refused,
    # and recorded rather than repaired quietly: refusing produced no label at
    # all, so the page left the corpus where the design intended an abstention
    # that still joins the record-level union.
    #
    # Only a face. The abstention class is faces only, and resolving a
    # contradicting sec_ii or continuation would move a page out of that union,
    # which is a decision about the census headline rather than a parser
    # detail. Those stay refused.
    resolved_from = resolution = None
    if (form_class in EXTRACTION_TARGETS and legible is False
            and part is Part.FACE):
        resolved_from, form_class = form_class, PageClass.COMPLETION_FACE_UNKNOWN_FORM
        resolution = RESOLVED_ILLEGIBLE

    return PageLabel(
        record_id=record_id, file_index=file_index, page=page,
        form_class=form_class,
        part=part,
        orientation=_enum(Orientation, obj["orientation"], "orientation"),
        confidence=_enum(Confidence, obj["confidence"], "confidence"),
        alt_class=_enum(PageClass, obj["alt_class"], "alt_class"),
        oversize=oversize,
        resolved_from=resolved_from,
        resolution=resolution,
        form_number_legible=legible)


# ----------------------------------------------------------------- census

@dataclass(frozen=True)
class Census:
    """Deliberately has no `permits` field. DEFECTS #2: amended filings mean a
    record can hold the same permit twice as two documents, and nothing in the
    page labels distinguishes an amendment from an original. Page counts and
    record counts are derivable; a permit count is not.
    """
    total_pages: int = 0
    total_records: int = 0
    pages_by_class: Counter = field(default_factory=Counter)
    records_by_class: Counter = field(default_factory=Counter)
    records_with_completion_report: int = 0
    oversize_pages: int = 0
    extraction_eligible_pages: int = 0
    pages_by_confidence: Counter = field(default_factory=Counter)


def aggregate(labels) -> Census:
    """Union over records, never a sum over classes: a record holding both a
    G-1 and a W-2 is one record with a completion report, not two.
    """
    pages_by_class: Counter = Counter()
    pages_by_confidence: Counter = Counter()
    classes_per_record: dict[str, set[PageClass]] = {}
    oversize = eligible = total = 0

    for label in labels:
        total += 1
        pages_by_class[label.form_class] += 1
        pages_by_confidence[label.confidence] += 1
        oversize += bool(label.oversize)
        eligible += bool(label.extraction_eligible)
        classes_per_record.setdefault(label.record_id, set()).add(label.form_class)

    records_by_class: Counter = Counter()
    for classes in classes_per_record.values():
        for cls in classes:
            records_by_class[cls] += 1

    # Union over every class meaning "a completion report face", not over the
    # two named ones. Abstaining on a page moves it within this set and never
    # out of it, which is what keeps the verified 115 stable under the change.
    with_report = sum(
        1 for classes in classes_per_record.values()
        if classes & COMPLETION_FACES)

    return Census(
        total_pages=total,
        total_records=len(classes_per_record),
        pages_by_class=pages_by_class,
        records_by_class=records_by_class,
        records_with_completion_report=with_report,
        oversize_pages=oversize,
        extraction_eligible_pages=eligible,
        pages_by_confidence=pages_by_confidence)
