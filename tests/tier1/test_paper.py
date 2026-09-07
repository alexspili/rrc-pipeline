"""Tier 1 for pipeline.paper: matching two pages by the marks on the paper.

Pure. Synthetic arrays only, no corpus, no model.

The module answers one question: are these two page images the front and back
of ONE sheet? Identity fields can only exclude, because they describe the well
and a file holds several filings for one well. Only the paper can confirm.

The load-bearing tests here are the ones that stop it confirming things it
should not. Two of them encode measurements that already caught the mechanism
lying:

  a stack of sheets punched in one stroke shares its holes, and three unrelated
  sheets scored 0.53 to 0.57 on the raw correlation, as high as a true pair; so
  the statistic is the margin between the flip a sheet can perform and one it
  cannot, never the raw score

  searching over rotations lifted the controls to +0.42 and +0.49 and destroyed
  the separation; so the transform is predicted and never searched
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline import paper


# ---------------------------------------------------------------- synthetic marks

def disc(size=160, radius=50, notches=()):
    """A filled circle, optionally bitten into at given angles.

    Stands in for a punch hole: the circle is the punch, the notches are the
    tear that makes one hole different from another.
    """
    centre = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - centre, yy - centre)
    mask = r <= radius
    angle = np.arctan2(yy - centre, xx - centre)
    for degrees, depth, width in notches:
        target = np.deg2rad(degrees)
        near = np.abs(np.angle(np.exp(1j * (angle - target)))) < width
        mask &= ~(near & (r > radius - depth))
    return mask, float(centre), float(centre)


def profile_of(mask, cx, cy):
    return paper.strip_harmonics(paper.outline_profile(mask, cx, cy))


def mark(mask, cx, cy, x=0.5, y=0.5, area=0.05, kind="hole"):
    return paper.Mark(x=x, y=y, area_in2=area, fill=0.8, kind=kind,
                      outline=tuple(profile_of(mask, cx, cy)))


# ------------------------------------------------------- the outline is a shape

def test_a_notch_shows_up_at_the_angle_it_was_cut():
    """The whole representation rests on this: the profile is the distance from
    the centre to the edge, by angle, so a bite out of the rim is a dip at that
    angle and nowhere else.
    """
    mask, cx, cy = disc(notches=[(90.0, 12, 0.12)])
    raw = paper.outline_profile(mask, cx, cy)
    where = np.argmin(raw) / len(raw) * 360.0
    assert abs(where - 90.0) < 8.0


def test_a_plain_circle_carries_no_shape():
    """An undamaged hole says nothing about which sheet it is in. After the
    harmonics come out it must be flat, not merely small.
    """
    mask, cx, cy = disc()
    assert float(np.std(profile_of(mask, cx, cy))) < 0.5


def test_a_mis_centred_hole_does_not_invent_a_signal():
    """A one-pixel error in the centre injects a pure cosine that survives
    mirroring, so it can lift an unrelated pair. Harmonics 0, 1 and 2 come out
    for that reason; measured, it drops a true pair's own unmirrored score from
    0.295 to 0.164 while leaving the mirrored score alone.
    """
    mask, cx, cy = disc()
    off = paper.strip_harmonics(paper.outline_profile(mask, cx + 3, cy + 3))
    assert float(np.std(off)) < 1.0


# --------------------------------------------- the transforms, and the controls

def test_the_two_flips_are_the_two_ways_to_turn_a_sheet_over():
    assert set(paper.TRANSFORMS) == {"flip_v", "flip_h"}
    assert set(paper.CONTROLS) == {"same", "rot180"}


def test_turning_the_sheet_over_is_recognised():
    """Flip the array the way the paper flips and the profile must line up
    again under the matching operator. This is the positive control for the
    whole orientation apparatus.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    front = profile_of(mask, cx, cy)
    back = profile_of(np.flipud(mask), cx, mask.shape[0] - 1 - cy)
    assert paper.correlate(front, paper.orient(back, "flip_v")) > 0.9

    sideways = profile_of(np.fliplr(mask), mask.shape[1] - 1 - cx, cy)
    assert paper.correlate(front, paper.orient(sideways, "flip_h")) > 0.9


def test_a_control_transform_does_not_match_a_turned_sheet():
    """The controls are the orientation-preserving maps, which paper cannot
    perform between two scans. If they score as well as the real ones the
    statistic is measuring something other than the sheet.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    front = profile_of(mask, cx, cy)
    back = profile_of(np.flipud(mask), cx, mask.shape[0] - 1 - cy)
    for control in paper.CONTROLS:
        assert paper.correlate(front, paper.orient(back, control)) < 0.5


def test_a_rotated_copy_is_not_a_match_under_any_transform():
    """R1, and it is the rule the earlier probe learned the hard way. Rotating
    the search space lifted every control to +0.42 and +0.49. A hole rotated in
    the plane is a different hole and must score as one.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12)])
    turned, _, _ = disc(notches=[(130.0, 14, 0.12)])
    front = profile_of(mask, cx, cy)
    other = profile_of(turned, cx, cy)
    for name in list(paper.TRANSFORMS) + list(paper.CONTROLS):
        assert paper.correlate(front, paper.orient(other, name)) < 0.5


# ------------------------------------------------------ the margin, not the score

def test_the_margin_is_the_statistic_not_the_raw_score():
    """R4. Sheets punched in one stroke share a rim: three unrelated sheets in
    one file scored 0.53 to 0.57 raw, as high as a true pair. What separates
    them is that a true pair matches MIRRORED and a stack-mate matches PLAIN.
    """
    one, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    two, _, _ = disc(notches=[(310.0, 16, 0.14), (95.0, 11, 0.11)])
    front_one, front_two = profile_of(one, cx, cy), profile_of(two, cx, cy)

    # Positions that DO pair under flip_v, so the marks genuinely get compared
    # and the verdict turns on the statistic rather than on the pairing.
    a = [mark(one, cx, cy, x=0.2, y=0.1), mark(two, cx, cy, x=0.6, y=0.1)]
    # ...but the rims are the unflipped ones, as a sheet scanned face up has.
    b = [paper.Mark(x=0.2, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(front_one)),
         paper.Mark(x=0.6, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(front_two))]

    verdict = paper.compare(a, b)
    assert verdict.marks_compared == 2, "the marks must actually be compared"
    assert not verdict.confirmed
    assert "margin" in verdict.reason

    # A rule on the raw correlation would confirm this outright: the rims are
    # identical, so an orientation-blind score is a perfect 1.0.
    assert paper.correlate(front_one, front_one) > 0.99


# --------------------------------------------------- abstention is load-bearing

def test_one_agreeing_mark_is_never_enough():
    """R5. A stack shares its punch holes and shares no stain, so a single
    agreeing mark can be the punch stroke rather than the sheet.
    """
    assert paper.MIN_MARKS_AGREEING >= 2
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12)])
    flipped = np.flipud(mask)
    a = [mark(mask, cx, cy, x=0.2, y=0.1)]
    b = [paper.Mark(x=0.2, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(profile_of(flipped, cx,
                                             mask.shape[0] - 1 - cy)))]
    verdict = paper.compare(a, b)
    assert not verdict.confirmed
    assert verdict.marks_agreeing <= 1


@pytest.mark.parametrize("a,b", [([], []), ([1], [])])
def test_a_page_with_no_marks_abstains_rather_than_denying(a, b):
    """R3. A missed mark must not manufacture evidence. `unknown` with a named
    reason, never `different`.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12)])
    left = [mark(mask, cx, cy)] * len(a)
    right = [mark(mask, cx, cy)] * len(b)
    verdict = paper.compare(left, right)
    assert not verdict.confirmed
    assert verdict.reason
    assert "no mark" in verdict.reason or "too few" in verdict.reason


def test_a_featureless_outline_abstains():
    """Two stack-mates returned NaN in the probe because their mark had no
    variation at all. A correlation that cannot be computed is not a zero.
    """
    flat = tuple(np.zeros(paper.SAMPLES))
    m = paper.Mark(x=0.2, y=0.1, area_in2=0.05, fill=0.8, kind="hole",
                   outline=flat)
    assert np.isnan(paper.correlate(np.array(flat), np.array(flat)))
    verdict = paper.compare([m, m], [m, m])
    assert not verdict.confirmed


# ------------------------------------------------------- pairing marks up first

def test_marks_of_different_size_are_never_paired():
    """R2. Position locates and pairs marks; the outline decides. Two
    stack-mates scored a positive margin in the probe and were rejected on area
    alone: 11 px and 1,682 px against the true blot's 11,282.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    flipped = np.flipud(mask)
    back = profile_of(flipped, cx, mask.shape[0] - 1 - cy)
    a = [mark(mask, cx, cy, x=0.2, y=0.1, area=0.05),
         mark(mask, cx, cy, x=0.6, y=0.1, area=0.05)]
    b = [paper.Mark(x=0.2, y=0.9, area_in2=0.005, fill=0.8, kind="hole",
                    outline=tuple(back)),
         paper.Mark(x=0.6, y=0.9, area_in2=0.005, fill=0.8, kind="hole",
                    outline=tuple(back))]
    assert not paper.compare(a, b).confirmed


def test_one_mark_cannot_explain_two():
    """Pairing is one-to-one, so a page speckled with identical blobs cannot
    manufacture agreement.
    """
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12)])
    flipped = np.flipud(mask)
    back = profile_of(flipped, cx, mask.shape[0] - 1 - cy)
    a = [mark(mask, cx, cy, x=0.2, y=0.1)]
    b = [paper.Mark(x=0.2, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(back)) for _ in range(4)]
    assert paper.compare(a, b).marks_agreeing <= 1


# ------------------------------------------------------------ the positive case

def test_two_agreeing_marks_on_a_turned_sheet_are_confirmed():
    """The case the module exists for: one sheet, scanned front and back."""
    one, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    two, _, _ = disc(notches=[(310.0, 16, 0.14), (95.0, 11, 0.11)])
    height = one.shape[0]
    a = [mark(one, cx, cy, x=0.2, y=0.1), mark(two, cx, cy, x=0.6, y=0.1)]
    b = [paper.Mark(x=0.2, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(profile_of(np.flipud(one), cx,
                                             height - 1 - cy))),
         paper.Mark(x=0.6, y=0.9, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(profile_of(np.flipud(two), cx,
                                             height - 1 - cy)))]
    verdict = paper.compare(a, b)
    assert verdict.confirmed
    assert verdict.transform == "flip_v"
    assert verdict.marks_agreeing >= 2
    assert all(m > paper.MARGIN_THRESHOLD for m in verdict.margins)


# ------------------------------- DEFECTS #53: printing is not damage to paper

def bar(width, height, size=400):
    """A filled rectangle: a line of underlined text, or a printed rule."""
    mask = np.zeros((size, size), dtype=bool)
    top = (size - height) // 2
    left = (size - width) // 2
    mask[top:top + height, left:left + width] = True
    return mask


def test_a_line_of_text_is_not_a_mark_on_the_paper():
    """An underline joins the letters of a text line into one component. On
    page 6 of 1495414 the operator's address came through that way at 5,628 px
    — larger than either punch hole — so no area threshold separates them. Its
    bounding box is 465x38, an aspect of 12.2, against 1.1 for a punch hole.
    """
    marks = paper.solid_marks(bar(465, 38))
    assert marks == [], "a text line was read as a mark on the paper"


def test_a_printed_rule_is_not_a_mark_on_the_paper():
    marks = paper.solid_marks(bar(2342, 13, size=2600))
    assert marks == []


def test_a_bold_glyph_is_not_a_mark_on_the_paper():
    """Individual bold letters passed every test but area, which is why the
    floor is where it is.
    """
    assert paper.solid_marks(bar(30, 40)) == []


def test_a_punch_hole_and_a_blot_both_survive_the_same_filter():
    """The envelope has to keep the real thing. Both shapes are the ones
    measured on 1495414: a 73x79 hole and a 197x148 corner blot.
    """
    hole, cx, cy = disc(size=200, radius=38)
    assert len(paper.solid_marks(hole)) == 1
    assert paper.solid_marks(hole)[0].kind == "hole"

    blot = np.zeros((300, 300), dtype=bool)
    yy, xx = np.mgrid[0:300, 0:300]
    blot |= ((xx - 150) ** 2 / 98 ** 2 + (yy - 150) ** 2 / 74 ** 2) <= 1
    found = paper.solid_marks(blot)
    assert len(found) == 1
    assert found[0].area_in2 > paper.MIN_MARK_AREA


def test_the_shape_envelope_is_stated_as_constants():
    """So a change to it is a diff, not a discovery."""
    assert paper.MAX_ASPECT == 3.0
    assert paper.MIN_MARK_AREA == 0.02


# ------------- DEFECTS #55: a transform that maps a page onto itself proves nothing

def test_a_mark_the_transform_maps_onto_its_own_twin_is_not_evidence():
    """A two-hole punch is symmetric about the page centre line, so flip_h
    maps each hole onto the other hole. The pairing then succeeds between any
    two punched pages and constrains nothing, which is how 1865938-0 p2 and
    1495009-1 p1 -- different leases, different counties -- were confirmed as
    one sheet.
    """
    one, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    two, _, _ = disc(notches=[(310.0, 16, 0.14), (95.0, 11, 0.11)])

    def punched(first, second, flip):
        """Two holes at mirror-symmetric x, as a real punch leaves them."""
        return [paper.Mark(x=0.338, y=0.04, area_in2=0.05, fill=0.75,
                           kind="hole",
                           outline=tuple(profile_of(first, cx, cy))),
                paper.Mark(x=0.672, y=0.04, area_in2=0.05, fill=0.75,
                           kind="hole",
                           outline=tuple(profile_of(second, cx, cy)))]

    a = punched(one, two, False)
    b = punched(one, two, False)
    # Under flip_h each hole lands on the other hole of its OWN page, so both
    # are ambiguous and neither may be used.
    assert paper.pair_marks(a, b, "flip_h") == []
    assert not paper.compare(a, b).confirmed


def test_self_symmetry_is_judged_per_transform_not_globally():
    """The same marks are ambiguous under one flip and perfectly usable under
    the other. Holes along the top edge map to the bottom edge under flip_v,
    where there is nothing to be confused with.
    """
    one, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    two, _, _ = disc(notches=[(310.0, 16, 0.14), (95.0, 11, 0.11)])
    height = one.shape[0]

    def top(first, second):
        return [paper.Mark(x=0.338, y=0.04, area_in2=0.05, fill=0.75,
                           kind="hole",
                           outline=tuple(profile_of(first, cx, cy))),
                paper.Mark(x=0.672, y=0.04, area_in2=0.05, fill=0.75,
                           kind="hole",
                           outline=tuple(profile_of(second, cx, cy)))]

    front = top(one, two)
    back = [paper.Mark(x=0.338, y=0.96, area_in2=0.05, fill=0.75, kind="hole",
                       outline=tuple(profile_of(np.flipud(one), cx,
                                                height - 1 - cy))),
            paper.Mark(x=0.672, y=0.96, area_in2=0.05, fill=0.75, kind="hole",
                       outline=tuple(profile_of(np.flipud(two), cx,
                                                height - 1 - cy)))]
    assert len(paper.pair_marks(front, back, "flip_v")) == 2
    verdict = paper.compare(front, back)
    assert verdict.confirmed
    assert verdict.transform == "flip_v"


def test_the_ambiguity_check_looks_at_area_too():
    """A mark is only confusable with a twin it could actually be mistaken
    for. A hole landing on a blot four times its size is not ambiguous.
    """
    one, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    marks = [paper.Mark(x=0.338, y=0.04, area_in2=0.05, fill=0.75,
                        kind="hole", outline=tuple(profile_of(one, cx, cy))),
             paper.Mark(x=0.662, y=0.04, area_in2=0.40, fill=0.40,
                        kind="blot", outline=tuple(profile_of(one, cx, cy)))]
    assert not paper.ambiguous_under(marks[0], marks, "flip_h")


# ------------------------------------ the frozen mechanism, 2026-09-06

def test_the_frozen_constants_are_the_ones_measured_under():
    """FROZEN before any held-out pair was drawn. A change to any of these is
    a change to the statistic the pre-registration pinned, and it invalidates
    the held-out run rather than improving it.
    """
    assert paper.MARGIN_THRESHOLD == 0.30
    assert paper.MIN_MARKS_AGREEING == 2
    assert paper.MIN_MARK_AREA == 0.02
    assert paper.MAX_ASPECT == 3.0
    assert paper.MIN_FILL == 0.30
    assert paper.AREA_RATIO == 1.6
    assert paper.POSITION_TOLERANCE == 0.02
    assert paper.MAX_OFFSET == 0.06
    assert paper.SAMPLES == 720
    assert paper.STRIP == 2


def test_the_threshold_still_admits_the_one_pair_it_confirms():
    """The threshold's only empirical constraint is an upper bound from a
    single true pair: 1495414 p6+p7 has a second margin of 0.359. Above that
    the mechanism confirms nothing at all, which is the vacuous pass the
    pre-registration exists to forbid.
    """
    assert paper.MARGIN_THRESHOLD < 0.359


def test_the_statistic_is_frozen_not_just_the_number():
    """A frozen threshold on an unfrozen statistic is not a firewall. These
    are the pieces that define what the number is a number OF.
    """
    assert set(paper.TRANSFORMS) == {"flip_v", "flip_h"}
    assert set(paper.CONTROLS) == {"same", "rot180"}
    for name in ("outline_profile", "strip_harmonics", "orient", "correlate",
                 "ambiguous_under", "pair_marks", "compare", "solid_marks"):
        assert callable(getattr(paper, name)), name


# ---------------------------- DEFECTS #61: read the page at its own resolution

def test_the_area_floor_is_read_at_the_page_s_own_resolution():
    """MIN_MARK_AREA is square inches, so it has to be converted with the
    resolution of the page it is applied to.

    Measured: 53 of 3,689 corpus pages are 200 dpi, every one of them inside a
    file that is otherwise 300 dpi. Converted at an assumed 300, the floor on
    those pages is 1,800 px, which is 0.045 in² at 200 dpi.
    """
    # 0.02 in² is 800 px at 200 dpi and 1,800 px at 300. A disc sized between
    # the two is a mark on one page and not on the other, and the only thing
    # that decides is which resolution the page was scanned at.
    mask, _, _ = disc(size=100, radius=20)
    area = int(mask.sum())
    assert paper.MIN_MARK_AREA * 200 ** 2 < area < paper.MIN_MARK_AREA * 300 ** 2

    assert paper.solid_marks(mask, dpi=200.0), (
        f"{area} px is over the 0.02 in² floor at 200 dpi and must be found")
    assert not paper.solid_marks(mask, dpi=300.0), (
        f"{area} px is under it at 300 dpi and must not be")


def test_one_physical_mark_read_at_two_resolutions_still_pairs():
    """The damaging half of #61. `area_in2` is area/dpi**2, so if the detector
    is told 300 for a page scanned at 200, one physical mark reports 2.25x
    smaller on one side of the pair than the other. AREA_RATIO is 1.6, so
    `_compatible` refuses it and a true pair straddling the change cannot be
    confirmed at all. Eleven adjacent corpus pairs straddle it.
    """
    shape, _, _ = disc(size=300, radius=60, notches=[(40.0, 14, 0.12)])
    small, _, _ = disc(size=200, radius=40, notches=[(40.0, 14, 0.12)])

    told_wrong = paper.solid_marks(small, dpi=300.0)
    at_300 = paper.solid_marks(shape, dpi=300.0)
    assert at_300, "the 300 dpi side is over the floor"
    assert told_wrong, "and so is the 200 dpi side, even read at the wrong dpi"
    assert not paper._compatible(at_300[0], told_wrong[0]), (
        "this is the defect: told the wrong resolution, one physical mark is "
        "not compatible with itself")

    told_right = paper.solid_marks(small, dpi=200.0)
    assert told_right
    assert paper._compatible(at_300[0], told_right[0]), (
        f"read at its own resolution it must pair: "
        f"{at_300[0].area_in2:.4f} in² against {told_right[0].area_in2:.4f}")


def test_a_half_turn_never_moves_a_page_between_the_two_sets():
    """Why a page stored upside down costs nothing, and a quarter turn does.

    The two legitimate flips are closed under rot180 and so are the two
    controls: rot180 after flip_v is flip_h, and rot180 after `same` is
    rot180. A 180 degree difference in how two pages were stored therefore
    permutes within each set and never moves a page from the legitimate set
    into the control set.

    Measured on the corpus, 2.9% of adjacent pairs differ by a quarter turn,
    which the mechanism cannot read and abstains on; half-turn differences are
    harmless and need no handling. Written down because the census records an
    `orientation` per page and nothing in this module consults it, and the
    reason that is safe is this closure rather than luck.
    """
    half = paper.CONTROLS["rot180"]
    points = [(0.13, 0.29), (0.71, 0.04), (0.5, 0.5), (0.02, 0.97)]

    for group in (paper.TRANSFORMS, paper.CONTROLS):
        for name, move in group.items():
            other = [t for t in group if t != name][0]
            composed = [half(*move(x, y)) for x, y in points]
            expected = [group[other](x, y) for x, y in points]
            assert np.allclose(composed, expected), f"rot180 after {name}"


# ================================================== the small-mark channel

def speck(size, x, y, radius=4):
    """One small round mark, drawn into a page-sized mask."""
    yy, xx = np.mgrid[0:size[0], 0:size[1]]
    return np.hypot(xx - x, yy - y) <= radius


def blank_sheet(height=3300, width=2550, border=60):
    """A sheet inset in a dark scanner field, which is what the scans are."""
    page = np.ones((height, width), dtype=bool)
    page[border:height - border, border:width - border] = False
    return page


def test_the_sheet_is_found_inside_the_scanner_field():
    """The scans are bilevel with a dark backing, so everything outside the
    paper is 'ink'. Without finding the sheet, the surround is one enormous
    mark and every coordinate is measured against the wrong frame.
    """
    page = blank_sheet()
    sheet = paper.sheet_region(page)
    assert sheet[1600, 1200], "the middle of the paper is on the sheet"
    assert not sheet[10, 10], "the scanner field is not"


def test_a_mark_under_the_solid_floor_is_found_here_and_not_there():
    """The two channels partition the marks by area, so neither can ever count
    the other's. That is what stops a speck being used as one of compare()'s
    two agreeing marks, where a shared punch stroke is already the hazard.
    """
    page = blank_sheet()
    page |= speck(page.shape, 200, 200, radius=6)          # ~113 px
    small = paper.small_marks(page)
    assert len(small) == 1
    assert small[0].area_in2 < paper.MIN_MARK_AREA
    assert paper.solid_marks(page) == []


def test_the_two_channels_never_see_the_same_mark():
    """Asserted on one array carrying both sizes, so the partition is a
    property of the code and not of two constants read side by side."""
    page = blank_sheet()
    page |= speck(page.shape, 200, 200, radius=6)           # under the floor
    page |= speck(page.shape, 200, 900, radius=40)          # over it
    small = {round(m.area_in2, 9) for m in paper.small_marks(page)}
    solid = {round(m.area_in2, 9) for m in paper.solid_marks(page)}
    assert small and solid
    assert small.isdisjoint(solid)


def test_the_inside_of_a_run_of_printing_is_removed():
    """The discriminator that does most of the work. Glyphs have neighbours on
    their baseline, leader dots have neighbours along their line, and damage to
    paper has neither. Measured on one real page, this took 2,357 candidates
    to 37.

    **The two ends of a run survive, and that is stated rather than tuned
    away.** A dot at the end of a row has one neighbour, and one neighbour is
    allowed, because a staple's two legs are a pair and must not delete each
    other. So a row of eight leader dots contributes two candidates, not zero.
    What stops those two mattering is not this filter: it is that they must
    then land on a mark of the other page under a flip and not under a
    control, and that at least two must do so at once.

    Tightening MAX_NEIGHBOURS to zero would remove them and would also remove
    every pair. That trade was not made, and this test is where it is written
    down.
    """
    page = blank_sheet()
    for i in range(8):
        page |= speck(page.shape, 200 + i * 60, 200, radius=5)
    kept = paper.small_marks(page)
    assert len(kept) == 2, [round(m.x, 3) for m in kept]
    assert min(m.x for m in kept) < max(m.x for m in kept), "the two ends"

    vertical = blank_sheet()
    for i in range(8):
        vertical |= speck(vertical.shape, 200, 200 + i * 60, radius=5)
    assert len(paper.small_marks(vertical)) == 2, (
        "a vertical run is a run too; keying on baselines alone let whole "
        "columns of leader dots through")


def test_a_dense_block_of_printing_is_removed_entirely():
    """The case the ends-of-a-run allowance does not leak: real text is two
    dimensional, so almost every glyph has two or more neighbours."""
    page = blank_sheet()
    for row in range(4):
        for column in range(8):
            page |= speck(page.shape, 200 + column * 60, 200 + row * 60,
                          radius=5)
    assert paper.small_marks(page) == []


def test_a_mark_in_the_middle_of_the_sheet_is_not_a_candidate():
    page = blank_sheet()
    page |= speck(page.shape, 1275, 1650, radius=6)        # dead centre
    assert paper.small_marks(page) == []


def test_a_turned_sheet_is_confirmed_and_a_copied_one_is_not():
    """The positive control for the channel, and the negative that matters:
    two pages scanned the same way up agree under `same`, which is a control,
    so they are refused however well they agree.
    """
    front = blank_sheet()
    for x, y in [(200, 200), (2350, 250), (250, 3100)]:
        front |= speck(front.shape, x, y, radius=6)

    back = np.flipud(front)
    verdict = paper.compare_small(paper.small_marks(front),
                                  paper.small_marks(back))
    assert verdict.confirmed, verdict.reason
    assert verdict.transform == "flip_v"
    assert verdict.margin > 0

    copy = paper.compare_small(paper.small_marks(front),
                               paper.small_marks(front.copy()))
    assert not copy.confirmed, copy.reason


def test_one_agreeing_small_mark_is_never_enough():
    """R5's reason with no outline to fall back on. Down here a single
    coincidence is cheap: every false agreement seen across 120
    guaranteed-false pairs was one mark.
    """
    front = blank_sheet()
    front |= speck(front.shape, 200, 200, radius=6)
    front |= speck(front.shape, 2350, 250, radius=6)
    back = blank_sheet()
    back |= speck(back.shape, 200, 3099, radius=6)          # mirrors the first
    back |= speck(back.shape, 2350, 2000, radius=6)         # mirrors nothing
    verdict = paper.compare_small(paper.small_marks(front),
                                  paper.small_marks(back))
    assert not verdict.confirmed
    assert verdict.agreeing < paper.MIN_SMALL_AGREEING


def test_a_page_with_too_few_small_marks_abstains_rather_than_denying():
    """R3. A mark under the floor that the detector missed is evidence of
    nothing at all."""
    front = blank_sheet()
    front |= speck(front.shape, 200, 200, radius=6)
    verdict = paper.compare_small(paper.small_marks(front), [])
    assert not verdict.confirmed
    assert "too few" in verdict.reason


def test_no_offset_is_searched_for_the_small_marks():
    """R1 in a new place. Searching a shared rigid offset was measured and it
    lifted the controls: false confirmations went from 0 to 2 of 120
    cross-record pairs and 3 to 11 of 160 same-file pairs, for one extra
    positive. So marks shifted bodily against their own sheet are refused
    rather than rescued.

    A shift of the whole SCAN is a different thing and is absorbed by
    construction, because coordinates are fractions of the sheet's own
    bounding box. What this refuses is a shift of the marks against the sheet.
    """
    front = blank_sheet()
    for x, y in [(200, 200), (2350, 250), (250, 3100)]:
        front |= speck(front.shape, x, y, radius=6)
    back = blank_sheet()
    for x, y in [(290, 3099), (2440, 3049), (340, 199)]:   # mirrored, then +90px
        back |= speck(back.shape, x, y, radius=6)
    verdict = paper.compare_small(paper.small_marks(front),
                                  paper.small_marks(back))
    assert not verdict.confirmed, (
        f"an offset was absorbed somewhere: {verdict.reason}")


def test_the_small_mark_constants_are_stated_in_inches():
    """DEFECTS #61: a constant in pixels means a different thing on the 53
    corpus pages that are 200 dpi, and this channel's whole discriminator is a
    distance. area_in2 is area/dpi**2, so the same pixels are a LARGER mark on
    a lower-resolution scan.
    """
    page = blank_sheet()
    page |= speck(page.shape, 200, 200, radius=6)
    at300 = paper.small_marks(page, dpi=300.0)
    at200 = paper.small_marks(page, dpi=200.0)
    assert at300 and at200
    assert at200[0].area_in2 > at300[0].area_in2


def test_the_small_mark_constants_are_the_ones_measured_under():
    """FROZEN 2026-09-07, before the held-out negatives were run. Every one of
    these was chosen while looking at 91 development records, and the firing
    rule was chosen after seeing both the positive and negative results, so
    they have no held-out support whatever. Changing one invalidates the
    held-out run rather than improving it.
    """
    assert paper.SMALL_AREA_IN2 == (25.0 / 300.0 ** 2, 0.02)
    assert paper.SMALL_AREA_IN2[1] == paper.MIN_MARK_AREA
    assert paper.SMALL_MAX_ASPECT == 2.5
    assert paper.SMALL_EDGE_IN == 0.8
    assert paper.SMALL_RUN_PITCH_IN == 0.35
    assert paper.SMALL_MAX_NEIGHBOURS == 1
    assert paper.SMALL_INSET_IN == 0.03
    assert paper.SMALL_TOLERANCE == 0.008
    assert paper.SMALL_AREA_RATIO == 3.0
    assert paper.MIN_SMALL_AGREEING == 2
    for name in ("sheet_region", "small_marks", "small_agreeing",
                 "compare_small"):
        assert callable(getattr(paper, name)), name


def test_the_small_channel_uses_the_same_transforms_and_controls():
    """It is a different statistic on the same physics. If these ever diverge
    from compare()'s, one of the two is wrong about what paper does."""
    import inspect
    source = inspect.getsource(paper.small_agreeing)
    assert "TRANSFORMS" in source and "CONTROLS" in source


# ------------- DEFECTS #63: a flip along the band the candidates sit in

def test_marks_in_one_edge_band_agree_too_easily_under_the_flip_along_it():
    """The hole the held-out run found, asserted so it cannot be forgotten.

    `SMALL_EDGE_IN` confines candidates to a rim, and a rim is one dimensional.
    `flip_v` leaves x alone, so two marks sharing a vertical band agree in x
    for free and only y has to line up. Simulated at the observed candidate
    counts, two agreements arise 0.62% of the time when marks are spread over
    the sheet and **85.65%** of the time when they share one edge band.

    **This test asserts the defect, not the fix.** The pair below is two
    unrelated sheets and `compare_small` confirms it. The fix is DEFECTS #55's
    rule applied to axes, it has no held-out support, and it waits for the
    district 02 fetch and a new pre-registered run. When it lands, this
    assertion inverts and cites that commit.
    """
    front = blank_sheet()
    back = blank_sheet()
    # Four marks, all on the right-hand edge, from two sheets that share
    # nothing. Only their y values are asked to agree.
    for y in (500, 2100):
        front |= speck(front.shape, 2400, y, radius=6)
    for y in (3299 - 500, 3299 - 2100):
        back |= speck(back.shape, 2400, y, radius=6)

    verdict = paper.compare_small(paper.small_marks(front),
                                  paper.small_marks(back))
    assert verdict.confirmed, (
        "if this now abstains, the axis rule has landed: invert this test and "
        "cite the commit (DEFECTS #63)")
    assert verdict.transform == "flip_v"

    # The x coordinate carried none of it: every mark shares the band.
    marks = paper.small_marks(front)
    assert max(m.x for m in marks) - min(m.x for m in marks) < 0.01


def test_the_edge_band_hole_is_symmetric_between_the_two_turns():
    """DEFECTS #64. #63 was written as a flip_v fault and it is not one.

    A sheet can be turned either way, and each turn leaves one coordinate
    alone. flip_v preserves x, so a left or right edge is cheap. **flip_h
    preserves y, so a top or bottom edge is cheap in exactly the same way.**
    The failing held-out pair happened to be the first kind and I wrote up only
    that kind.

    This is the mirror of
    test_marks_in_one_edge_band_agree_too_easily_under_the_flip_along_it, and
    like it, it asserts the defect rather than a fix.
    """
    front = blank_sheet()
    back = blank_sheet()
    # All four marks along the TOP edge, from two sheets that share nothing.
    # flip_h mirrors x, so only their x values are asked to agree; y is free.
    for x in (500, 2100):
        front |= speck(front.shape, x, 200, radius=6)
    for x in (2049, 449):                       # the mirrored x positions
        back |= speck(back.shape, x, 200, radius=6)

    verdict = paper.compare_small(paper.small_marks(front),
                                  paper.small_marks(back))
    assert verdict.confirmed, (
        "if this now abstains the axis rule has landed: invert this test and "
        "the flip_v one together (DEFECTS #63, #64)")
    assert verdict.transform == "flip_h"

    marks = paper.small_marks(front)
    assert max(m.y for m in marks) - min(m.y for m in marks) < 0.01, (
        "the y coordinate carried none of it: every mark shares the band")
