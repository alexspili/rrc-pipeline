"""Tier 2: the costing instrument prices what the code actually sends.

DEFECTS #50. The identity corpus read was quoted at $2.61 and cost $5.24,
because the quote was built on a 1000-px page image and the reader sends 1568.
The page count in that quote was right; only the price was wrong, which is the
version of this mistake that is hardest to notice.

No model calls. Prices come from measured cache entries and from the modules'
own constants.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location(
        "estimate_batch", ROOT / "scripts" / "estimate_batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not (ROOT / "data" / "extract" / "cache_identity.jsonl").exists(),
    reason="prices from the identity cache; data/ is never committed "
           "(DEFECTS #75)")
def test_a_page_is_priced_from_the_cap_the_module_actually_sends():
    """The quote that missed by 2x priced an identity page as though it were a
    classifier page. Both modules are asked here, and they must disagree,
    because they send different images.
    """
    from pipeline import classify, extractor, identity
    assert identity.IMAGE_CAP == extractor.IMAGE_CAP == 1568
    assert classify.ARMS["vision_1000"]["cap"] != identity.IMAGE_CAP

    module = _script()
    per_page = module.identity_price()
    assert per_page is not None, "no measured identity pages to price from"
    # Measured over 528 cached pages on 2026-09-05: $0.0150 a page. Pinned
    # loosely, because the point is that it is nowhere near the $0.0074 the
    # quote used, not that it is exactly this.
    assert per_page > 0.010, (
        f"identity priced at ${per_page:.4f}/page, which is back in the range "
        "the DEFECTS #50 quote came from")


def test_the_extraction_price_comes_from_measured_tokens_not_constants():
    """estimate_batch reads the smoke run's own recorded token counts. If that
    file goes away the script must say so rather than fall back to a guess.
    """
    module = _script()
    with pytest.raises(RuntimeError):
        module.price({}, 1)
