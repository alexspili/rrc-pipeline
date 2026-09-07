"""Tier 3: the district 02 adjacent sitting, scored against the rule fixed
before it ran.

`make eval`. Nothing here recomputes a decision. The rule is in
docs/labeling-protocol-adjacent.md, written before any pair was drawn; the
mechanism was frozen in commit 1a0182976062931bdcf416f3a104975f91d3cac6; the
verdicts were sealed and hashed at ceb7e34c8c448196 before Alex saw an image.

**Result: the rule passed, on both halves, and three things it turned up
matter more than the pass.** The adjacent false-confirmation rate is 20 times
the cross-record one as a point estimate and cannot be told apart from it at
this denominator. The three-way label collapsed: `same-bundle` was never used,
so the confusion the label existed to detect was not measured. And the parity
of the first page predicts same-sheet far better than the mechanism does.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "adjacent_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "adjacent_sitting_verdicts.json"

SEALED_SHA = "ceb7e34c8c448196"
MAX_FALSE = 1
MIN_CONFIRMED = 2
MIN_DENOMINATOR = 8
CANNOT_TELL_TRIP = 0.30


def upper_bound(k: int, n: int, alpha: float = 0.05) -> float:
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        tail = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i)
                   for i in range(k + 1))
        low, high = (mid, high) if tail > alpha else (low, mid)
    return high


def _need(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} absent; data/ is git-ignored "
                    "(CLAUDE.md rule 3)")


def rows() -> dict:
    _need(SHEET)
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    return {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}


def sealed() -> dict:
    _need(VERDICTS)
    return json.loads(VERDICTS.read_text())["verdicts"]


def call(row) -> str:
    return (row["verdict"] or "").strip().lower()


def test_the_sealed_verdicts_are_the_ones_the_sheet_went_out_with():
    if not VERDICTS.exists():
        pytest.skip("verdicts absent")
    blob = json.loads(VERDICTS.read_text())
    recomputed = hashlib.sha256(
        json.dumps(blob["verdicts"], sort_keys=True).encode()).hexdigest()
    assert recomputed == blob["sha256"]
    assert recomputed.startswith(SEALED_SHA)


def test_the_labels_are_trustworthy_enough_to_score():
    sheet = rows()
    unsure = sum(1 for r in sheet.values() if call(r) == "cannot-tell")
    assert unsure / len(sheet) <= CANNOT_TELL_TRIP
    assert unsure == 3 and len(sheet) == 40


def test_the_pre_registered_rule_passed_on_both_halves():
    """One clause, a conjunction: at most one confirmation among pairs judged
    not one sheet, and at least two among pairs judged same-sheet with a
    denominator of eight.
    """
    sheet, verdicts = rows(), sealed()
    same = [k for k in verdicts if call(sheet[k]) == "same-sheet"]
    notsame = [k for k in verdicts
               if call(sheet[k]) in ("different", "same-bundle")]

    false_confirmations = [k for k in notsame if verdicts[k]["confirmed"]]
    confirmed = [k for k in same if verdicts[k]["confirmed"]]

    assert len(notsame) == 20 and len(false_confirmations) == 1
    assert len(same) == 17 and len(confirmed) == 3

    assert len(false_confirmations) <= MAX_FALSE
    assert len(confirmed) >= MIN_CONFIRMED
    assert len(same) >= MIN_DENOMINATOR


def test_the_safety_half_passed_at_exactly_the_bar():
    """It cleared by nothing. One false confirmation against a bar of one, and
    the bar was set where it was because zero was not attainable. Recorded so
    the pass is not read as headroom.
    """
    assert MAX_FALSE == 1


def test_the_adjacent_rate_is_twenty_times_the_cross_record_one():
    """The point estimate, and why it settles nothing.

    1 of 20 is 5.0% against 1 of 400, which is 0.25%. But 20 pairs licenses a
    95% upper bound of 21.6%, and the cross-record bound of 1.18% sits inside
    that interval. The protocol said in advance that 40 pairs could detect a
    gross difference and could not show the regimes are similar. It did
    neither, and that was foreseen rather than discovered.
    """
    assert round(1 / 20, 4) == 0.05
    assert round(upper_bound(1, 20), 3) == 0.216
    assert upper_bound(1, 400) < 0.05 < upper_bound(1, 20)


def test_the_three_way_label_collapsed_and_measured_nothing():
    """`same-bundle` existed to catch the machine's one predicted failure: a
    staple goes through every sheet of a bundle, so bundle-mates carry marks in
    matching places. It was used zero times in 40 pairs.

    So the sitting did not measure that confusion. Whether the distinction was
    not visible, not present, or folded into `different` is unknown, and no
    number here bears on DEFECTS #63's prediction.
    """
    sheet = rows()
    assert Counter(call(r) for r in sheet.values())["same-bundle"] == 0


def test_page_parity_predicts_same_sheet_better_than_the_mechanism():
    """The largest thing the sitting found, and it costs nothing to compute.

    Pairs whose first page is even are same-sheet 14 of 19; pairs whose first
    page is odd, 3 of 18. Fisher exact two-sided p = 0.0008. That is what would
    be seen if these files open with a separator card, shifting every sheet
    boundary by one.

    It was pre-registered as a secondary analysis and decides nothing here.
    These labels are independent of the mechanism, unlike the 9.73% against
    5.91% across the frame that suggested it.
    """
    sheet, verdicts = rows(), sealed()
    tally = Counter()
    for item, v in verdicts.items():
        if call(sheet[item]) in ("same-sheet", "different", "same-bundle"):
            tally[v["starts_on"], call(sheet[item]) == "same-sheet"] += 1
    even = tally[("even", True)], tally[("even", True)] + tally[("even", False)]
    odd = tally[("odd", True)], tally[("odd", True)] + tally[("odd", False)]
    assert even == (14, 19)
    assert odd == (3, 18)
    assert even[0] / even[1] > 4 * (odd[0] / odd[1])

    # and the mechanism, on the same pairs, confirms 3 of 17
    same = [k for k in verdicts if call(sheet[k]) == "same-sheet"]
    assert sum(1 for k in same if verdicts[k]["confirmed"]) == 3


def test_the_channel_is_still_wired_into_nothing():
    """DEFECTS #66 leaves the hole open, so passing the bar does not license
    wiring it in. Asserted rather than intended.
    """
    import inspect

    from pipeline import reassemble
    source = inspect.getsource(reassemble)
    assert "compare_small" not in source
    assert "small_marks" not in source
