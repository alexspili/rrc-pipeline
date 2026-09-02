"""Tier 2: the county map HANDOFF claims exists, checked against the manifest.

HANDOFF says "every county name in the manifest maps to exactly one 3-digit
prefix, all matching real RRC county codes". That claim has been quoted since
the recon session and nothing has ever tested it. The API cross-check now
depends on it, so it gets a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.validate import county_codes, parse_api_ft

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.jsonl"


def _records():
    if not MANIFEST.exists():
        pytest.skip("manifest absent; data/ is git-ignored (CLAUDE.md rule 3)")
    return [json.loads(line)["meta"] for line in MANIFEST.open() if line.strip()]


def test_the_index_carries_an_api_number_on_most_records():
    """HANDOFF: 176 of 202. A collapse here means the archive changed shape or
    the tsvector parser broke, and the API cross-check would go quiet rather
    than fail.
    """
    records = _records()
    parsed = sum(1 for m in records if parse_api_ft(m.get("api_ft")))
    assert parsed >= 170, f"only {parsed} of {len(records)} records index an API"


def test_every_county_maps_to_exactly_one_code():
    """The claim the cross-check rests on. A county mapping two ways would be
    dropped by county_codes, so this test is what says the map is not quietly
    shrinking.
    """
    records = _records()
    pairs = [(m.get("county"), m.get("api_ft")) for m in records]
    mapped = county_codes(pairs)

    named = {(m.get("county") or "").strip().upper() for m in records
             if (m.get("county") or "").strip()
             and parse_api_ft(m.get("api_ft"))}
    dropped = sorted(named - set(mapped))
    assert not dropped, (
        f"counties the index maps more than one way: {dropped}. The map drops "
        "them, so the API county check goes silent on those records.")


def test_every_code_is_three_digits():
    codes = set(county_codes([(m.get("county"), m.get("api_ft"))
                              for m in _records()]).values())
    assert codes, "no county codes learned at all"
    assert all(len(c) == 3 and c.isdigit() for c in codes)


def test_brazoria_is_039():
    """The demo document's county, and the code that catches its transposed
    G-5. If this changes, DEFECTS' worked example stops working.
    """
    mapped = county_codes([(m.get("county"), m.get("api_ft"))
                           for m in _records()])
    assert mapped.get("BRAZORIA") == "039"
