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
    """A refusal that does not report what it compared cannot be audited, and
    the count came back zero for a while whatever had actually been paired.
    """
    verdict = paper.compare(marks(FACE), marks(9))
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
    monkeypatch.setattr(papermatch, "DETECTOR", "0000000000000000")
    assert cache.get(render.doc_hash(pdf()), FACE) is None
    monkeypatch.setattr(papermatch, "DETECTOR", before)
    assert cache.get(render.doc_hash(pdf()), FACE) is not None
