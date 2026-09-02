#!/usr/bin/env python3
"""Deterministic checks over an extracted completion report.

Pure. Takes a CompletionReport and returns findings; no I/O, no model, no
corpus. Cut order step 4.

Two severities, and the difference is the point. An ERROR is structurally
impossible on any form of any era: a well plugged back below its own total
depth, a perforation that ends above where it starts, a Texas API number whose
county code is not the county the form names. A WARNING is suspicious and its
rate on this corpus has not been measured, so it is surfaced for review and
never counted as a defect until somebody measures how often it fires on
documents that are actually correct.

That split exists because of DEFECTS #10 and #11: rules written from the
handful of documents somebody happened to read do not survive contact with a
corpus spanning 1950s to 2008 paper. Every rule below names the documents it
was checked against, and the ones checked against two documents are warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from pipeline.extract import CompletionReport, Status, Value


class Severity(str, Enum):
    ERROR = "error"        # structurally impossible, on any form of any era
    WARNING = "warning"    # suspicious; its false-positive rate is unmeasured


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    fields: tuple[str, ...] = ()

    def __str__(self) -> str:
        where = f" [{', '.join(self.fields)}]" if self.fields else ""
        return f"{self.severity.value}: {self.rule}: {self.message}{where}"


# ------------------------------------------------------------------ parsing

#: Texas. Every API number in this corpus starts here, and one that does not
#: is not a well in this state.
TEXAS_STATE_CODE = "42"

_API = re.compile(r"(\d{2})\D{0,3}(\d{3})\D{0,3}(\d{4,5})")


@dataclass(frozen=True)
class ApiNumber:
    state: str
    county: str
    unique: str

    def __str__(self) -> str:
        return f"{self.state}-{self.county}-{self.unique}"


def parse_api(raw: str | None) -> ApiNumber | None:
    """A Texas API number from however it is punctuated on the page.

    Seen as "42- 039-31674" on a G-1 face and "42- 309-31674" on the G-5 in
    the same file, which is the transposition the county check exists to catch.
    """
    if not raw:
        return None
    match = _API.search(str(raw))
    if not match:
        return None
    return ApiNumber(*match.groups())


#: Feet, from a value written as 9200' or 8,608 or "6954 (Cal)".
_DEPTH = re.compile(r"-?\d[\d,]*(\.\d+)?")


def parse_depth(raw: str | None) -> float | None:
    if raw is None:
        return None
    match = _DEPTH.search(str(raw))
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SLASHED = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_WORDED = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{2,4})$")

#: This corpus is paper filed from the 1950s to 2008, so a two-digit year at
#: or below 30 is 2000s and anything above it is 1900s. Stated rather than
#: assumed: on a corpus reaching further forward this would be wrong.
_CENTURY_PIVOT = 30


def _year(raw: str) -> int:
    value = int(raw)
    if len(raw) == 4:
        return value
    return 2000 + value if value <= _CENTURY_PIVOT else 1900 + value


def parse_date(raw: str | None) -> date | None:
    """A date from the forms' several spellings, or None.

    Seen: 1977-09-22 (normalised by the extractor), 9/22/77, 9-22-77,
    11/18/08, and "May 4, 1977" on a W-2 Section II.
    """
    if not raw:
        return None
    text = str(raw).strip()
    iso = _ISO.match(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    slashed = _SLASHED.match(text)
    if slashed:
        month, day, year = slashed.groups()
        try:
            return date(_year(year), int(month), int(day))
        except ValueError:
            return None
    worded = _WORDED.match(text)
    if worded:
        name, day, year = worded.groups()
        month = _MONTHS.get(name[:3].lower())
        if month is None:
            return None
        try:
            return date(_year(year), month, int(day))
        except ValueError:
            return None
    return None


# ------------------------------------------- the archive's own index

#: The searchable API number the archive keeps beside each record, as a
#: Postgres tsvector: "'03931674':2 '1l':3 'api':1" is county 039, well
#: 31674. Present on 202 of 202 records; the 8-digit token is on 176.
_TSVECTOR_TOKEN = re.compile(r"'(\d{8})'")


def parse_api_ft(raw: str | None) -> tuple[str, str] | None:
    """(county code, unique) from the archive's index, or None.

    This is metadata the archive typed independently of the paper, so it is a
    cross-check the pipeline gets for nothing: no labels, no second form, no
    model call. It is the machine-reproducible version of noticing by eye that
    a G-5 reads 42-309-31674 where the G-1 reads 42-039-31674.
    """
    if not raw:
        return None
    match = _TSVECTOR_TOKEN.search(str(raw))
    if not match:
        return None
    digits = match.group(1)
    return digits[:3], digits[3:]


def county_codes(records) -> dict[str, str]:
    """County name to 3-digit code, learned from the archive's own index.

    `records` is an iterable of (county name, api_ft). A county that the index
    maps to more than one code is dropped rather than guessed at: a map that
    quietly picks a winner would produce confident false findings, which is
    worse than no finding at all.
    """
    seen: dict[str, set[str]] = {}
    for county, api_ft in records:
        parsed = parse_api_ft(api_ft)
        if not parsed or not (county or "").strip():
            continue
        seen.setdefault(county.strip().upper(), set()).add(parsed[0])
    return {name: next(iter(codes))
            for name, codes in seen.items() if len(codes) == 1}


def check_api_against_index(report: CompletionReport,
                            api_ft: str | None) -> list[Finding]:
    """The extracted API number against the archive's indexed one.

    Label-free and available on every extracted document, which is what makes
    the transposed-digit catch a pipeline output rather than something a human
    happened to notice.
    """
    indexed = parse_api_ft(api_ft)
    raw = _read(report.identity, "api_number")
    if indexed is None or raw is None:
        return []
    api = parse_api(raw)
    if api is None:
        return []
    findings = []
    if api.county != indexed[0]:
        findings.append(Finding(
            "api.index_county", Severity.ERROR,
            f"county code {api.county} on the page, {indexed[0]} in the "
            "archive index",
            ("identity.api_number",)))
    if api.unique.lstrip("0") != indexed[1].lstrip("0"):
        findings.append(Finding(
            "api.index_unique", Severity.WARNING,
            f"well number {api.unique} on the page, {indexed[1]} in the "
            "archive index",
            ("identity.api_number",)))
    return findings


# ------------------------------------------------------------------- access

def _read(group: dict[str, Value], name: str) -> str | None:
    """The text of a field, or None when it is not there to read.

    A blank, illegible or absent field is not a validation failure. Rules run
    on what the form actually carries.
    """
    value = group.get(name)
    if value is None or value.status is not Status.PRESENT:
        return None
    return value.value or value.raw


# -------------------------------------------------------------------- rules

def check_api_number(report: CompletionReport,
                     county_codes: dict[str, str]) -> list[Finding]:
    """The API number's shape, and its county against the county named.

    Origin: record 1501720, where the G-1 face reads 42-039-31674 and the G-5
    in the same file reads 42-309-31674. Brazoria is 039; 309 is a
    transposition, and the county the form names is what catches it.
    """
    findings: list[Finding] = []
    raw = _read(report.identity, "api_number")
    if raw is None:
        return findings

    api = parse_api(raw)
    if api is None:
        return [Finding("api.structure", Severity.ERROR,
                        f"{raw!r} is not a state-county-unique API number",
                        ("identity.api_number",))]
    if api.state != TEXAS_STATE_CODE:
        findings.append(Finding(
            "api.state", Severity.ERROR,
            f"state code {api.state} is not Texas ({TEXAS_STATE_CODE})",
            ("identity.api_number",)))

    county = _read(report.identity, "county")
    if county:
        expected = county_codes.get(county.strip().upper())
        if expected and expected != api.county:
            findings.append(Finding(
                "api.county_prefix", Severity.ERROR,
                f"county code {api.county} is not {county.strip()} "
                f"({expected})",
                ("identity.api_number", "identity.county")))
    return findings


#: Orderings that hold on any completion report because of what the events
#: are, not because of what this corpus happens to contain.
_DATE_ORDER = (
    ("date_permit_issued", "drilling_commenced",
     "a permit is issued before drilling starts"),
    ("drilling_commenced", "drilling_completed",
     "drilling starts before it finishes"),
)


def check_dates(report: CompletionReport) -> list[Finding]:
    """Date orderings, and one flag whose rate is unmeasured.

    Checked against record 1501720, whose completion date of 11/18/08 sits nine
    months after its own test date of 2/18/2008 and after the RRC's received
    stamp. HANDOFF records that document as carrying real date errors.
    """
    findings: list[Finding] = []
    dates = {name: parse_date(_read(report.completion, name))
             for name in ("date_permit_issued", "drilling_commenced",
                          "drilling_completed")}
    dates["completion_date"] = parse_date(
        _read(report.identity, "completion_date"))
    dates["date_of_test"] = parse_date(_read(report.test, "date_of_test"))

    for earlier, later, why in _DATE_ORDER:
        first, second = dates.get(earlier), dates.get(later)
        if first and second and first > second:
            findings.append(Finding(
                f"date.{earlier}_before_{later}", Severity.ERROR,
                f"{first} is after {second}, and {why}",
                (f"completion.{earlier}", f"completion.{later}")))

    started, completion = dates.get("drilling_commenced"), dates.get("completion_date")
    if started and completion and started > completion:
        findings.append(Finding(
            "date.completed_before_started", Severity.ERROR,
            f"completion date {completion} precedes the start of drilling "
            f"{started}",
            ("identity.completion_date", "completion.drilling_commenced")))

    tested = dates.get("date_of_test")
    if tested and completion and tested < completion:
        findings.append(Finding(
            "date.test_before_completion", Severity.WARNING,
            f"the test is dated {tested}, before the completion date "
            f"{completion}",
            ("test.date_of_test", "identity.completion_date")))
    return findings


def check_depths(report: CompletionReport) -> list[Finding]:
    """Depth orderings within one document.

    The orderings are structural: a well is not plugged back below its own
    total depth, a packer does not sit below the tubing shoe it hangs from,
    and an interval does not end above where it starts.
    """
    findings: list[Finding] = []
    total = parse_depth(_read(report.completion, "total_depth"))

    def below_total(depth, name, field):
        if total is not None and depth is not None and depth > total:
            findings.append(Finding(
                "depth.below_total", Severity.ERROR,
                f"{name} {depth:g} is below the total depth {total:g}",
                (field, "completion.total_depth")))

    for name, label in (("plug_back_depth", "plug-back depth"),
                        ("top_of_pay", "top of pay")):
        below_total(parse_depth(_read(report.completion, name)), label,
                    f"completion.{name}")

    previous = None
    for index, row in enumerate(report.tables.get("casing_strings", ())):
        depth = parse_depth(_read(row.cells, "depth_set"))
        below_total(depth, f"casing string {index + 1}", 
                    f"casing_strings[{index}].depth_set")
        if previous is not None and depth is not None and depth < previous:
            findings.append(Finding(
                "depth.casing_order", Severity.WARNING,
                f"casing string {index + 1} is set at {depth:g}, above the "
                f"string before it at {previous:g}",
                (f"casing_strings[{index}].depth_set",)))
        if depth is not None:
            previous = depth

    for index, row in enumerate(report.tables.get("tubing", ())):
        depth = parse_depth(_read(row.cells, "depth_set"))
        packer = parse_depth(_read(row.cells, "packer_set"))
        below_total(depth, "tubing", f"tubing[{index}].depth_set")
        if depth is not None and packer is not None and packer > depth:
            findings.append(Finding(
                "depth.packer_below_tubing", Severity.ERROR,
                f"the packer at {packer:g} is below the tubing shoe at "
                f"{depth:g}",
                (f"tubing[{index}].packer_set", f"tubing[{index}].depth_set")))

    for index, row in enumerate(report.tables.get("producing_intervals", ())):
        top = parse_depth(_read(row.cells, "from"))
        bottom = parse_depth(_read(row.cells, "to"))
        if top is not None and bottom is not None and top > bottom:
            findings.append(Finding(
                "depth.interval_inverted", Severity.ERROR,
                f"perforation interval runs from {top:g} up to {bottom:g}",
                (f"producing_intervals[{index}].from",
                 f"producing_intervals[{index}].to")))
        below_total(bottom, f"perforation interval {index + 1}",
                    f"producing_intervals[{index}].to")
    return findings


#: Boxes closer than this, in page fractions, count as touching or equal for
#: the schematic-grid signature. Real reads jitter by more than half a percent
#: of the page; a schematic emission agrees to the decimal.
_GRID_TOLERANCE = 0.005

#: Fewer abutting cells than this is not a signature. Two adjacent cells can
#: genuinely share a printed rule on the form.
_GRID_MIN_CELLS = 3


def check_geometry(report: CompletionReport) -> list[Finding]:
    """Flag table rows whose boxes are a schematic, not a reading.

    Origin: DEFECTS #29. The fingerprint, measured on document 1: every cell
    box in the row starts exactly where the previous one ends and all share
    one identical y band. That is a model drawing an idealized form from its
    layout prior. A genuine reading carries gaps and jitter.

    Permanent output, not a diagnostic one-off: if a later prompt or model
    change regresses geometry back into confabulation, nothing else here
    would say so.
    """
    findings: list[Finding] = []
    for name, rows in report.tables.items():
        for index, row in enumerate(rows):
            boxes = sorted((cell.region.box for cell in row.cells.values()
                            if cell.region is not None),
                           key=lambda b: b[0])
            if len(boxes) < _GRID_MIN_CELLS:
                continue
            same_band = all(
                abs(b[1] - boxes[0][1]) <= _GRID_TOLERANCE
                and abs(b[3] - boxes[0][3]) <= _GRID_TOLERANCE
                for b in boxes)
            abutting = all(
                abs(boxes[i][0] - boxes[i - 1][2]) <= _GRID_TOLERANCE
                for i in range(1, len(boxes)))
            if same_band and abutting:
                findings.append(Finding(
                    "geometry.schematic_grid", Severity.WARNING,
                    f"{name} row {index + 1}: {len(boxes)} cell boxes abut "
                    "edge to edge in one y band, the fingerprint of a "
                    "layout drawn from prior rather than read from the page",
                    tuple(f"{name}[{index}]" for _ in [0])))
    return findings


def validate(report: CompletionReport,
             counties: dict[str, str] | None = None,
             api_ft: str | None = None) -> list[Finding]:
    """Every rule, worst first. An empty list means nothing was checkable."""
    findings = (check_api_number(report, counties or {})
                + check_api_against_index(report, api_ft)
                + check_dates(report) + check_depths(report)
                + check_geometry(report))
    return sorted(findings, key=lambda f: (f.severity is Severity.WARNING,
                                           f.rule))
