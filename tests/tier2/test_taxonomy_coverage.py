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
