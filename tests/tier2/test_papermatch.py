"""Tier 2: reading real pages and deciding whether they are one sheet.

Skips when `data/` is absent, which is the repo's pattern for the git-ignored
corpus (CLAUDE.md rule 3). There are deliberately **no page fixtures**. The
first attempt built one by blanking a page and pasting back only what the
detector called a mark, and it shipped an operator's address; tightened, it
still shipped a printed fragment and a handwritten squiggle. Redaction by
detection asks the component whose failure mode is mistaking ink for paper to
certify that it did not (DEFECTS #53). So the real pages stay where they are
and these tests skip without them.

The pair is record 1495414, file 0: page 6 is a G-1 face, page 7 is its
Section III, and they are one sheet. Every other page in that file was punched
in the same stroke, which makes them the hardest negatives available.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import paper, papermatch, render

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"

RECORD, FILE_INDEX = "1495414", 0
FACE, BACK = 6, 7
#: Different sheets from the same file, punched in one stroke with the pair.
STACK_MATES = (3, 4, 5, 8, 9, 12)


def pdf() -> Path:
    if not MANIFEST.exists():
        pytest.skip("manifest absent; data/ is git-ignored (CLAUDE.md rule 3)")
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == RECORD:
            name = json.loads(line)["files"][FILE_INDEX]["name"]
            path = RAW / RECORD / name
            if not path.exists():
                pytest.skip(f"{path} is git-ignored corpus, not present here")
            return path
    pytest.skip(f"record {RECORD} not in this manifest")


def marks(page: int):
    return papermatch.page_marks(pdf(), page)


# ------------------------------------------------------- what a mark actually is

def test_the_detector_finds_the_marks_and_not_the_form():
    """Page 6 carries a torn corner and two punch holes. It also carries a
    whole printed G-1: field labels, rules, checkboxes, an underlined address.
    Before DEFECTS #53 the detector returned 33 marks on this page, most of
    them printing, including the operator's address as a single component
    larger than either punch hole.
    """
    found = marks(FACE)
    assert len(found) == 3, [(m.kind, round(m.area_in2, 4)) for m in found]
    assert sorted(m.kind for m in found) == ["blot", "hole", "hole"]
    assert all(m.area_in2 >= paper.MIN_MARK_AREA for m in found)


def test_the_punch_holes_are_where_the_punch_put_them():
    """Both on the top edge, and the pitch between them is the corpus-wide
    constant. Position is not evidence about which sheet this is -- unrelated
    pages collide 16.9% of the time -- it is only how the holes get paired up.
    """
    holes = [m for m in marks(FACE) if m.kind == "hole"]
    assert len(holes) == 2
    assert all(h.y < 0.06 for h in holes)
    assert abs(holes[0].x - holes[1].x) > 0.25


# ------------------------------------------------------------ the pair, and only it

def test_the_two_sides_of_one_sheet_are_confirmed():
    verdict = paper.compare(marks(FACE), marks(BACK))
    assert verdict.confirmed, verdict.reason
    assert verdict.transform == "flip_v"
    assert verdict.marks_agreeing >= paper.MIN_MARKS_AGREEING


def test_the_margins_are_the_ones_this_was_built_on():
    """A development number, from a record whose marks were inspected by eye.
    Pinned so that a change to the detector or the statistic has to face it.
    """
    verdict = paper.compare(marks(FACE), marks(BACK))
    assert [round(m, 3) for m in verdict.margins] == [0.478, 0.359]


@pytest.mark.parametrize("page", STACK_MATES)
def test_a_sheet_punched_in_the_same_stroke_is_refused(page):
    """The failure the margin exists to prevent. On the raw correlation three
    of these score 0.53 to 0.57, as high as the true pair, because one punch
    stroke through a stack leaves the same rim on every sheet in it.
    """
    verdict = paper.compare(marks(FACE), marks(page))
    assert not verdict.confirmed, (
        f"p{FACE}+p{page} confirmed with margins {verdict.margins}")


def test_the_refusals_say_how_much_evidence_they_looked_at():
    """A refusal that does not report what it compared cannot be audited.

    p6 and p9 are both punched pages, and under flip_h a two-hole punch maps
    each hole onto the other hole of its own page, so every hole is set aside
    as ambiguous (DEFECTS #55). "Nothing paired" and "nothing was allowed to
    pair" are different facts and the refusal has to distinguish them.
    """
    verdict = paper.compare(marks(FACE), marks(9))
    assert not verdict.confirmed
    assert verdict.marks_ambiguous >= 2
    assert "ambiguous" in verdict.reason


def test_a_refusal_on_the_margin_says_so_instead():
    """The other kind of refusal: marks paired, and did not agree well enough.
    It must not be reported as an ambiguity."""
    front, back = marks(FACE), marks(BACK)
    verdict = paper.compare(front, back, threshold=0.99)
    assert not verdict.confirmed
    assert verdict.marks_compared >= 1
    assert "margin" in verdict.reason


# ------------------------------------------------------------------- the cache

def test_the_cache_returns_what_the_detector_returned(tmp_path):
    cache = papermatch.MarkCache(tmp_path)
    fresh = papermatch.page_marks(pdf(), FACE, cache)
    cached = papermatch.page_marks(pdf(), FACE, cache)
    assert len(cached) == len(fresh)
    for a, b in zip(fresh, cached):
        assert (a.kind, round(a.x, 9), round(a.y, 9)) == (
            b.kind, round(b.x, 9), round(b.y, 9))
        assert np.allclose(a.outline, b.outline, atol=1e-4)


def test_a_cached_page_gives_the_same_verdict(tmp_path):
    """CLAUDE.md rule 7 with DEFECTS #14's lesson attached: a cache that
    changes the answer is worse than no cache.
    """
    cache = papermatch.MarkCache(tmp_path)
    live = paper.compare(marks(FACE), marks(BACK))
    warm = papermatch.compare_pages(pdf(), FACE, pdf(), BACK, cache)
    again = papermatch.compare_pages(pdf(), FACE, pdf(), BACK, cache)
    assert warm.confirmed == again.confirmed == live.confirmed
    assert [round(m, 6) for m in again.margins] == [round(m, 6)
                                                    for m in live.margins]


def test_changing_a_detection_constant_invalidates_the_cache(tmp_path,
                                                             monkeypatch):
    """The key holds a hash of the constants, so a threshold change cannot be
    served a page detected under the old one.
    """
    cache = papermatch.MarkCache(tmp_path)
    papermatch.page_marks(pdf(), FACE, cache)
    before = papermatch.DETECTOR
    dpi = papermatch.page_dpi(pdf(), FACE)
    monkeypatch.setattr(papermatch, "DETECTOR", "0000000000000000")
    assert cache.get(render.doc_hash(pdf()), FACE, dpi) is None
    monkeypatch.setattr(papermatch, "DETECTOR", before)
    assert cache.get(render.doc_hash(pdf()), FACE, dpi) is not None


# ------------------------- DEFECTS #61: the page's own resolution, not 300

#: 53 corpus pages are 200 dpi and every one sits inside a file that is
#: otherwise 300. This is one of them, with a 300 dpi page beside it.
MIXED_RECORD, MIXED_FILE = "1498123", 1
PAGE_300, PAGE_200 = 4, 6


def mixed_pdf() -> Path:
    if not MANIFEST.exists():
        pytest.skip("manifest absent; data/ is git-ignored (CLAUDE.md rule 3)")
    for line in MANIFEST.open():
        row = json.loads(line) if line.strip() else None
        if row and row["record_id"] == MIXED_RECORD:
            path = RAW / MIXED_RECORD / row["files"][MIXED_FILE]["name"]
            if not path.exists():
                pytest.skip(f"{path} is git-ignored corpus, not present here")
            return path
    pytest.skip(f"record {MIXED_RECORD} not in this manifest")


def test_the_corpus_really_does_mix_resolutions_inside_one_file():
    """The premise of the defect, asserted rather than remembered."""
    resolutions = render.page_resolutions(mixed_pdf())
    assert resolutions[PAGE_300 - 1] == 300.0
    assert resolutions[PAGE_200 - 1] == 200.0


def test_a_page_is_read_at_its_own_resolution():
    """`page_marks` used to call `solid_marks` with the default dpi of 300 on
    every page. On a 200 dpi page that converts the 0.02 in² floor to 0.045
    in², and it reports every mark 2.25x smaller than it is, which is outside
    AREA_RATIO and so stops one physical mark pairing with itself across the
    change.

    This page gains two components when it is read correctly, and both of them
    were rendered and looked at: they are part of a RECEIVED stamp and a piece
    of handwriting, not damage to the paper. The test asserts that the page is
    read at its own resolution. It does not assert that what the corrected
    floor admits is a mark on the paper, because measured across all 53 pages
    it is not (DEFECTS #61).
    """
    pdf = mixed_pdf()
    image = render.extract_page_image(pdf, PAGE_200).convert("L")
    mask = np.asarray(image) < 128

    found = papermatch.page_marks(pdf, PAGE_200)
    at_own = paper.solid_marks(mask, dpi=200.0)
    at_assumed = paper.solid_marks(mask, dpi=300.0)
    assert len(at_own) != len(at_assumed), (
        "this page must be one where the reading differs, or the test is "
        "asserting nothing")
    assert len(found) == len(at_own)
    assert [round(m.area_in2, 6) for m in found] == [
        round(m.area_in2, 6) for m in at_own]


def test_the_cache_key_separates_two_resolutions_of_one_page(tmp_path):
    """Resolution is a property of the page, not of the detector, so it goes
    in the per-page key. Folding it into DETECTOR would invalidate every
    cached page in the corpus at 1.2 s each.
    """
    cache = papermatch.MarkCache(tmp_path)
    doc = render.doc_hash(mixed_pdf())
    a = cache.path(doc, PAGE_200, dpi=200.0)
    b = cache.path(doc, PAGE_200, dpi=300.0)
    assert a != b
    assert papermatch.DETECTOR in a.name and papermatch.DETECTOR in b.name


# --------------------------- the small-mark channel's cache, 2026-09-07

def test_the_small_mark_cache_returns_what_the_detector_returned(tmp_path):
    cache = papermatch.SmallMarkCache(tmp_path)
    fresh = papermatch.page_small_marks(pdf(), FACE, cache)
    cached = papermatch.page_small_marks(pdf(), FACE, cache)
    assert len(cached) == len(fresh)
    for a, b in zip(fresh, cached):
        assert (round(a.x, 9), round(a.y, 9), round(a.area_in2, 9)) == \
               (round(b.x, 9), round(b.y, 9), round(b.area_in2, 9))


def test_the_two_caches_do_not_share_a_key(tmp_path):
    """A change to one channel's constants must not invalidate the other's
    pages. There are 1,451 cached under the solid-mark detector and each costs
    about 1.5 s to rebuild, so folding the keys together would make every
    small-mark experiment expensive for no reason.
    """
    assert papermatch.DETECTOR != papermatch.SMALL_DETECTOR
    doc = render.doc_hash(pdf())
    marks_path = papermatch.MarkCache(tmp_path).path(doc, FACE, 300.0)
    small_path = papermatch.SmallMarkCache(tmp_path).path(doc, FACE, 300.0)
    assert marks_path != small_path
    assert papermatch.SMALL_DETECTOR not in marks_path.name
    assert papermatch.DETECTOR not in small_path.name


def test_changing_a_small_mark_constant_invalidates_only_its_own_cache(
        tmp_path, monkeypatch):
    cache = papermatch.SmallMarkCache(tmp_path)
    papermatch.page_small_marks(pdf(), FACE, cache)
    doc, dpi = render.doc_hash(pdf()), papermatch.page_dpi(pdf(), FACE)
    assert cache.get(doc, FACE, dpi) is not None
    monkeypatch.setattr(papermatch, "SMALL_DETECTOR", "0000000000000000")
    assert cache.get(doc, FACE, dpi) is None
