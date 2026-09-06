"""Tier 3: the held-out sitting, scored against the rule fixed before it ran.

`make eval`. This is the first thing in tier 3; the directory has existed and
been empty since the repo was laid out.

Nothing here recomputes a decision. The rule is in
docs/labeling-protocol-paper.md, the mechanism was frozen in commit
4868fdd3f714a38f9117b81b2b1c5f57a7c2b642, and the verdicts were sealed and
hashed before Alex saw the sheet. These tests assert the outcome so that a
later change to the module has to face it rather than quietly rescore it.

**Result: the mechanism does not ship.** Part A passed with zero false
confirmations in 325 held-out guaranteed-false pairs. Part B failed at 4 of 16.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "tests" / "fixtures" / "paper_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"

#: Pre-registered before the sheet was drawn.
SEALED_SHA = "943d12256c7e20de"
MIN_DENOMINATOR = 8
CANNOT_TELL_TRIP = 0.30


def _need(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} absent; data/ is git-ignored "
                    "(CLAUDE.md rule 3)")


def rows() -> dict:
    _need(SHEET)
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    return {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}


def verdicts() -> dict:
    _need(VERDICTS)
    return json.loads(VERDICTS.read_text())["verdicts"]


def call(row) -> str:
    return (row["verdict"] or "").strip().lower()


def test_the_sealed_verdicts_are_the_ones_the_sheet_went_out_with():
    """If these moved, the sitting proves nothing and the scoring is void."""
    blob = json.loads(VERDICTS.read_text()) if VERDICTS.exists() else None
    if blob is None:
        pytest.skip("verdicts absent")
    recomputed = hashlib.sha256(
        json.dumps(blob["verdicts"], sort_keys=True).encode()).hexdigest()
    assert recomputed == blob["sha256"]
    assert recomputed.startswith(SEALED_SHA)


def test_the_labels_are_trustworthy_enough_to_score():
    """Pre-registered: above 30% cannot-tell the sitting is inconclusive
    because the labels cannot carry a result."""
    sheet = rows()
    unsure = sum(1 for r in sheet.values() if call(r) == "cannot-tell")
    assert unsure / len(sheet) <= CANNOT_TELL_TRIP


def test_part_a_found_no_false_confirmation():
    """325 guaranteed-false pairs from the sitting's own records, plus the 8
    the human labelled not-same-sheet. The safety property held everywhere it
    was tested, including 517 development negatives.
    """
    sheet, sealed = rows(), verdicts()
    wrong = [k for k, v in sealed.items()
             if v["confirmed"] and call(sheet[k]) == "not-same-sheet"]
    assert wrong == []


def test_part_b_failed_the_pre_registered_bar():
    """4 of 16, against a rule needing at least half of at least 8.

    Asserted rather than written down in prose so that a later change to the
    module cannot quietly restate this sitting as a pass.
    """
    sheet, sealed = rows(), verdicts()
    same = [k for k, v in sealed.items() if call(sheet[k]) == "same-sheet"]
    confirmed = [k for k in same if sealed[k]["confirmed"]]
    assert len(same) >= MIN_DENOMINATOR, "the denominator was large enough"
    assert len(same) == 16 and len(confirmed) == 4
    assert 2 * len(confirmed) < len(same), "this sitting did not pass"


def test_the_pre_registered_rule_failed_and_alex_shipped_it_anyway():
    """Both facts, and they are not in tension.

    The conjunction failed: Part A passed, Part B did not. That is recorded
    above and is not rewritten.

    Alex then shipped it, on 2026-09-06, on a quantity the bar never measured.
    "At least half of the pairs judged same-sheet" compares the mechanism to a
    perfect one; what decides is whether it adds correct attachments the
    current system misses. Of the 16 same-sheet pairs, reassembly attaches
    NONE and the paper confirms four, so all four are additions (DEFECTS #58).

    This test exists so that neither half of that can be quietly dropped: not
    the failure, and not the reason it shipped regardless.
    """
    sheet, sealed = rows(), verdicts()
    same = [k for k, v in sealed.items() if call(sheet[k]) == "same-sheet"]
    confirmed = [k for k in same if sealed[k]["confirmed"]]
    assert 2 * len(confirmed) < len(same), "the bar failed"
    assert len(confirmed) == 4, "and four correct additions is why it shipped"


def test_reassembly_takes_the_confirmer_without_depending_on_it():
    """Shipped as a caller-supplied callable, so `pipeline/reassemble.py` stays
    pure and tier-1 testable and the default behaviour is unchanged.
    """
    import inspect

    from pipeline import reassemble
    assert "confirms" in inspect.signature(reassemble.group).parameters
    source = Path(reassemble.__file__).read_text()
    assert "import paper" not in source and "papermatch" not in source


def test_the_human_judged_on_a_channel_the_module_cannot_read():
    """The finding that explains the failure, pinned so it is not forgotten:
    15 of 16 same-sheet calls cite staple marks, and staples sit below
    MIN_MARK_AREA where bold printed glyphs live, so the floor cannot be
    lowered to reach them.
    """
    sheet, sealed = rows(), verdicts()
    same = [k for k, v in sealed.items() if call(sheet[k]) == "same-sheet"]
    citing = sum(1 for k in same
                 if "staple" in (sheet[k]["evidence"] or "").lower())
    assert citing >= 0.75 * len(same), Counter(
        (sheet[k]["evidence"] or "none").lower() for k in same)
