"""Tier 2: the census run's guards, not its arithmetic.

`pageclass.aggregate` is already pinned in tier 1. What is covered here is the
two things that make the headline number trustworthy: that every manifest page
is accounted for, and that the sample offered for hand-verification is drawn
honestly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import census
from pipeline import pageclass as pc


def _label(record_id, page, form_class, file_index=0):
    return pc.PageLabel(
        record_id=record_id, file_index=file_index, page=page,
        form_class=form_class,
        part=pc.Part.FACE if form_class in pc.PART_REQUIRED else None,
        orientation=pc.Orientation.UP, confidence=pc.Confidence.HIGH)


def _pages(spec):
    return [(r, f, p, Path("x.pdf")) for r, f, p in spec]


# ------------------------------------------------------------- reconciliation

def test_a_fully_covered_corpus_reconciles():
    pages = _pages([("1", 0, 1), ("1", 0, 2)])
    labels = [_label("1", 1, pc.PageClass.G1), _label("1", 2, pc.PageClass.PLAT_MAP)]
    problems = census.reconcile(pages, labels, {})
    assert [p for p in problems if "neither a label" in p] == []


def test_a_page_that_produced_nothing_at_all_is_caught():
    """A census quietly covering 3,600 of 3,689 pages is not a census, and
    nothing else in the pipeline would notice.
    """
    pages = _pages([("1", 0, 1), ("1", 0, 2), ("1", 0, 3)])
    labels = [_label("1", 1, pc.PageClass.G1)]
    problems = census.reconcile(pages, labels, {"1-0-2": "boom"})
    assert any("neither a label nor an error" in p for p in problems)
    assert any("1-0-3" in p for p in problems)


def test_an_errored_page_still_counts_as_accounted_for():
    pages = _pages([("1", 0, 1)])
    problems = census.reconcile(pages, [], {"1-0-1": "unparseable"})
    assert [p for p in problems if "neither a label" in p] == []


def test_a_result_for_a_page_not_in_the_manifest_is_caught():
    pages = _pages([("1", 0, 1)])
    labels = [_label("1", 1, pc.PageClass.G1), _label("9", 9, pc.PageClass.G1)]
    problems = census.reconcile(pages, labels, {})
    assert any("not in the manifest" in p for p in problems)


# ------------------------------------------------------------ verification set

def test_the_sample_only_offers_records_actually_counted():
    """It exists to catch over-counting, so it must draw from the records the
    census claims have a completion report and nothing else.
    """
    labels = [_label("1", 1, pc.PageClass.G1),
              _label("2", 1, pc.PageClass.W2),
              _label("3", 1, pc.PageClass.PLAT_MAP),
              _label("4", 1, pc.PageClass.W15)]
    sample = census.verification_sample(labels, size=10)
    assert {r for r, _ in sample} == {"1", "2"}


def test_the_sample_shows_the_pages_that_caused_the_count():
    """A human verifying "does this record contain a completion report" needs
    the page the classifier based that on, not the record's first page.
    """
    labels = [_label("1", 4, pc.PageClass.G1),
              _label("1", 9, pc.PageClass.W2),
              _label("1", 1, pc.PageClass.SEPARATOR_CARD)]
    (record_id, pages), = census.verification_sample(labels, size=10)
    assert record_id == "1"
    assert sorted(p.page for p in pages) == [4, 9]


def test_the_sample_is_seeded_and_therefore_reproducible():
    """Chosen before anyone saw which records looked convincing."""
    labels = [_label(str(i), 1, pc.PageClass.G1) for i in range(40)]
    first = census.verification_sample(labels, size=15, seed=1)
    second = census.verification_sample(labels, size=15, seed=1)
    third = census.verification_sample(labels, size=15, seed=2)
    assert [r for r, _ in first] == [r for r, _ in second]
    assert [r for r, _ in first] != [r for r, _ in third]


def test_the_sample_does_not_exceed_what_exists():
    labels = [_label(str(i), 1, pc.PageClass.G1) for i in range(3)]
    assert len(census.verification_sample(labels, size=15)) == 3


def test_no_completion_reports_means_nothing_to_verify():
    labels = [_label("1", 1, pc.PageClass.PLAT_MAP)]
    assert census.verification_sample(labels, size=15) == []
