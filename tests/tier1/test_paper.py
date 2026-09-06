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
    mask, cx, cy = disc(notches=[(40.0, 14, 0.12), (200.0, 9, 0.10)])
    stack_mate = profile_of(mask, cx, cy)            # same rim, never flipped
    front = profile_of(mask, cx, cy)
    a = [mark(mask, cx, cy, x=0.2, y=0.1),
         mark(mask, cx, cy, x=0.6, y=0.1)]
    b = [paper.Mark(x=0.2, y=0.1, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(stack_mate)),
         paper.Mark(x=0.6, y=0.1, area_in2=0.05, fill=0.8, kind="hole",
                    outline=tuple(stack_mate))]
    verdict = paper.compare(a, b)
    assert not verdict.confirmed
    assert "margin" in verdict.reason
    assert paper.correlate(front, stack_mate) > 0.9   # raw score would confirm


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
