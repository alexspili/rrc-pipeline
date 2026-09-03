#!/usr/bin/env python3
"""Per-revision form templates: geometry from the paper, not from the model.

Pure domain. No I/O, no model calls, no PDF reading. Everything here takes
word boxes as input and returns geometry, so all of it is tier-1 testable.

Origin: DEFECTS #29 and the box grading that followed it. Model boxes are not
field locators on this paper. This module tests the other framing: these are
forms, a revision's layout is fixed, and the corpus is evidence about roughly
twelve templates rather than about 839 independent boxes.

Three rules are enforced here rather than asked for, on the reasoning that a
constructor is stronger than a prompt.

  A token becomes a canonical anchor only if it appears exactly once on a
  page and on at least two pooled pages. A token the OCR garbles differently
  on every page never pools, which is the abstention principle applied to
  the template's own fuel.

  A field's label must resolve to one anchor, or to several anchors that
  agree with each other. Anything else abstains. Never a nearest match:
  a wrong box that looks grounded is worse than an honest band, and this is
  the settled design rule that binds whichever mechanism wins.

  Pooling uses the median, not the mean, so one badly registered page cannot
  drag a field's canonical position.

The pre-registered bar this is measured against is in
docs/labeling-protocol-extract.md under "Box grading, stage three".
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field
from difflib import SequenceMatcher

from pipeline.textlayer import Word, norm

#: A token is selective enough to anchor on at four characters. Same rule and
#: same reason as scripts/snap_coverage.py: "of" and "3" match half a page.
MIN_ANCHOR_CHARS = 4

#: Fuzzy match threshold for a printed label token against a canonical
#: anchor. The OCR on this paper garbles labels rather than losing them:
#: "Complet4on", "PUTENTi", "Rscoeds". Exact matching would abstain on all
#: three; a loose threshold would match anything.
LABEL_RATIO = 0.80

#: A printed label is a phrase, so agreement between the anchors resolved
#: from it is anisotropic. Its tokens share a printed line, which is tight,
#: and they can run a long way along it, which is loose. One threshold for
#: both was wrong in both directions at once: too tight for "6. LOCATION
#: (Section, Block, and Survey)", which spans 0.16 of the page, and loose
#: enough to call two anchors 0.137 apart in y, nineteen line-heights, the
#: same label. The line tolerance is about one and a half line-heights on
#: this corpus, which is tight enough that two consecutive printed labels do
#: not merge into one; checkbox stacks are handled as columns rather than by
#: loosening it until they fit.
LABEL_LINE_Y = 0.011
LABEL_LINE_X = 0.35

#: A checkbox label runs down the page instead: "11. Purpose of Test" over
#: Initial Potential, Retest, Reclass. So a checkbox spec is also clustered
#: as a column, and whichever grouping accounts for more of the label's
#: distinct tokens wins.
LABEL_COLUMN_X = 0.06
LABEL_COLUMN_Y = 0.15

#: Registration gates. A page below either is declared unregistered and the
#: template asserts nothing about it, which is an outcome rather than a
#: failure: unknown-frame pages fall through to the layered join.
MIN_ANCHORS = 8
MAX_RESIDUAL = 0.010

#: One declared round of outlier trimming before the gate is applied. A page
#: where the OCR puts one token in the wrong place is a page with one bad
#: measurement, not a page from another form, and discarding it whole would
#: throw away fuel this corpus does not have to spare. A pair is trimmed when
#: its residual exceeds this multiple of the median residual; the fit is then
#: redone on what survives, and the gate judges that. Trimming can never
#: rescue a page below MIN_ANCHORS, so a page that only agrees about seven
#: tokens is still refused.
TRIM_MULTIPLE = 3.0
TRIM_FLOOR = 0.005

#: The value band's vertical padding, in multiples of the page's median line
#: height, and the tolerance for "on the same printed line".
BAND_LINES = 0.6

#: Caps on an asserted region, in page fractions. A cell rule that ran to the
#: next printed text could hand back half a page, and a big box scores `hit`
#: for reasons that have nothing to do with locating anything: the grading
#: protocol was written against model boxes, which were small, so it does not
#: guard against winning by drawing large. A region over the cap is clipped
#: back to the cap at the label's top-left corner, because that corner is
#: where the value starts. Region areas are reported beside the grades so the
#: two mechanisms can be compared on size as well as on landing.
MAX_REGION_WIDTH = 0.45
MAX_REGION_HEIGHT = 0.075

#: Right edge used when no anchor follows the label on its line.
PAGE_RIGHT = 0.98


def revision_key(raw: str | None) -> str:
    """`Rev. 4/1/83` and `Rev. 4/ 1/ 83` are one template, not two.

    The smoke run carries both spellings. Without this a revision gets two
    templates, each with half the fuel, and neither is ever tested against
    the other.
    """
    return norm(raw or "") or "unknown"


@dataclass(frozen=True)
class Affine:
    """u = a x + b y + c, v = d x + e y + f."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.b * y + self.c,
                self.d * x + self.e * y + self.f)

    def box(self, box: tuple[float, float, float, float]):
        x0, y0 = self.apply(box[0], box[1])
        x1, y1 = self.apply(box[2], box[3])
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


IDENTITY = Affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclass(frozen=True)
class Anchor:
    """A printed token whose position is agreed across pooled pages."""

    token: str
    box: tuple[float, float, float, float]
    pages: int
    spread: tuple[float, float]

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2,
                (self.box[1] + self.box[3]) / 2)


@dataclass(frozen=True)
class Registration:
    """How a page maps onto a template's frame, and how well."""

    transform: Affine
    matched: int
    residual_median: float
    residual_p90: float


@dataclass
class Template:
    """One revision, one form class, one page role."""

    revision: str
    form_class: str
    page_role: str
    anchors: dict[str, Anchor] = dc_field(default_factory=dict)
    fields: dict[str, tuple[float, float, float, float]] = dc_field(
        default_factory=dict)
    line_height: float = 0.012
    built_from: list[str] = dc_field(default_factory=list)
    rejected: list[str] = dc_field(default_factory=list)


# --------------------------------------------------------------------------
# least squares affine, in pure Python: no new dependency
# --------------------------------------------------------------------------

def _solve3(matrix, rhs):
    """Gaussian elimination with partial pivoting on a 3x3 system."""
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(3):
            if r == col:
                continue
            factor = m[r][col] / m[col][col]
            for k in range(col, 4):
                m[r][k] -= factor * m[col][k]
    return [m[i][3] / m[i][i] for i in range(3)]


def fit_affine(pairs) -> tuple[Affine | None, list[float]]:
    """Least-squares 2x3 affine from source points onto target points.

    Returns the transform and the per-point residual distances. Fewer than
    three points, or three collinear ones, returns None rather than a
    transform that happens to satisfy an underdetermined system.
    """
    if len(pairs) < 3:
        return None, []
    design = [[sx, sy, 1.0] for (sx, sy), _ in pairs]
    normal = [[sum(design[i][r] * design[i][c] for i in range(len(design)))
               for c in range(3)] for r in range(3)]
    coefficients = []
    for axis in (0, 1):
        rhs = [sum(design[i][r] * pairs[i][1][axis] for i in range(len(pairs)))
               for r in range(3)]
        solved = _solve3(normal, rhs)
        if solved is None:
            return None, []
        coefficients.append(solved)
    transform = Affine(*coefficients[0], *coefficients[1])
    residuals = []
    for (sx, sy), (tx, ty) in pairs:
        ux, uy = transform.apply(sx, sy)
        residuals.append(((ux - tx) ** 2 + (uy - ty) ** 2) ** 0.5)
    return transform, residuals


def robust_fit(pairs, min_pairs: int = MIN_ANCHORS):
    """Fit, trim the pairs the fit disagrees with most, fit again.

    Returns (transform, residuals, kept, trimmed). The second fit is the one
    that counts, and the residuals returned are the surviving ones, so the
    gate in `register` judges the page the transform was actually built from.
    """
    transform, residuals = fit_affine(pairs)
    if transform is None:
        return None, [], 0, 0
    if len(pairs) <= min_pairs:
        return transform, residuals, len(pairs), 0
    limit = max(TRIM_MULTIPLE * statistics.median(residuals), TRIM_FLOOR)
    kept = [pair for pair, residual in zip(pairs, residuals)
            if residual <= limit]
    if len(kept) < min_pairs or len(kept) == len(pairs):
        return transform, residuals, len(pairs), 0
    refit, refit_residuals = fit_affine(kept)
    if refit is None:
        return transform, residuals, len(pairs), 0
    return refit, refit_residuals, len(kept), len(pairs) - len(kept)


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]


# --------------------------------------------------------------------------
# anchors and registration
# --------------------------------------------------------------------------

def unique_tokens(words: list[Word]) -> dict[str, tuple[float, ...]]:
    """Tokens that occur exactly once on the page, with their boxes.

    Uniqueness is not a nicety. A token appearing twice cannot register a
    page without a choice, and the settled rule forbids making that choice
    by proximity.
    """
    counts = Counter(norm(w[4]) for w in words
                     if len(norm(w[4])) >= MIN_ANCHOR_CHARS)
    return {norm(w[4]): tuple(w[:4]) for w in words
            if counts.get(norm(w[4])) == 1}


def line_height(words: list[Word]) -> float:
    heights = [w[3] - w[1] for w in words if w[3] > w[1]]
    return statistics.median(heights) if heights else 0.012


def register(template: Template, words: list[Word],
             min_anchors: int = MIN_ANCHORS,
             max_residual: float = MAX_RESIDUAL) -> Registration | None:
    """Map this page onto the template frame, or refuse to.

    Refusing is a real answer. A page that cannot be registered gets no
    template geometry at all and falls through to the layered join, which is
    the fallback the mechanism keeps for unknown-revision pages.
    """
    page = unique_tokens(words)
    pairs = []
    for token, anchor in template.anchors.items():
        box = page.get(token)
        if box is None:
            continue
        pairs.append((((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                      anchor.centre))
    if len(pairs) < min_anchors:
        return None
    transform, residuals, kept, _ = robust_fit(pairs, min_anchors)
    if transform is None:
        return None
    median = statistics.median(residuals)
    if median > max_residual:
        return None
    return Registration(transform, kept, median, _p90(residuals))


def build_anchors(pages: list[list[Word]], min_pages: int = 2):
    """Pool unique tokens across registered pages, by median position.

    Pages are registered onto the page with the most unique tokens before
    pooling, so a differently cropped scan does not smear every anchor.
    """
    if not pages:
        return {}, [], []
    per_page = [unique_tokens(w) for w in pages]
    reference = max(range(len(pages)), key=lambda i: len(per_page[i]))
    positions = defaultdict(list)
    used, rejected = [reference], []
    for token, box in per_page[reference].items():
        positions[token].append(box)
    for index, tokens in enumerate(per_page):
        if index == reference:
            continue
        shared = [t for t in tokens if t in per_page[reference]]
        pairs = [((sum(tokens[t][0::2]) / 2, sum(tokens[t][1::2]) / 2),
                  (sum(per_page[reference][t][0::2]) / 2,
                   sum(per_page[reference][t][1::2]) / 2)) for t in shared]
        if len(pairs) < MIN_ANCHORS:
            rejected.append(index)
            continue
        transform, residuals, _, _ = robust_fit(pairs)
        if transform is None or statistics.median(residuals) > MAX_RESIDUAL:
            rejected.append(index)
            continue
        used.append(index)
        for token, box in tokens.items():
            positions[token].append(transform.box(box))
    anchors = {}
    for token, boxes in positions.items():
        if len(boxes) < min_pages:
            continue
        median = tuple(statistics.median(b[i] for b in boxes)
                       for i in range(4))
        centres_x = [(b[0] + b[2]) / 2 for b in boxes]
        centres_y = [(b[1] + b[3]) / 2 for b in boxes]
        anchors[token] = Anchor(
            token=token, box=median, pages=len(boxes),
            spread=(max(centres_x) - min(centres_x),
                    max(centres_y) - min(centres_y)))
    return anchors, used, rejected


# --------------------------------------------------------------------------
# labels to fields
# --------------------------------------------------------------------------

def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def shared_label_tokens(specs) -> set[str]:
    """Tokens claimed by more than one field spec, which anchor nothing.

    "operator" is on this list: Rev. 7/5/66 prints it for field 3 and again
    for "if Operator has changed within last 60 days, give former Operator".
    Matching on it would put the operator's name two field-rows below where
    it is, which is precisely the failure the model boxes already make.
    """
    counts: Counter = Counter()
    for spec in specs.values():
        for token in set(spec.tokens):
            counts[token] += 1
    return {token for token, n in counts.items() if n > 1}


def _cluster(found, axis: int, tol: float, span: float):
    """Group resolved anchors into label candidates along one axis."""
    ordered = sorted(found, key=lambda item: item[1].centre[axis])
    groups, current = [], []
    for token, anchor in ordered:
        if current and (anchor.centre[axis]
                        - current[-1][1].centre[axis]) > tol:
            groups.append(current)
            current = []
        current.append((token, anchor))
    if current:
        groups.append(current)
    other = 1 - axis
    return [g for g in groups
            if max(a.centre[other] for _, a in g)
            - min(a.centre[other] for _, a in g) <= span]


def _best(groups):
    """The group accounting for most of the label's distinct tokens.

    A tie is an abstention, not a coin toss. `operator` pools at field 3 and
    again at "if Operator has changed, give former Operator", one distinct
    token each, and picking either would be the nearest-guess.
    """
    if not groups:
        return None
    # A checkbox label is clustered both ways, and for a one-anchor label the
    # line and the column are the same group. Left in, that identity looked
    # like a tie and abstained on a field the template had actually found.
    seen, unique = set(), []
    for group in groups:
        key = frozenset(id(anchor) for _, anchor in group)
        if key not in seen:
            seen.add(key)
            unique.append(group)
    ranked = sorted(unique, key=lambda g: -len({token for token, _ in g}))
    if len(ranked) > 1 and (len({t for t, _ in ranked[0]})
                            == len({t for t, _ in ranked[1]})):
        return None
    return ranked[0]


def resolve_label(anchors: dict[str, Anchor], tokens, banned: set[str],
                  checkbox: bool = False):
    """The anchor box a printed label resolves to, or None.

    Unique, or decisively disambiguated by position. Never nearest.

    "Decisively disambiguated" earns its place. The pool holds `lease` and
    `leasp` for one printed word the OCR read two ways, and `wildcat` beside
    `widcat`; those are one label, not two candidates. It also holds `field`
    twice in genuinely different places, and `well` against `wells` half a
    page apart, which are two candidates and abstain. The test that separates
    them is whether the anchors share a printed line, and the tie-break is
    which line accounts for more of the label's own distinct tokens.
    """
    found = []
    for token in tokens:
        if token in banned:
            continue
        for name, anchor in anchors.items():
            if _ratio(token, name) >= LABEL_RATIO:
                found.append((token, anchor))
    if not found:
        return None
    groups = _cluster(found, 1, LABEL_LINE_Y, LABEL_LINE_X)
    if checkbox:
        groups = groups + _cluster(found, 0, LABEL_COLUMN_X, LABEL_COLUMN_Y)
    best = _best(groups)
    if best is None:
        return None
    boxes = [a.box for _, a in best]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def value_region(anchors: dict[str, Anchor], label_box, height: float,
                 checkbox: bool = False):
    """Where the value sits, given where its printed label sits.

    The rule as first declared put the value to the right of its label. That
    is wrong for this form family and the fuel pages said so before any
    grading: Rev. 7/5/66 prints the label in the top-left corner of a ruled
    cell and the operator types the value **underneath** it. "6. LOCATION
    (Section, Block, and Survey)" sits at y 0.272 and its value at y 0.287.
    A right-of-label band returned slivers 0.02 wide that contained nothing.

    So the region is the cell the label corners: from the label's left edge
    to the next printed anchor on its line, and from the label's top down to
    the next printed anchor below inside that column. That covers a value
    written to the right and a value written below with one rule rather than
    a choice between two, and choosing between two would be the nearest-guess
    the design rules forbid.

    Changed after reading the fuel pages and before any box was graded. The
    graded document is sealed, so this is engineering against the mechanism
    rather than tuning against the outcome, but it is a change to a declared
    rule and it is recorded as one.
    """
    left = label_box[0]
    top = label_box[1]
    centre_y = (label_box[1] + label_box[3]) / 2
    same_line = [a for a in anchors.values()
                 if abs(a.centre[1] - centre_y) <= BAND_LINES * height
                 and a.box[0] >= label_box[2]]
    right = min([a.box[0] for a in same_line], default=PAGE_RIGHT)
    if checkbox:
        right = max([a.box[2] for a in same_line] + [label_box[2]])
    below = [a for a in anchors.values()
             if a.box[1] > label_box[3] + 0.2 * height
             and a.centre[0] >= left - 0.02 and a.centre[0] <= right + 0.02]
    bottom = min([a.box[1] for a in below],
                 default=label_box[3] + 3.0 * height)
    right = min(max(right, left + 0.02), 1.0)
    bottom = min(max(bottom, label_box[3] + 0.4 * height), 1.0)
    right = min(right, left + MAX_REGION_WIDTH)
    bottom = min(bottom, top + MAX_REGION_HEIGHT)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def row_region(block: tuple[float, float, float, float], index: int,
               rows: int):
    """Row k of n, by equal bands inside a table block.

    This is the one declared guess in the design. It assumes a table's rows
    are evenly ruled, which is a weaker assumption than the rest of the
    module makes and is the first thing that should break on a form whose
    rows are not. It carries its own source tag so that it can be reported
    separately and cannot inflate the headline.
    """
    if rows <= 0 or not 0 <= index < rows:
        return None
    top = block[1] + (block[3] - block[1]) * index / rows
    bottom = block[1] + (block[3] - block[1]) * (index + 1) / rows
    if bottom <= top:
        return None
    return (block[0], top, block[2], bottom)


@dataclass(frozen=True)
class Block:
    """A table's printed heading, and the table it heads."""

    table: str
    tokens: tuple[str, ...]


def block_region(anchors: dict[str, Anchor], heads, height: float,
                 floor: float = 0.90):
    """The area a table heading owns: down to the next heading, right to the
    next heading on its own line.

    Side-by-side tables are the reason for the second half of that rule. On
    Rev. 7/5/66 the tubing record and the producing-interval record share a
    y band, and a rule that only looked downward would give each of them a
    band of zero height.
    """
    placed = [(box, name) for name, box in heads.items() if box]
    placed.sort(key=lambda item: ((item[0][1] + item[0][3]) / 2, item[0][0]))
    out = {}
    for index, (box, name) in enumerate(placed):
        centre_y = (box[1] + box[3]) / 2
        below = [b for b, _ in placed if (b[1] + b[3]) / 2 > centre_y + height]
        bottom = min([b[1] for b in below], default=floor)
        beside = [b for b, _ in placed
                  if abs((b[1] + b[3]) / 2 - centre_y) <= height
                  and b[0] > box[0]]
        right = min([b[0] for b in beside], default=PAGE_RIGHT)
        top = box[3]
        if bottom <= top or right <= box[0]:
            continue
        out[name] = (box[0], top, right, bottom)
    return out
