"""Tier 2: the viewer's TypeScript vocabularies match pipeline/extract.py.

The exporter writes what the Python types allow; the viewer refuses what its
TypeScript types do not know. Two vocabularies in two languages drift
silently unless something reads both, so this reads both.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline import extract as ex

ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "viewer" / "src" / "types.ts"


def literals(name: str) -> set[str]:
    source = TYPES.read_text()
    block = re.search(rf"const {name} = \[(.*?)\]", source, re.S)
    assert block, f"viewer/src/types.ts has no const {name}"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def test_the_status_vocabulary_matches():
    assert literals("STATUSES") == {s.value for s in ex.Status}


def test_the_region_source_vocabulary_matches():
    assert literals("SOURCES") == set(ex.SOURCES)
