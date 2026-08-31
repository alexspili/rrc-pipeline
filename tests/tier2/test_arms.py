"""Tier 2: the arm competition's arithmetic.

The decision rule was recorded before any arm ran (docs/modules/classify.md).
These tests pin the two pieces of it that could quietly go wrong: which arm
counts as cheapest, and whether a gap between two arms is real at this sample
size.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "run_arms", ROOT / "scripts" / "run_arms.py")
run_arms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_arms)


def _row(page_id, form_class, tokens_in, tokens_out=40):
    return {"page_id": page_id, "form_class": form_class,
            "input_tokens": tokens_in, "output_tokens": tokens_out}


# ------------------------------------------------------------------- costing

def test_arm_cost_uses_list_prices_on_measured_tokens():
    per_page, priced = run_arms.arm_cost(
        [_row("1-0-1", "g1", 1_000_000, 1_000_000)])
    assert priced == 1
    assert per_page == 6.00          # $1/MTok in + $5/MTok out


def test_arm_cost_ignores_rows_that_never_reached_the_model():
    rows = [_row("1-0-1", "g1", 2000), {"page_id": "1-0-2", "error": "boom"}]
    _, priced = run_arms.arm_cost(rows)
    assert priced == 1


def test_arms_are_ranked_by_measured_cost():
    """Origin: DEFECTS #9 and classify.md R10. The text arm is cheapest across
    the corpus and was the most expensive of the three on the first page
    probed, so a hardcoded cheapest-first order is an assumption wearing a
    constant's clothes. Here the text arm is deliberately the dearest.
    """
    all_rows = {
        "text": [_row("1-0-1", "g1", 9000)],
        "vision_1000": [_row("1-0-1", "g1", 1546)],
        "vision_1568": [_row("1-0-1", "g1", 2078)],
    }
    assert run_arms.rank_by_cost(all_rows) == [
        "vision_1000", "vision_1568", "text"]


# ------------------------------------------------------- paired significance

def _truth(**pages):
    return {page_id: {"form_class": cls, "part": "", "orientation": "up"}
            for page_id, cls in pages.items()}


def test_identical_arms_are_indistinguishable():
    truth = _truth(**{f"1-0-{i}": "g1" for i in range(1, 21)})
    rows = [_row(f"1-0-{i}", "g1", 1500) for i in range(1, 21)]
    result = run_arms.mcnemar(rows, list(rows), truth)
    assert result["discordant"] == 0
    assert result["p_value"] == 1.0
    assert result["difference"] == 0.0


def test_a_small_edge_on_sixty_pages_is_not_distinguishable():
    """Three pages of disagreement, two of them favouring the costlier arm, is
    a +1.7pp difference and nothing at all. This is the case the standing
    instruction is about: it must not read as a win.
    """
    truth = _truth(**{f"1-0-{i}": "g1" for i in range(1, 61)})
    cheap = [_row(f"1-0-{i}", "g1" if i > 3 else "w2", 1000)
             for i in range(1, 61)]
    dear = [_row(f"1-0-{i}", "g1" if i != 1 else "w2", 2000)
            for i in range(1, 61)]
    result = run_arms.mcnemar(cheap, dear, truth)
    assert result["b"] == 0 and result["c"] == 2
    assert result["difference"] < 0.05
    assert result["p_value"] > 0.05


def test_a_real_separation_is_distinguishable():
    truth = _truth(**{f"1-0-{i}": "g1" for i in range(1, 61)})
    cheap = [_row(f"1-0-{i}", "g1" if i > 15 else "w2", 1000)
             for i in range(1, 61)]
    dear = [_row(f"1-0-{i}", "g1", 2000) for i in range(1, 61)]
    result = run_arms.mcnemar(cheap, dear, truth)
    assert result["c"] == 15 and result["b"] == 0
    assert result["p_value"] < 0.001
    assert result["difference"] == 0.25


def test_pages_without_ground_truth_are_not_scored():
    """The run covers the smoke slice too, and those pages have no label. They
    must not enter the comparison as silent agreements.
    """
    truth = _truth(**{"1-0-1": "g1"})
    rows_a = [_row("1-0-1", "g1", 1000), _row("9-0-9", "plat_map", 1000)]
    rows_b = [_row("1-0-1", "g1", 2000), _row("9-0-9", "schematic", 2000)]
    assert run_arms.mcnemar(rows_a, rows_b, truth)["n"] == 1


# ------------------------------------------------------ winner selection

def _scores(**pairs):
    return {arm: {"class_accuracy": acc, "n": 58} for arm, acc in pairs.items()}


def test_a_distinguishable_win_is_not_discarded_because_another_arm_is_contested():
    """Origin: DEFECTS #13. On the first real run vision_1000 beat text by
    16.1pp at p=0.004, and vision_1568 beat it by 13.0pp at p=0.109. The
    contested loop reset the winner to cheapest for any contested arm, so the
    decisive win was thrown away and the run reported "WINNER: text, no gap
    survived the paired test" while printing p=0.004 four lines above.
    """
    decision = run_arms.decide(
        ranked=["text", "vision_1000", "vision_1568"],
        scores=_scores(text=0.667, vision_1000=0.828, vision_1568=0.797),
        paired={"vision_1000": {"p_value": 0.004, "discordant": 9},
                "vision_1568": {"p_value": 0.109, "discordant": 10}})
    assert decision["winner"] == "vision_1000"
    assert "vision_1568" in decision["contested"]
    assert "vision_1000" not in decision["contested"]


def test_the_cheapest_arm_wins_when_no_gap_is_distinguishable():
    decision = run_arms.decide(
        ranked=["text", "vision_1000"],
        scores=_scores(text=0.70, vision_1000=0.78),
        paired={"vision_1000": {"p_value": 0.20, "discordant": 6}})
    assert decision["winner"] == "text"
    assert decision["contested"] == ["vision_1000"]


def test_a_gap_inside_five_points_is_not_contested_merely_unproven():
    """Under 5pp the rule already says cheapest wins, so there is nothing to
    flag. A contested flag there would cry wolf on every run.
    """
    decision = run_arms.decide(
        ranked=["text", "vision_1000"],
        scores=_scores(text=0.70, vision_1000=0.73),
        paired={"vision_1000": {"p_value": 0.40, "discordant": 4}})
    assert decision["winner"] == "text"
    assert decision["contested"] == []


def test_the_best_distinguishable_arm_wins_not_merely_the_first():
    decision = run_arms.decide(
        ranked=["text", "vision_1000", "vision_1568"],
        scores=_scores(text=0.60, vision_1000=0.70, vision_1568=0.85),
        paired={"vision_1000": {"p_value": 0.01, "discordant": 12},
                "vision_1568": {"p_value": 0.001, "discordant": 20}})
    assert decision["winner"] == "vision_1568"
