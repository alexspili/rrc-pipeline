"""Tier 2: the poppler boundary, against a synthetic CCITT fixture.

The fixture is drawn, not redacted from the corpus: see
scripts/make_render_fixture.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline import pageclass as pc
from pipeline import render

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pages.pdf"


def test_preflight_finds_poppler():
    render.preflight()


def test_preflight_names_the_missing_tool_and_how_to_install_it(monkeypatch):
    """poppler cannot come from requirements.txt, so a missing binary has to
    fail with an instruction rather than a FileNotFoundError three frames
    down in subprocess.
    """
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    with pytest.raises(render.PreflightError) as exc:
        render.preflight()
    assert "pdfimages" in str(exc.value)
    assert "brew install poppler" in str(exc.value)


def test_page_dimensions_reads_every_page():
    assert render.page_dimensions(FIXTURE) == [(1200, 1600), (1600, 1200), (3000, 900)]


def test_the_oversize_guard_fires_on_the_foldout_page():
    """Origin: DEFECTS #1. Page 3 is AR 3.33, in the range of the real
    fold-out plats in record 1495350.
    """
    dims = render.page_dimensions(FIXTURE)
    assert [pc.is_oversize(w, h) for w, h in dims] == [False, False, True]


def test_render_caps_the_long_edge_and_returns_a_png():
    png, (width, height) = render.render_page_png(FIXTURE, 1, cap=1000)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert max(width, height) == 1000
    assert (width, height) == pc.downscale_target(1200, 1600, cap=1000)


def test_doc_hash_is_stable_and_short_enough_to_key_a_cache():
    first = render.doc_hash(FIXTURE)
    assert first == render.doc_hash(FIXTURE)
    assert len(first) == 16


def test_page_text_returns_the_layer_or_nothing_without_raising():
    """The drawn fixture has no text layer. Real pages do: 247 of 249 files.
    Either way this must not raise, or the text arm cannot be scored on the
    two files that have none.
    """
    assert render.page_text(FIXTURE, 1) == ""
