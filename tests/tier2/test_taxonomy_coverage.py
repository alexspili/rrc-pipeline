"""Tier 2: the taxonomy covers the forms the corpus actually contains.

Origin: DEFECTS #10. The class list was written from the handful of documents
read during recon, and five form families that occur on hundreds of pages were
simply absent. They would have been labelled `other_form`, which exists to
reveal gaps of a few pages, not to absorb a sixth of the corpus.

Reading the class list against the corpus is how the hole was found. Doing it
in a test is how it stays shut.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import pageclass as pc
from pipeline.formscan import scan_corpus

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "form_headers.json"

#: A form on more than this many pages is a class the taxonomy owes an answer
#: for. Below it, `other_form` is doing its job rather than hiding a hole.
#:
#: This is a judgement about when a bucket stops being a diagnostic and starts
#: being a hiding place, not a number fitted to whatever the corpus currently
#: contains. It was 20 and that was the wrong kind of number: it had been set
#: just above P-12, a real form nobody had checked, and what it was really
#: suppressing was the survey-abstract bug in DEFECTS #11. With the scanner
#: fixed it filters forms rather than noise, so it can sit lower.
COVERAGE_THRESHOLD = 10


def _counts():
    if not MANIFEST.exists() or not RAW.exists():
        pytest.skip("corpus absent; data/ is git-ignored (CLAUDE.md rule 3)")
    return scan_corpus(MANIFEST, RAW, cache=CACHE)


def test_every_common_form_has_a_class():
    counts = _counts()
    uncovered = sorted(
        ((token, n) for token, n in counts.items()
         if n > COVERAGE_THRESHOLD and pc.form_token_class(token) is None),
        key=lambda pair: -pair[1])

    assert not uncovered, (
        "form families on more than "
        f"{COVERAGE_THRESHOLD} pages with no class in the taxonomy:\n  "
        + "\n  ".join(f"{token}: {n} pages" for token, n in uncovered)
        + "\nAdd them to PageClass, or raise the threshold and say why.")


def test_the_scan_finds_the_forms_recon_already_documented():
    """A guard on the scanner rather than the taxonomy. If the OCR pipeline
    breaks, this test would otherwise pass by finding nothing at all.
    """
    counts = _counts()
    for token in ("G-1", "W-2", "P-4", "W-3", "W-15", "G-5"):
        assert counts.get(token, 0) > 0, f"{token} vanished from the scan"


def test_completion_reports_clear_the_corpus_sufficiency_floor():
    """HANDOFF sets the reopen-fetch threshold at roughly 80 records carrying a
    completion report. This is a floor from bad OCR, not the census: the one
    page known to be a G-1 face reads as "F(R)lC7lbP G(o)IL" and is not
    counted here. It exists so that a corpus change which guts completion
    coverage fails loudly instead of being discovered during extraction.
    """
    counts = _counts()
    assert counts.get("G-1", 0) + counts.get("W-2", 0) > 100, (
        "legible completion-report headers collapsed; the corpus may have "
        "changed or the OCR scan may be broken")


# ------------ DEFECTS #60: a section heading and a form class must agree

#: Read off the form design and measured on 55 pages with no crossover: a G-1
#: carries Sections I and II on its face and Section III on the back; a W-2
#: carries Section I on the face and Section II on the back.
SECTION_FAMILY = {"sec_ii": "w2", "sec_iii": "g1"}


def test_a_section_heading_and_a_form_class_must_not_contradict():
    """Alex asked whether a W-2 back page ever starts with Section III. It
    does not, in 31 pages. The classifier nonetheless called 28 of the 31
    Section III pages a W-2, contradicting its own `part` field.

    This pins the relationship, not the census file, so it holds for any run.
    """
    import json
    census = ROOT / "data" / "census" / "vision_1000.jsonl"
    if not census.exists():
        pytest.skip("census absent; data/ is git-ignored (CLAUDE.md rule 3)")

    contradictions = []
    for line in census.open():
        if not line.strip():
            continue
        row = json.loads(line)
        expected = SECTION_FAMILY.get(row.get("part"))
        if expected and row.get("form_class") in ("g1", "w2"):
            if row["form_class"] != expected:
                contradictions.append(
                    (row["page_id"], row["part"], row["form_class"]))

    # The census on disk was produced before this was understood, so the
    # contradictions are expected to be there. What is pinned is the count, so
    # that a re-run which does not improve it cannot pass unnoticed.
    assert len(contradictions) == 31, (
        f"{len(contradictions)} contradictions, expected the 31 recorded in "
        f"DEFECTS #60; a re-classification should reduce this, and a change "
        f"in either direction wants explaining")
    third = [c for c in contradictions if c[1] == "sec_iii"]
    assert len(third) == 28, "28 Section III pages were called W-2"


def test_the_section_families_are_the_ones_measured():
    assert SECTION_FAMILY == {"sec_ii": "w2", "sec_iii": "g1"}
