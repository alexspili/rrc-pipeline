#!/usr/bin/env python3
"""Are these two page images the front and back of one sheet of paper?

Pure numeric. No I/O, no model calls, no file paths: callers hand in arrays.

**Why this exists.** Reassembly pairs pages by comparing identity fields, and
those fields describe the *well*. A file holds several filings for one well, so
agreement between them is guaranteed rather than informative. Identity fields
can only **exclude** — a contradiction proves not-a-pair — and nothing in them
can ever **confirm**. Only the paper can. A punch through old paper tears a
particular rim, and the back of that sheet carries the same rim mirrored.

**A punch hole is only one kind of mark.** The corner blot on record 1495414
matched front-to-back with a margin of +1.162, against +0.459 for the punch
hole on the same sheet, so this module reads every solid mark and does not care
which kind it is. That matters for more than sensitivity: a stack of sheets
punched in one stroke shares its holes and shares no stain, which is why two
agreeing marks are required rather than one.

**The statistic is the margin, never the raw score.** Measured on file
1495414-0: three unrelated sheets from the same stack scored 0.53 to 0.57 raw,
as high as a true pair. What separates them is which transform wins. A true
pair matches *mirrored*, because someone turned the sheet over; a stack-mate
matches *plain*, because both were scanned face up.

**The transform is predicted, never searched.** Allowing a rotation offset
search lifted the controls to +0.42 and +0.49 and destroyed the separation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Angles sampled around a mark. 720 is one sample every half degree, which is
#: finer than any tear the 300 dpi scans resolve.
SAMPLES = 720

#: Harmonics removed before correlating: 0 is the mean, 1 is the centre offset,
#: 2 is ellipticity from scan skew. A one-pixel centring error injects a pure
#: cosine that survives mirroring and would lift unrelated pairs. Measured:
#: removing them holds a true pair at 0.619 and drops that same pair's
#: unmirrored score from 0.295 to 0.164.
STRIP = 2

#: Smallest mark worth reading, square inches, and the shape it has to have.
#: Together these are the envelope of physical damage to paper, and their job
#: is to keep **printing** out (DEFECTS #53).
#:
#: The area floor sits where measurement put the gap: individual bold glyphs on
#: page 6 of 1495414 run 750 to 1,500 px and real marks start at 4,292. It was
#: 0.008 in² (720 px) and let every bold letter through.
#:
#: Area alone cannot do it. An underline joins a text line into one component,
#: and the operator's address on that page came through at **5,628 px, larger
#: than either punch hole**. Shape separates them: that line's bounding box is
#: 465x38, an aspect of 12.2, against 1.3 for the corner blot and 1.1 for the
#: punch holes. A limit of 3 removes every text line and printed rule on both
#: pages and keeps every real mark.
#:
#: Known cost, recorded rather than discovered later: **staple holes are below
#: this floor** and this module cannot read them. Bold glyphs are the same size
#: and pass every other test, so the floor cannot be lowered to recover them.
#: Staples need their own discriminator and do not have one.
MIN_MARK_AREA = 0.02
MAX_ASPECT = 3.0

#: Ink density, filled area over bounding box. A printed form rule is one
#: enormous hollow shape at 0.03 to 0.12; the 1495414 corner blot is 0.37 on
#: both sides of the sheet.
MIN_FILL = 0.30

#: What makes a mark a punch hole rather than a blot: round, solid, and the
#: size of a punch. Recorded because the kind travels into the report, not
#: because the two are treated differently.
HOLE_FILL = 0.65
HOLE_ASPECT = 1.4
HOLE_AREA = (0.02, 0.10)

#: Two marks can be the same mark only if their areas agree this well. In the
#: probe this alone rejected two stack-mates that had cleared the margin: 11 px
#: and 1,682 px against the true blot's 11,282.
AREA_RATIO = 1.6

#: And only if they land this close once the transform is applied, as a
#: fraction of the page. The verified corner blot landed 0.026 in away.
POSITION_TOLERANCE = 0.02

#: How far the two scans may be cropped differently. A rigid offset is a
#: property of the scanner, not of the sheet, so it is estimated and removed.
MAX_OFFSET = 0.06

#: Two marks minimum. One agreeing mark can be the punch stroke rather than
#: the sheet, because a stack punched together shares its holes.
MIN_MARKS_AGREEING = 2

#: FROZEN 2026-09-06 by scripts/probe_paper.py, before any held-out pair was
#: drawn. Every constant above is frozen with it, and the pre-registration in
#: docs/labeling-protocol-paper.md pins the commit that implements `compare`,
#: because a frozen number on an unfrozen statistic is not a firewall.
#:
#: **This number is barely constrained by evidence, and saying so is the
#: point.** Over 517 hard negatives, after the ambiguity rule of DEFECTS #55,
#: **not one negative ever reached two agreeing marks at all**. So no negative
#: has ever been held out by this threshold; they are held out by
#: MIN_MARKS_AGREEING and by the ambiguity rule. The threshold has one
#: empirical constraint and it is an upper bound from a single true pair:
#: 1495414 p6+p7 has a second margin of 0.359, so a threshold above that
#: refuses the only pair the mechanism currently confirms.
#:
#: 0.30 is therefore the value every development measurement was taken under,
#: with 0.059 of headroom below the one positive. It is not a value the
#: negative distribution chose, because the negative distribution never had an
#: opinion. The held-out run is what gives it one.
MARGIN_THRESHOLD = 0.30

#: Turning a sheet over is a reflection, and the operator may turn it about
#: either edge, so both of these are legitimate and both are tried.
TRANSFORMS = {
    "flip_v": lambda x, y: (x, 1.0 - y),
    "flip_h": lambda x, y: (1.0 - x, y),
}

#: The transforms a turned-over sheet CANNOT produce, because turning paper
#: over always reverses orientation. Two options on each side, so the real side
#: is handed no freedom the control lacks.
CONTROLS = {
    "same": lambda x, y: (x, y),
    "rot180": lambda x, y: (1.0 - x, 1.0 - y),
}


@dataclass(frozen=True)
class Mark:
    """One solid mark on a page, and the shape of its edge."""

    x: float
    y: float
    area_in2: float
    fill: float
    kind: str                       # "hole" | "blot"
    outline: tuple[float, ...]      # distance to edge by angle, harmonics gone


@dataclass(frozen=True)
class Verdict:
    """What the paper says, and why.

    `reason` is populated on success as well as failure. A mechanism that
    explains itself only when it declines is one nobody can audit.
    """

    confirmed: bool
    reason: str
    margins: tuple[float, ...] = ()
    transform: str | None = None
    marks_agreeing: int = 0
    marks_compared: int = 0

    #: Marks the winning transform mapped onto a twin of their own page, and
    #: so could not be used (DEFECTS #55). Reported because "nothing paired"
    #: and "nothing was allowed to pair" are different facts, and a refusal
    #: that conflates them cannot be audited.
    marks_ambiguous: int = 0


# ------------------------------------------------------------ shape of an edge

def outline_profile(mask, cx: float, cy: float, samples: int = SAMPLES,
                    max_radius: float = 400.0):
    """Distance from a centre to the edge of the mark it sits in, by angle.

    Rays are walked outward until they leave the mark. Star-convex shapes are
    described exactly; a lobed blot is described approximately, which is
    acceptable because the comparison is between two readings of the same
    shape and the approximation is the same on both sides.
    """
    mask = np.asarray(mask)
    height, width = mask.shape
    out = np.zeros(samples)
    for i, theta in enumerate(np.linspace(0, 2 * np.pi, samples,
                                          endpoint=False)):
        dx, dy = np.cos(theta), np.sin(theta)
        r = 0.0
        while r < max_radius:
            x, y = int(round(cx + dx * r)), int(round(cy + dy * r))
            if not (0 <= x < width and 0 <= y < height) or not mask[y, x]:
                break
            r += 0.5
        out[i] = r
    return out


def strip_harmonics(profile, k: int = STRIP):
    """Remove the mean, the centre offset and the ellipticity.

    What is left is the tear, which is the only part that identifies a sheet.
    """
    profile = np.asarray(profile, dtype=float)
    spectrum = np.fft.rfft(profile)
    spectrum[:k + 1] = 0
    return np.fft.irfft(spectrum, len(profile))


def orient(profile, transform: str):
    """A profile as it appears after the sheet has been through `transform`.

    An angle theta maps differently under each: reflection about the
    horizontal axis sends theta to -theta, reflection about the vertical axis
    sends it to pi - theta, and a half turn sends it to theta + pi.
    """
    profile = np.asarray(profile, dtype=float)
    half = len(profile) // 2
    if transform == "flip_v":
        return profile[::-1]
    if transform == "flip_h":
        return np.roll(profile[::-1], half)
    if transform == "rot180":
        return np.roll(profile, half)
    if transform == "same":
        return profile
    raise ValueError(f"unknown transform {transform!r}")


def correlate(a, b) -> float:
    """Pearson correlation, or NaN when one side carries no shape at all.

    NaN rather than 0.0 on purpose: an undamaged rim and a rim that disagrees
    are different facts, and only the second is evidence.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape or a.size == 0:
        return float("nan")
    if a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ------------------------------------------------------------ finding the marks

def solid_marks(mask, dpi: float = 300.0) -> list[Mark]:
    """Every solid mark on a page, largest first.

    A morphological opening runs before labelling so that a mark touching a
    printed rule keeps its own identity. Without it the mark is absorbed into
    an eight-inch-wide component and thrown away with it, which is what lost
    both punch holes on 1495414 page 7 and what stopped the 2026-09-04 attempt.
    """
    from scipy import ndimage

    mask = np.asarray(mask, dtype=bool)
    height, width = mask.shape
    opened = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    labels, _ = ndimage.label(opened)

    out: list[Mark] = []
    for index, box in enumerate(ndimage.find_objects(labels), start=1):
        blob = labels[box] == index
        area = int(blob.sum())
        if area < MIN_MARK_AREA * dpi * dpi:
            continue
        box_h = box[0].stop - box[0].start
        box_w = box[1].stop - box[1].start
        if box_h == 0 or box_w == 0:
            continue
        fill = area / (box_h * box_w)
        if fill < MIN_FILL:
            continue
        # Damage to paper is roughly equant. Printing is not: a text line or a
        # printed rule runs 12:1 and 180:1 (DEFECTS #53).
        if max(box_h, box_w) / min(box_h, box_w) > MAX_ASPECT:
            continue
        cy, cx = ndimage.center_of_mass(blob)
        cx, cy = box[1].start + cx, box[0].start + cy
        area_in2 = area / dpi ** 2
        round_and_solid = (fill >= HOLE_FILL
                           and max(box_h, box_w) / min(box_h, box_w)
                           <= HOLE_ASPECT
                           and HOLE_AREA[0] <= area_in2 <= HOLE_AREA[1])
        profile = strip_harmonics(outline_profile(opened, cx, cy))
        out.append(Mark(x=cx / width, y=cy / height, area_in2=area_in2,
                        fill=fill, kind="hole" if round_and_solid else "blot",
                        outline=tuple(profile)))
    return sorted(out, key=lambda m: -m.area_in2)


# ---------------------------------------------------------------- the comparison

def _compatible(a: Mark, b: Mark) -> bool:
    smaller = min(a.area_in2, b.area_in2)
    if smaller <= 0:
        return False
    return max(a.area_in2, b.area_in2) / smaller <= AREA_RATIO


def ambiguous_under(mark: Mark, page: list[Mark], transform: str) -> bool:
    """Does the transform map this mark onto another mark of its own page?

    If it does, the mechanism cannot tell the mark from its twin, and its
    agreement says nothing about which sheet this is.

    Origin: DEFECTS #55. A two-hole punch is symmetric about the page centre
    line, so `flip_h` maps each hole onto the other hole and the positional
    pairing succeeds between any two punched pages in the archive. That is how
    two sheets from different counties were confirmed as one sheet.
    """
    move = TRANSFORMS.get(transform) or CONTROLS[transform]
    tx, ty = move(mark.x, mark.y)
    for other in page:
        if other is mark:
            continue
        if not _compatible(mark, other):
            continue
        if ((other.x - tx) ** 2 + (other.y - ty) ** 2) ** 0.5 < \
                POSITION_TOLERANCE:
            return True
    return False


def pair_marks(a: list[Mark], b: list[Mark], transform: str):
    """Marks of b that land on a mark of a, once b's page is turned over.

    Greedy and one-to-one, so a page speckled with identical blobs cannot
    manufacture agreement. A rigid offset between the two scans is estimated
    from the marks themselves and removed first; the crop is a property of the
    scanner and is not evidence about the sheet.

    Marks the transform maps onto a twin of their own page are dropped first
    (DEFECTS #55): under such a transform the pairing constrains nothing, and
    R2's division of labour — position pairs, the outline decides — has quietly
    stopped holding.
    """
    move = TRANSFORMS.get(transform) or CONTROLS[transform]
    a = [m for m in a if not ambiguous_under(m, a, transform)]
    b = [m for m in b if not ambiguous_under(m, b, transform)]
    moved = [(m, move(m.x, m.y)) for m in b]

    offsets = {(0.0, 0.0)}
    for mark, (tx, ty) in moved:
        for other in a:
            if not _compatible(mark, other):
                continue
            dx, dy = other.x - tx, other.y - ty
            if abs(dx) <= MAX_OFFSET and abs(dy) <= MAX_OFFSET:
                offsets.add((round(dx, 5), round(dy, 5)))

    best: list[tuple[Mark, Mark]] = []
    for dx, dy in offsets:
        taken: set[int] = set()
        pairs: list[tuple[Mark, Mark]] = []
        for mark, (tx, ty) in sorted(moved, key=lambda p: -p[0].area_in2):
            tx, ty = tx + dx, ty + dy
            choice, closest = None, POSITION_TOLERANCE
            for i, other in enumerate(a):
                if i in taken or not _compatible(mark, other):
                    continue
                distance = ((other.x - tx) ** 2 + (other.y - ty) ** 2) ** 0.5
                if distance < closest:
                    choice, closest = i, distance
            if choice is not None:
                taken.add(choice)
                pairs.append((a[choice], mark))
        if len(pairs) > len(best):
            best = pairs
    return best


def _margin(front: Mark, back: Mark, transform: str) -> float:
    """How much better the real transform explains this pair than any control.

    This is the statistic. The raw correlation is not, because a stack of
    sheets punched in one stroke scores 0.53 to 0.57 on it.
    """
    real = correlate(np.asarray(front.outline),
                     orient(back.outline, transform))
    if np.isnan(real):
        return float("nan")
    controls = [correlate(np.asarray(front.outline),
                          orient(back.outline, name)) for name in CONTROLS]
    controls = [c for c in controls if not np.isnan(c)]
    if not controls:
        return float("nan")
    return real - max(controls)


def compare(a: list[Mark], b: list[Mark],
            threshold: float = MARGIN_THRESHOLD,
            minimum: int = MIN_MARKS_AGREEING) -> Verdict:
    """Do these two pages carry the same marks, seen from opposite sides?

    Confirms only when at least `minimum` marks agree under a single
    transform, each clearing `threshold` on the margin. Everything else
    abstains with a named reason: this module never asserts that two pages are
    different, because a mark it failed to find is not evidence of anything
    (R3).
    """
    a, b = list(a), list(b)
    if not a or not b:
        empty = "both pages" if not a and not b else ("the first page"
                                                      if not a else
                                                      "the second page")
        return Verdict(confirmed=False,
                       reason=f"no mark found on {empty}")
    if min(len(a), len(b)) < minimum:
        return Verdict(confirmed=False, marks_compared=min(len(a), len(b)),
                       reason=f"too few marks: {len(a)} and {len(b)}, "
                              f"{minimum} needed on each side")

    # Best of the two real transforms, ranked on how many marks clear the
    # margin and then on how many were paired at all, so that a refusal still
    # reports how much evidence it actually looked at.
    # Seeded from the first transform rather than from zeros: when nothing
    # pairs under either flip, a zero-initialised best is never replaced and
    # the count of marks set aside as ambiguous is silently reported as none.
    best: tuple[int, int, tuple[float, ...], str | None, int] | None = None
    set_aside = 0
    for transform in TRANSFORMS:
        dropped = (sum(1 for m in a if ambiguous_under(m, a, transform))
                   + sum(1 for m in b if ambiguous_under(m, b, transform)))
        # The most any single flip had to set aside, not the winner's count:
        # the winning flip is usually the one that had to set aside nothing,
        # so reporting its zero hides the reason the other flip was refused.
        set_aside = max(set_aside, dropped)
        pairs = pair_marks(a, b, transform)
        margins = [_margin(front, back, transform) for front, back in pairs]
        clearing = tuple(sorted((m for m in margins
                                 if not np.isnan(m) and m >= threshold),
                                reverse=True))
        candidate = (len(clearing), len(pairs), clearing, transform, dropped)
        if best is None or candidate[:2] > best[:2]:
            best = candidate

    _, compared, margins, transform, _ = best
    dropped = set_aside
    if len(margins) >= minimum:
        return Verdict(confirmed=True, reason="marks agree under one flip",
                       margins=margins, transform=transform,
                       marks_agreeing=len(margins), marks_compared=compared,
                       marks_ambiguous=dropped)

    # "Nothing paired" and "nothing was allowed to pair" are different facts.
    if not compared:
        note = (f"no mark could be paired under either flip; {dropped} were "
                f"set aside as ambiguous under it (DEFECTS #55)"
                if dropped else "no mark could be paired under either flip")
    else:
        note = (f"only {len(margins)} of {compared} paired marks cleared the "
                f"margin threshold {threshold}, {minimum} needed")
    return Verdict(
        confirmed=False, margins=margins, transform=transform,
        marks_agreeing=len(margins), marks_compared=compared,
        marks_ambiguous=dropped, reason=note)
