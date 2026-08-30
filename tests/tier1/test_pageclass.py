"""Tier 1: pure page-classification domain. No I/O, no network, no fixtures
beyond a frozen CSV of ids.

Written before pipeline/pageclass.py exists, per CLAUDE.md rule 5.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline import pageclass as pc

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ------------------------------------------------------------- geometry guard

@pytest.mark.parametrize(
    "w,h,oversize,why",
    [
        (2537, 3279, False, "the modal 300dpi portrait page"),
        (1688, 2178, False, "a 200dpi page, 53 of these in the corpus"),
        (3712, 3040, False, "landscape but page-shaped; 646 images are landscape"),
        (11264, 3040, True, "widest real page in the corpus, record 1495350 p12"),
        (1010, 15167, True, "DEFECTS #1's original well-log strip"),
    ],
)
def test_oversize_guard(w, h, oversize, why):
    """Origin: DEFECTS #1. A long-edge downscale destroys pages that are not
    page-shaped. No log strip survives in this corpus, but 23 pages exceed
    AR 2.0 and the widest would land at a 423px short edge under the 1568 cap.
    """
    assert pc.is_oversize(w, h) is oversize, why


def test_oversize_boundary_is_exactly_two():
    assert pc.is_oversize(2000, 1000) is False   # AR 2.0 exactly, allowed
    assert pc.is_oversize(2001, 1000) is True
    assert pc.is_oversize(1000, 2001) is True    # orientation must not matter


# ---------------------------------------------------------- downscale targets

def test_downscale_caps_the_long_edge():
    assert pc.downscale_target(2537, 3279, cap=1568) == (1213, 1568)
    assert pc.downscale_target(3712, 3040, cap=1568) == (1568, 1284)


def test_downscale_never_upscales():
    """A 200dpi page smaller than the cap must be left alone. Upscaling a
    bilevel scan invents ink that was never on the paper.
    """
    assert pc.downscale_target(800, 1000, cap=1568) == (800, 1000)


def test_downscale_preserves_aspect_within_one_pixel():
    for w, h in [(2537, 3279), (3712, 3040), (11264, 3040), (2546, 3285)]:
        tw, th = pc.downscale_target(w, h, cap=1000)
        assert abs((w / h) - (tw / th)) < (1 / min(tw, th)), (w, h, tw, th)
        assert max(tw, th) <= 1000


# ------------------------------------------------------------ token estimate

def test_token_estimate_is_area_over_750():
    """UNVERIFIED against the API. This is the published w*h/750 rule of
    thumb; the bounded probe replaces it with a measured count_tokens figure
    before any cost number reaches prose (CLAUDE.md rule 8).
    """
    assert pc.estimate_image_tokens(1213, 1568) == pytest.approx(2536, abs=2)
    assert pc.estimate_image_tokens(775, 1000) == pytest.approx(1033, abs=2)


# ------------------------------------------------------------------- page ids

def test_page_id_round_trips_over_frozen_fixture():
    """Frozen 20-row sample, seed 20260830. The full-manifest sweep is tier 2."""
    rows = list(csv.DictReader((FIXTURES / "page_ids.csv").open()))
    assert len(rows) == 20
    for row in rows:
        made = pc.page_id(row["record_id"], int(row["file_index"]), int(row["page"]))
        assert made == row["page_id"]
        assert pc.parse_page_id(made) == (
            row["record_id"], int(row["file_index"]), int(row["page"]))


def test_page_ids_fit_the_batch_custom_id_limit():
    rows = list(csv.DictReader((FIXTURES / "page_ids.csv").open()))
    ids = [r["page_id"] for r in rows]
    assert len(set(ids)) == len(ids)
    assert all(len(i) <= 64 for i in ids)


@pytest.mark.parametrize("bad", ["", "1493418", "1493418-0", "a-0-1", "1493418-0-0"])
def test_parse_page_id_rejects_malformed(bad):
    with pytest.raises(ValueError):
        pc.parse_page_id(bad)


# ------------------------------------------------------------- PageLabel rules

def _label(**kw):
    base = dict(record_id="1501720", file_index=0, page=2,
                form_class=pc.PageClass.G1, part=pc.Part.FACE,
                orientation=pc.Orientation.UP, confidence=pc.Confidence.HIGH,
                alt_class=None, oversize=False)
    base.update(kw)
    return pc.PageLabel(**base)


def test_part_is_required_for_form_classes():
    with pytest.raises(ValueError):
        _label(part=None)


def test_part_is_forbidden_for_census_only_classes():
    """A plat has no Section III. Allowing part here would let the census
    report sections of documents that do not have any.
    """
    with pytest.raises(ValueError):
        _label(form_class=pc.PageClass.PLAT_MAP, part=pc.Part.FACE)
    assert _label(form_class=pc.PageClass.PLAT_MAP, part=None).part is None


def test_oversize_page_is_never_extraction_eligible():
    """Origin: DEFECTS #1, as a constructor invariant rather than a rule in
    docs/modules. Extraction must refuse a page whose short edge was crushed
    by the downscale until tiling exists.
    """
    assert _label().extraction_eligible is True
    assert _label(oversize=True).extraction_eligible is False


def test_printed_form_back_is_never_extraction_eligible():
    """A form back carries the same header and form number as the face and
    contains no data. Extracting it produces confident garbage.
    """
    assert _label(part=pc.Part.BACK_INSTRUCTIONS).extraction_eligible is False


def test_identity_bearing_forms_are_not_extraction_targets():
    assert _label(form_class=pc.PageClass.P4).extraction_eligible is False
    assert _label(form_class=pc.PageClass.P4).identity_bearing is True


# --------------------------------------------------------------- cache keying

def test_cache_key_is_stable_and_prompt_sensitive():
    """CLAUDE.md rule 7: never re-infer an unchanged (document, prompt) pair."""
    a = pc.cache_key("deadbeef", pc.prompt_hash("classify this page"))
    b = pc.cache_key("deadbeef", pc.prompt_hash("classify this page"))
    c = pc.cache_key("deadbeef", pc.prompt_hash("classify this page "))
    assert a == b
    assert a != c


# ------------------------------------------------------------ response parsing

def test_parses_a_clean_response():
    label = pc.parse_response(
        '{"form_class":"g1","part":"face","orientation":"up",'
        '"confidence":"high","alt_class":"w2"}',
        record_id="1501720", file_index=0, page=2, oversize=False)
    assert label.form_class is pc.PageClass.G1
    assert label.alt_class is pc.PageClass.W2


def test_parses_json_wrapped_in_prose():
    """Haiku sometimes prefaces JSON with a sentence. Tolerate that; do not
    tolerate anything else.
    """
    label = pc.parse_response(
        'Here is the classification:\n```json\n'
        '{"form_class":"plat_map","part":null,"orientation":"cw90",'
        '"confidence":"medium","alt_class":null}\n```',
        record_id="1501720", file_index=0, page=9, oversize=False)
    assert label.form_class is pc.PageClass.PLAT_MAP
    assert label.orientation is pc.Orientation.CW90


@pytest.mark.parametrize("body", [
    "not json at all",
    '{"form_class":"g1"',
    '{"form_class":"G-1 completion report","part":"face","orientation":"up",'
    '"confidence":"high","alt_class":null}',
    '{"part":"face","orientation":"up","confidence":"high","alt_class":null}',
    '{"form_class":"g1","part":"face","orientation":"sideways",'
    '"confidence":"high","alt_class":null}',
])
def test_parse_response_refuses_to_guess(body):
    """No silent coercion. An out-of-enum class is a prompt or model problem
    and must surface as one, not become `other_nonform`.
    """
    with pytest.raises(ValueError):
        pc.parse_response(body, record_id="1501720", file_index=0,
                          page=2, oversize=False)
