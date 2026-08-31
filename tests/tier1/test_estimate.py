"""Tier 1: a stratified proportion weights by the corpus, not by our effort.

Pure arithmetic, no I/O. Written before any stage-2 label exists, so the
metric cannot be adjusted once a number is on the table.
"""

from __future__ import annotations

import math

import pytest

from pipeline.estimate import (Stratum, design_standard_error,
                               stratified_proportion)


def test_a_stratum_drawn_whole_has_no_sampling_error():
    """Stratum D is 7 pages and all 7 are labelled. There is nothing left to
    be uncertain about, and the finite-population correction has to say so.
    """
    whole = Stratum("D", frame_size=7, sampled=7, hits=5)
    assert whole.variance == 0.0
    estimate = stratified_proportion([whole])
    assert estimate.proportion == pytest.approx(5 / 7)
    assert estimate.standard_error == 0.0


def test_strata_are_weighted_by_frame_size_not_by_sample_size():
    """The failure this exists to prevent: 8 of 46 and 25 of 113 pooled raw
    would let the thinly sampled stratum speak for a quarter of the answer
    instead of the 29% of the frame it actually is.
    """
    corroborated = Stratum("E", frame_size=46, sampled=8, hits=8)     # p = 1.0
    silent = Stratum("C", frame_size=113, sampled=25, hits=15)        # p = 0.6
    estimate = stratified_proportion([corroborated, silent])

    expected = (46 / 159) * 1.0 + (113 / 159) * 0.6
    assert estimate.proportion == pytest.approx(expected)

    pooled = (8 + 15) / (8 + 25)
    assert estimate.proportion != pytest.approx(pooled)


def test_the_finite_population_correction_shrinks_the_error_bar():
    """Stratum A draws 22 of 43. Treating that as a draw from an infinite
    population overstates the standard error by about a third.
    """
    small_frame = Stratum("A", frame_size=43, sampled=22, hits=16)
    big_frame = Stratum("A", frame_size=43_000, sampled=22, hits=16)
    assert small_frame.variance < big_frame.variance

    p = 16 / 22
    uncorrected = p * (1 - p) / 21
    assert big_frame.variance == pytest.approx(uncorrected, rel=0.01)
    assert small_frame.variance == pytest.approx(uncorrected * (1 - 22 / 43))


def test_a_sample_bigger_than_its_frame_is_refused():
    """Not a hypothetical. The frame is recomputed from the census by the
    tier-2 validator, and a census rerun that moved a page between strata
    would show up exactly here.
    """
    with pytest.raises(ValueError, match="recomputed after the draw"):
        Stratum("A", frame_size=43, sampled=44, hits=0)


def test_more_hits_than_pages_is_refused():
    with pytest.raises(ValueError, match="hits in"):
        Stratum("A", frame_size=43, sampled=22, hits=23)


def test_a_single_draw_from_a_larger_stratum_is_refused():
    """One page gives a proportion of 0 or 1 and no way to say how uncertain
    it is. Silently reporting zero variance there would be a lie in the
    direction that flatters the design.
    """
    with pytest.raises(ValueError, match="no estimable within-stratum variance"):
        Stratum("tiny", frame_size=40, sampled=1, hits=1)

    entire = Stratum("tiny", frame_size=1, sampled=1, hits=1)
    assert entire.variance == 0.0


def test_duplicate_stratum_names_are_refused():
    with pytest.raises(ValueError, match="duplicate stratum names"):
        stratified_proportion([Stratum("A", 43, 22, 10),
                               Stratum("A", 29, 8, 4)])


def test_an_empty_estimate_is_refused():
    with pytest.raises(ValueError, match="no strata"):
        stratified_proportion([])


# --------------------------------------------- the allocation's own promise

#: Straight out of docs/labeling-protocol-stage2.md, with the proportions the
#: census verification suggests: about 0.75 where the printed form number did
#: not survive imaging, about 0.95 where it did.
G1_FACE_PLAN = [("A", 43, 22, 0.75), ("B", 29, 8, 0.95)]
W2_FACE_PLAN = [("C", 113, 25, 0.85), ("D", 7, 7, 0.85), ("E", 46, 8, 0.95)]


def test_the_allocation_delivers_the_error_bar_the_protocol_claims():
    """The protocol claims about 4.8pp on each face precision. That claim is
    a property of the allocation, so it is pinned here rather than being
    recomputed by hand if the allocation is ever edited.
    """
    for plan in (G1_FACE_PLAN, W2_FACE_PLAN):
        assert design_standard_error(plan) == pytest.approx(0.048, abs=0.004)


def test_the_lean_allocation_would_have_been_worse():
    """Recorded because the smaller option was on the table and declined. If
    someone later trims the draw to save labelling time, this is what it costs.
    """
    lean_g1 = [("A", 43, 18, 0.75), ("B", 29, 6, 0.95)]
    assert design_standard_error(lean_g1) > design_standard_error(G1_FACE_PLAN)
    assert design_standard_error(lean_g1) == pytest.approx(0.056, abs=0.006)


def test_percent_formatting_carries_the_error_bar():
    estimate = stratified_proportion([Stratum("A", 43, 22, 16),
                                      Stratum("B", 29, 8, 8)])
    assert "+/-" in estimate.as_percent()
    assert math.isfinite(estimate.standard_error)


def test_a_planned_proportion_is_not_rounded_to_whole_pages():
    """Found by the test above before this module was committed. Rounding
    0.95 across 8 draws gives 8 hits, a proportion of 1.0 and a variance of
    zero, so the plan claimed a precision the allocation cannot deliver.
    """
    thin = [("B", 29, 8, 0.95)]
    assert design_standard_error(thin) > 0.0
    assert design_standard_error(thin) == pytest.approx(0.0701, abs=0.001)
