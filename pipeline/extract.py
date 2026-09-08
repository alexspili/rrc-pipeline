#!/usr/bin/env python3
"""The extraction schema: values that know where they came from.

Pure domain. No I/O, no model calls. The shape was proposed and agreed before
any of it was written (CLAUDE.md rule 5) and probed against a real document
before it was coded (scripts/probe_sonnet.py).

Two decisions are enforced here rather than asked for in the prompt, on the
same reasoning as R13 in the classifier: a prompt can be ignored and a
constructor cannot.

  A value that is not `present` carries no box. The probe returned
  `[0, 0, 0, 0]` on a field the form does not have, which is a box that
  locates nothing and would draw a highlight in the page's top-left corner.

  A `status` is never inferred from emptiness. `blank`, `illegible` and
  `not_on_this_form` are three different facts about a form, and the whole
  point of the enum is that scoring cannot mix them. A 1975 Form W-2 has no
  API number field at all; that is not the same as an operator leaving one
  empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from pipeline.pageclass import PageClass
from pipeline.pageclass import _json_object   # fenced or bare JSON, one parser


class Status(str, Enum):
    """Why a value is or is not here. Never collapse these."""

    PRESENT = "present"                    # written on the page, and read
    BLANK = "blank"                        # the field exists, nobody filled it
    ILLEGIBLE = "illegible"                # written, and not readable
    NOT_ON_THIS_FORM = "not_on_this_form"  # this revision has no such field

    #: The form has this field, on a page this document does not contain.
    #:
    #: Origin: DEFECTS #24. Distinct from both neighbours above, and common
    #: rather than exotic: 9 of the 15 ground-truth documents are face-only,
    #: and only 107 of the 486 corpus pages that point to a reverse side are
    #: actually followed by one. Calling it not_on_this_form asserts the form
    #: has no such field; calling it blank asserts an operator left it empty.
    PAGE_NOT_IN_DOCUMENT = "page_not_in_document"


#: Only a value that is actually on the page can be pointed at.
LOCATABLE = frozenset({Status.PRESENT})

#: Where a region's coordinates came from. Ordered strongest to weakest, and
#: the order is the honesty ordering the viewer renders:
#:
#:   text_layer   a word box measured off the page by pdftotext
#:   template     a per-revision form template, registered onto this page
#:   template_row an even row band inside a template's table block, which is
#:                the one place the mechanism guesses at a boundary
#:   model        the vision model's own report of where it read something,
#:                measured at hit+near 60.9% overall and 11.4% on 1966 paper
#:   page         no geometry at all: here is the page and the raw text
SOURCES = frozenset({"text_layer", "template", "template_row", "model",
                     "page"})


@dataclass(frozen=True)
class Region:
    """Where on a page a value sits, as fractions of width and height.

    Fractions rather than pixels: the image sent to the model is downscaled
    from the source scan and the viewer renders at another size again.

    Approximate by construction. A vision model reports roughly where it read
    something; this is a locator for a human reviewer, not a measurement.

    `source` says which mechanism asserted the box, and it is not decoration.
    The grading of 2026-09-03 measured region quality as a steep function of
    where the coordinates came from, so a viewer that renders a snapped box
    and a modelled one identically is claiming a confidence it does not have.
    The tag travels all the way into the viewer and stays visually distinct
    there (DEFECTS #29, and the design rule that came out of it).

    It defaults to `model` so that every region already on disk keeps the
    provenance it actually had. Nothing recorded before this field existed
    came from anywhere else.
    """

    page: int
    box: tuple[float, float, float, float]
    source: str = "model"

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(
                f"unknown region source {self.source!r}, expected one of "
                f"{sorted(SOURCES)}")
        if self.page < 1:
            raise ValueError(f"page is 1-based, got {self.page}")
        if len(self.box) != 4:
            raise ValueError(f"box needs four numbers, got {len(self.box)}")
        left, top, right, bottom = self.box
        if not all(0.0 <= v <= 1.0 for v in self.box):
            raise ValueError(
                f"box must be fractions of the page, 0 to 1, got {self.box}")
        if left >= right or top >= bottom:
            raise ValueError(
                f"box must have positive area as [left, top, right, bottom], "
                f"got {self.box}")

    @property
    def area(self) -> float:
        return (self.box[2] - self.box[0]) * (self.box[3] - self.box[1])


@dataclass(frozen=True)
class Correction:
    """A value struck through on the paper and replaced by hand.

    Both completion faces read while designing this schema carry one: the G-1
    on record 1501720 has "Cowtrap (Wildcat)" struck out for "Miocene 6350",
    and the W-2 on 1493495 has "Wildcat" struck out for "RED FISH REEF NORTH
    (F-8)". Keeping only the final value would throw away exactly the
    disagreement the cross-form checker exists to find.
    """

    raw: str
    region: Region | None = None


@dataclass(frozen=True)
class Value:
    """One extracted field. The unit that carries provenance."""

    status: Status
    value: str | None = None
    raw: str | None = None
    region: Region | None = None
    correction: Correction | None = None

    #: The printed label of the box the model says it read this from, copied
    #: off the page, with the field number when the form prints one.
    #:
    #: It is a claim and not proof, in exactly the way `region` is. The box
    #: grading of 2026-09-03 measured the model's own geometry at hit+near
    #: 60.9%, and nothing here makes a label more self-verifying than a
    #: rectangle was (DEFECTS #29, #42). What it buys is that a value read out
    #: of the wrong box becomes checkable by a human, and that two documents
    #: which agree on every value can still be told apart by which boxes those
    #: values came from, which is what DEFECTS #43 turned on.
    #:
    #: The label text, never the field number on its own: the same box is
    #: numbered 24 on a G-1 and 31 or 32 on a W-2 (DEFECTS #59).
    #:
    #: Defaults to None so every value already on disk keeps its meaning.
    #: Nothing recorded before this field existed carried a label.
    found_in: str | None = None

    def __post_init__(self) -> None:
        if self.status in LOCATABLE:
            if self.region is None:
                raise ValueError(
                    "a present value must say where it was read from")
            if self.raw is None:
                raise ValueError(
                    "a present value must carry the text as written")
        else:
            if self.region is not None:
                raise ValueError(
                    f"a {self.status.value} value has nothing to point at; "
                    "region must be None")
            if self.value is not None or self.raw is not None:
                raise ValueError(
                    f"a {self.status.value} value carries no text, got "
                    f"value={self.value!r} raw={self.raw!r}")
            if self.found_in is not None:
                raise ValueError(
                    f"a {self.status.value} value was not read out of a box, "
                    f"got found_in={self.found_in!r}")
        if self.correction is not None and self.status not in LOCATABLE:
            raise ValueError(
                "a correction belongs to a value that was actually read")

    @property
    def corrected(self) -> bool:
        return self.correction is not None


@dataclass(frozen=True)
class Row:
    """One line of a table: casing string, perforation interval, formation top.

    A row is a mapping of column name to Value so that a table cell carries
    provenance exactly like a scalar field does. Nothing about a casing depth
    makes it less worth locating than a completion date.
    """

    cells: dict[str, Value] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, cell in self.cells.items():
            if not isinstance(cell, Value):
                raise ValueError(f"row cell {name!r} is not a Value")

    def get(self, name: str) -> Value | None:
        return self.cells.get(name)


#: v1 field sets, from the cut order: identity, dates, depths, casing.
#: The per-form test tables are v2 and v1 must not grow into them.
IDENTITY_FIELDS = (
    "field_name", "lease_name", "well_number", "operator_name",
    "operator_address", "county", "rrc_district", "location_survey",
    "distance_to_town", "api_number", "rrc_well_id", "purpose_of_filing",
    "completion_date", "pipeline_connection", "logs_run",
)

COMPLETION_FIELDS = (
    "type_of_completion", "date_permit_issued", "drilling_commenced",
    "drilling_completed", "total_depth", "plug_back_depth", "top_of_pay",
    "elevation", "directional_survey", "drilling_contractor",
)

#: Tabular blocks. `tubing` is here rather than among the scalars because it
#: is one row of the same kind of data as a casing string, and the W-2 prints
#: it as a one-row table. Modelling it as a lone object dropped it silently on
#: the first real document parsed, which is standing rule 9 arriving in this
#: module's own code: three values gone, no error raised.
COMPLETION_TABLES = (
    "casing_strings", "liner_strings", "tubing", "producing_intervals",
    "treatments", "formation_tops",
)

#: v1 takes one field from the test block and no more.
TEST_FIELDS = ("date_of_test",)


@dataclass(frozen=True)
class CompletionReport:
    """One completion report, reassembled from its face and its sections."""

    record_id: str
    file_index: int
    pages: tuple[int, ...]
    form_class: str
    form_revision: Value
    identity: dict[str, Value] = field(default_factory=dict)
    completion: dict[str, Value] = field(default_factory=dict)
    tables: dict[str, tuple[Row, ...]] = field(default_factory=dict)
    test: dict[str, Value] = field(default_factory=dict)

    #: Keys the model returned that the v1 schema has no home for. Recorded
    #: rather than discarded quietly, on the same reasoning as R16 in the
    #: classifier: a drop nobody counts is a drop nobody can argue with, and
    #: this module lost `tubing` that way on its first real document.
    dropped: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError("a completion report comes from at least one page")
        for name, group, allowed in (
                ("identity", self.identity, IDENTITY_FIELDS),
                ("completion", self.completion, COMPLETION_FIELDS),
                ("test", self.test, TEST_FIELDS)):
            unknown = sorted(set(group) - set(allowed))
            if unknown:
                raise ValueError(f"{name} has fields not in the v1 schema: "
                                 f"{', '.join(unknown)}")
        unknown = sorted(set(self.tables) - set(COMPLETION_TABLES))
        if unknown:
            raise ValueError(f"unknown tables: {', '.join(unknown)}")
        for value in self.values():
            if value.region is not None and value.region.page not in self.pages:
                raise ValueError(
                    f"a value cites page {value.region.page}, which is not one "
                    f"of this document's pages {self.pages}")

    def values(self):
        """Every Value in the document, scalars and table cells alike."""
        for group in (self.identity, self.completion, self.test):
            yield from group.values()
        yield self.form_revision
        for rows in self.tables.values():
            for row in rows:
                yield from row.cells.values()

    def named_values(self):
        """(dotted name, Value) pairs in a stable order.

        The order is load-bearing for the overlay tooling: the numbers drawn
        on a page and the rows of the grading sheet are the same enumeration,
        and they must never diverge.
        """
        yield "document.form_revision", self.form_revision
        for group_name, group in (("identity", self.identity),
                                  ("completion", self.completion),
                                  ("test", self.test)):
            for field, value in group.items():
                yield f"{group_name}.{field}", value
        for table, rows in self.tables.items():
            for index, row in enumerate(rows):
                for cell_name, cell in row.cells.items():
                    yield f"{table}[{index}].{cell_name}", cell

    @property
    def located(self) -> int:
        return sum(1 for v in self.values() if v.region is not None)

    @property
    def present(self) -> int:
        return sum(1 for v in self.values() if v.status is Status.PRESENT)


# ------------------------------------------------------------------ parsing

_FRACTION = re.compile(r"^-?\d+(\.\d+)?$")


def _page_of(index, pages: tuple[int, ...] | None) -> int | None:
    """Translate the model's page index into a page of the file.

    The model is shown "Page 1 of 2" and answers with that index. The document
    knows the pages are, say, 9 and 10 of the file. Conflating the two made
    every value in the first smoke run cite a page its document did not have.
    """
    if index is None:
        return None
    try:
        index = int(index)
    except (TypeError, ValueError):
        return None
    if pages is None:
        return index
    if 1 <= index <= len(pages):
        return pages[index - 1]
    return None


def _region(raw, page_hint: int | None) -> Region | None:
    """A box from the model, or None. A degenerate box is not a box.

    The probe returned [0, 0, 0, 0] on a field the form does not have. Read
    literally that is the page's top-left corner, and it would draw a highlight
    there. Treated as absent rather than repaired into something plausible.
    """
    if not raw:
        return None
    box = raw.get("box") if isinstance(raw, dict) else raw
    if not box or not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        numbers = tuple(float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        return None
    page = raw.get("page") if isinstance(raw, dict) else None
    resolved = page if page is not None else page_hint
    if resolved is None:
        return None
    return Region(page=int(resolved), box=numbers)


#: Keys that mark an object as a value rather than a table row. An empty
#: table comes back as a value object with status "blank": the prompt says
#: every value is an object and also that tables are arrays, and a table with
#: nothing in it satisfies the first rule. Two smoke documents did this.
_VALUE_KEYS = frozenset({"status"})


def looks_like_value(obj) -> bool:
    return isinstance(obj, dict) and bool(_VALUE_KEYS & set(obj))


def parse_value(obj, *, page_hint: int | None = None,
                pages: tuple[int, ...] | None = None) -> Value:
    """One value object from the model.

    Strict about status, which is the field the whole schema turns on, and
    forgiving about a missing box, which the type then decides the meaning of.
    """
    if not isinstance(obj, dict):
        raise ValueError(f"expected a value object, got {type(obj).__name__}")
    if "status" not in obj:
        raise ValueError("value object has no status")
    try:
        status = Status(obj["status"])
    except ValueError:
        allowed = ", ".join(s.value for s in Status)
        raise ValueError(
            f"status={obj['status']!r} is not one of: {allowed}") from None

    mapped = dict(obj)
    mapped["page"] = _page_of(obj.get("page"), pages)
    region = _region(mapped, page_hint) if status in LOCATABLE else None
    correction = None
    raw_correction = obj.get("correction")
    if raw_correction and status in LOCATABLE:
        fixed = dict(raw_correction)
        fixed["page"] = _page_of(raw_correction.get("page", obj.get("page")),
                                 pages)
        correction = Correction(
            raw=str(raw_correction.get("raw", "")),
            region=_region(fixed, page_hint))

    if status in LOCATABLE:
        return Value(status=status,
                     value=_text(obj.get("value")),
                     raw=_text(obj.get("raw")) or _text(obj.get("value")),
                     region=region, correction=correction,
                     found_in=_text(obj.get("found_in")))
    return Value(status=status)


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


#: Observed model spellings for forms the vocabulary does not enumerate,
#: mapped after reading the paper: all 17 corpus faces the 2026-09-07 run
#: refused were rendered and their mastheads read. Form 2 "Well Record" is
#: the pre-G-1/W-2 completion report and is the first real member of the
#: class the stage-2 decided fix defined; Form 3 "Potential Test Form"
#: (1-1958), GWT-1 (Rev. 6-1-54) and the rest are test filings or non-RRC
#: paper, not completions. Keys are normalise_form_class tokens (lowercased,
#: dashes and spaces stripped). Only strings seen on read paper belong here;
#: an unknown string still raises, which is R8.
LEGACY_ALIASES = {
    "2": "completion_face_legacy",        # Form 2 "Well Record"
    "form2": "completion_face_legacy",
    "3": "other_form",                    # Form 3 "Potential Test Form"
    "form3": "other_form",
    "g3": "other_form",                   # Form 3, gas-well instance
    "gwt1": "other_form",                 # GWT-1 back pressure test
    "other": "other_form",
    "welltestreport": "other_form",       # a testing contractor's own sheet
}


def normalise_form_class(raw: str) -> str:
    """One spelling per class, and the class must exist.

    Origin: DEFECTS #22. The smoke run wrote `g1` on two documents and `g-1` on
    two others, which are two classes to every count downstream.

    Validated against the whole `PageClass` vocabulary rather than against the
    two values the prompt asks for. The same run answered `w15` on a page the
    stage-2 labels confirm is a W-15 cementing report, which is extraction
    acting as a second opinion on the classifier. Narrowing this to g1 and w2
    would throw that away.
    """
    token = (raw or "").strip().lower().replace("-", "").replace(" ", "")
    for member in PageClass:
        if member.value.replace("_", "") == token.replace("_", ""):
            return member.value
    # The enum match first, the alias table second, so an alias can never
    # shadow a real class ("gwt1" stays distinct from the enum's "gt1").
    alias = LEGACY_ALIASES.get(token.replace("_", ""))
    if alias:
        return alias
    raise ValueError(f"form_class={raw!r} is not a page class")


def parse_report(body: str, *, record_id: str, file_index: int,
                 pages: tuple[int, ...]) -> CompletionReport:
    """A whole document from one model response.

    Uses the classifier's `_json_object`, which already tolerates a fenced or
    prose-prefaced object and refuses anything else. The probe fenced its
    output; a second parser would have been a second thing to keep correct.
    """
    obj = _json_object(body)
    pages = tuple(pages)
    document = obj.get("document") or {}
    form_class = document.get("form_class")
    # Returned as a bare string on some documents and as a value object on
    # others, because the prompt asked for both shapes in one block. Accept
    # either rather than losing a document to a wrapper.
    if looks_like_value(form_class):
        form_class = form_class.get("value")
    if not form_class or not isinstance(form_class, str):
        raise ValueError("response has no document.form_class")
    form_class = normalise_form_class(form_class)

    def group(name: str, allowed) -> dict[str, Value]:
        source = obj.get(name) or {}
        return {k: parse_value(v, pages=pages)
                for k, v in source.items() if k in allowed}

    completion_obj = obj.get("completion") or {}
    tables: dict[str, tuple[Row, ...]] = {}
    for name in COMPLETION_TABLES:
        rows = completion_obj.get(name) or []
        # An empty table arrives as a value object with status "blank", not as
        # an empty list. Read as no rows; reading its status and box keys as
        # cells is what the first smoke run did.
        if looks_like_value(rows):
            rows = []
        # A one-row table may arrive as a bare object. The W-2 prints tubing
        # as a single row and the model returns it either way.
        elif isinstance(rows, dict):
            rows = [rows]
        parsed = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{name} contains a non-row entry")
            parsed.append(Row(cells={k: parse_value(v, pages=pages)
                                     for k, v in row.items()}))
        if parsed:
            tables[name] = tuple(parsed)

    known = {"identity": IDENTITY_FIELDS, "test": TEST_FIELDS,
             "completion": tuple(COMPLETION_FIELDS) + tuple(COMPLETION_TABLES)}
    # Root-level keys are scanned too. Three re-score documents returned
    # every field flattened beside `document`, and the first version of this
    # accounting only looked inside the groups it knew, so 26 fields per
    # document vanished with dropped reporting zero (DEFECTS #74).
    dropped = tuple(sorted(
        {f"{group}.{key}"
         for group, allowed in known.items()
         for key in (obj.get(group) or {})
         if key not in allowed}
        | {key for key in obj
           if key not in ("document", *known)}))

    return CompletionReport(
        record_id=record_id, file_index=file_index, pages=pages,
        form_class=form_class,
        form_revision=parse_value(document.get("form_revision")
                                  or {"status": "blank"}, pages=pages),
        identity=group("identity", IDENTITY_FIELDS),
        completion=group("completion", COMPLETION_FIELDS),
        tables=tables,
        test=group("test", TEST_FIELDS),
        dropped=dropped)
