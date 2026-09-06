"""Tier 2: the development probe reports what it measured.

DEFECTS #54. The probe found one false positive and printed "Zero of 517" two
lines below the line that said 1, because the rule-of-three sentence was
written assuming the answer. And the one row that mattered was labelled with
only the first record of a cross-record pair, so the result could not be looked
at.

The script is read as text and its helpers are exercised directly; no corpus is
needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "probe_paper.py"


def _probe():
    spec = importlib.util.spec_from_file_location("probe_paper", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_pair_label_names_both_sides():
    """A cross-record pair labelled with one record id reads as two pages of
    one file and is nothing of the sort.
    """
    label = _probe().pair_label("1865938", 0, 2, "1500687", 1, 1)
    assert "1865938" in label and "1500687" in label
    assert label.count("p") >= 2


def test_a_same_file_pair_is_still_readable():
    label = _probe().pair_label("1495414", 0, 6, "1495414", 0, 7)
    assert "1495414" in label
    assert "6" in label and "7" in label


def test_the_false_positive_bound_uses_the_measured_count():
    """Zero events licenses a bound. One event does not license the same one,
    and the sentence must not say it does.
    """
    bound = _probe().false_positive_bound
    assert "below" in bound(0, 517)
    assert "0.58%" in bound(0, 517)

    # The failure was a sentence claiming zero events while one was reported.
    # It is the CLAIM that must not appear; the word may, and here it appears
    # in "Not zero, and not to be reported as zero", which is the point.
    one = bound(1, 517)
    assert "Zero of" not in one
    assert one.startswith("1 of 517")
    assert "0.58%" not in one, "one event must not license the zero-event bound"


def test_the_bound_says_so_when_there_is_nothing_to_bound():
    assert "no" in _probe().false_positive_bound(0, 0).lower()
