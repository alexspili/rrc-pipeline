"""Tier 3: the pre-registered held-out run of the small-mark channel.

`make eval`. Nothing here recomputes a decision. The rule is in
docs/labeling-protocol-staple.md, written before any held-out record was
scored; the mechanism and every constant were frozen first, in commit
1a0182976062931bdcf416f3a104975f91d3cac6. These tests assert the outcome so
that a later change to the channel has to face it rather than restate it.

**Result: the rule passed, and the one failure showed a hole.** 1 false
confirmation in 400 guaranteed-false cross-record pairs from the 111 held-out
records, a 95% upper bound of 1.180% against a bar of 2%. The pair that fired
had all four of its agreeing marks in one edge band, where flip_v leaves the x
coordinate untouched and constrains nothing (DEFECTS #63).

Both facts are asserted here. Neither may be dropped: not the pass, and not
the reason the pass is narrower than it looks.
"""

from __future__ import annotations

import math
from pathlib import Path

from pipeline import paper

ROOT = Path(__file__).resolve().parents[2]

#: Pre-registered in docs/labeling-protocol-staple.md before the run.
FROZEN_AT = "1a0182976062931bdcf416f3a104975f91d3cac6"
BOUND_REQUIRED = 0.02

#: The run. 400 pairs, two different records with different leases, drawn only
#: from the held-out half of tests/fixtures/paper_record_split.csv.
HELD_OUT_PAIRS = 400
HELD_OUT_FALSE_CONFIRMATIONS = 1

#: Development, for contrast. Never blended with the above.
DEVELOPMENT = {"same_sheet_fired": 4, "same_sheet_total": 16,
               "not_same_sheet_fired": 0, "not_same_sheet_total": 8,
               "cross_record_fired": 0, "cross_record_total": 120}


def upper_bound(k: int, n: int, alpha: float = 0.05) -> float:
    """The largest rate whose chance of producing k or fewer is still alpha."""
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        tail = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i)
                   for i in range(k + 1))
        low, high = (mid, high) if tail > alpha else (low, mid)
    return high


def test_the_pre_registered_rule_passed():
    """One clause: a 95% upper bound below 2% on the held-out cross-record
    false-confirmation rate."""
    bound = upper_bound(HELD_OUT_FALSE_CONFIRMATIONS, HELD_OUT_PAIRS)
    assert bound < BOUND_REQUIRED
    assert round(bound, 5) == 0.0118


def test_the_bar_was_a_bound_because_zero_was_not_attainable():
    """DEFECTS #51 applied before the bar was written. At the modelled
    per-pair rate the expected count over 400 pairs is 1.8, so a bar of "zero
    false confirmations" would have been unreachable, which is exactly the
    mistake the reassembly pre-registration made in the other direction.
    """
    modelled_per_pair = 0.0046
    assert HELD_OUT_PAIRS * modelled_per_pair > 1.0, (
        "if zero were attainable the bar should have been zero")
    assert upper_bound(3, HELD_OUT_PAIRS) < BOUND_REQUIRED, (
        "and the bar must not have been trivially loose either")


def test_the_reachability_model_understated_the_risk():
    """What the run's one failure cost the protocol, kept beside the pass.

    The 0.46% per-pair figure came from a two-dimensional catchment. The
    channel's own edge filter confines candidates to a rim, and along a rim a
    flip parallel to it constrains one coordinate instead of two: simulated at
    the observed counts, 0.62% spread over the sheet against 85.65% confined
    to one band. The measurement stands; the model behind the bar does not.
    """
    assert 0.8565 > 0.0062 * 100, "the banded case is two orders of magnitude worse"


def test_the_development_numbers_are_not_the_held_out_ones():
    """They answer different questions and are never blended. Development owns
    reach, which is not measured held out because every positive in existence
    has been judged; held out owns safety.
    """
    assert DEVELOPMENT["same_sheet_fired"] == 4
    assert DEVELOPMENT["same_sheet_total"] == 16
    assert DEVELOPMENT["cross_record_fired"] == 0
    assert HELD_OUT_FALSE_CONFIRMATIONS == 1
    assert upper_bound(0, DEVELOPMENT["cross_record_total"]) > 0.02, (
        "0 of 120 licenses nothing better than 3%, and never 'no false "
        "positives'")


def test_the_channel_is_wired_into_nothing():
    """It changes no output, and DEFECTS #63 says it may not until the edge
    band hole is closed and measured. Asserted rather than intended.
    """
    import inspect

    from pipeline import reassemble
    source = inspect.getsource(reassemble)
    assert "compare_small" not in source
    assert "small_marks" not in source


def test_the_frozen_constants_are_still_the_frozen_ones():
    """A frozen number on an unfrozen statistic is not a firewall, so the
    functions are named here too."""
    assert paper.SMALL_AREA_IN2 == (25.0 / 300.0 ** 2, paper.MIN_MARK_AREA)
    assert paper.SMALL_EDGE_IN == 0.8
    assert paper.MIN_SMALL_AGREEING == 2
    assert paper.SMALL_TOLERANCE == 0.008
    for name in ("sheet_region", "small_marks", "small_agreeing",
                 "compare_small"):
        assert callable(getattr(paper, name)), name
    assert len(FROZEN_AT) == 40


# ------------------------------------------------- DEFECTS #64, 2026-09-07

#: Measured on the 91 development records after Alex asked whether the channel
#: should read the whole page rather than only its periphery.
PERIPHERY = {"same_sheet": 4, "not_same_sheet": 0, "cross_record": 1}
WHOLE_PAGE = {"same_sheet": 5, "not_same_sheet": 0, "cross_record": 7}
DEVELOPMENT_CROSS_RECORD_PAIRS = 120


def test_the_edge_filter_earns_its_place_on_selectivity():
    """It went into the code as a physical claim, that staples and punches sit
    near edges. That claim died with the staple model. What it actually does is
    keep the candidate list short: about 6 candidates a page against about 45
    for the whole page, so roughly fifty times fewer chances for two accidental
    agreements.

    Reading the whole page buys one true confirmation and costs six false ones.
    The filter survives on a different argument from the one that put it there,
    and this test is where that argument is written down.
    """
    assert WHOLE_PAGE["same_sheet"] - PERIPHERY["same_sheet"] == 1
    assert WHOLE_PAGE["cross_record"] - PERIPHERY["cross_record"] == 6
    assert (upper_bound(WHOLE_PAGE["cross_record"],
                        DEVELOPMENT_CROSS_RECORD_PAIRS)
            > BOUND_REQUIRED), "the whole page would not have passed the bar"
    assert (upper_bound(PERIPHERY["cross_record"],
                        DEVELOPMENT_CROSS_RECORD_PAIRS)
            > BOUND_REQUIRED), (
        "and 120 pairs licenses nothing either way; only the 400 held-out "
        "pairs carry the safety claim")


def test_the_band_effect_is_not_what_governs_the_false_rate():
    """DEFECTS #63 presented it as the explanation and proposed an
    axis-degeneracy rule as the fix. Across every false confirmation on record,
    one of nine has its candidates in a band; the other eight are spread 0.908
    to 0.981 across the sheet. The fix would address one case in nine.

    What governs the rate is candidate count, of which the band case is a
    special instance where one coordinate stops counting.
    """
    banded = 1
    total = (HELD_OUT_FALSE_CONFIRMATIONS + PERIPHERY["cross_record"]
             + WHOLE_PAGE["cross_record"])
    assert total == 9
    assert banded / total < 0.2, (
        "if the band case ever becomes the majority, DEFECTS #63's fix "
        "becomes the right one and #64 needs revisiting")
