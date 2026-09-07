"""Tier 2: the free passes survive a results row with nothing cached behind it.

DEFECTS #73. An API-level batch failure produces a results row with no cache
entry, and both free passes called extract_document(None, ...) on every row,
falling through to the live path holding no client. Each script must skip
rows carrying an error, and say how many it skipped.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.jsonl"

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="needs data/manifest.jsonl")

ERRORED_ROW = {
    "page_id": "1493495-0-9", "record_id": "1493495", "file_index": 0,
    "pages": [9], "mode": "grouped", "prompt_hash": "0" * 16,
    "form_class": None, "form_revision": None, "values": 0, "present": 0,
    "located": 0, "labelled": 0, "dropped": [], "input_tokens": 0,
    "output_tokens": 0, "cached": False,
    "error": "batch result errored: usage limits",
}


def run_pass(script: str, tmp_path: Path, extra: list[str]) -> str:
    tmp_path.mkdir(parents=True, exist_ok=True)
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps(ERRORED_ROW) + "\n")
    cache = tmp_path / "cache.jsonl"
    cache.write_text("")
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script),
         "--results", str(results), "--cache", str(cache),
         "--out", str(tmp_path / "out.jsonl"), *extra],
        capture_output=True, text=True)
    assert done.returncode == 0, (
        f"{script} died on an errored row:\n{done.stderr[-800:]}")
    return done.stdout


def test_the_free_passes_survive_a_run_with_uncached_failures(tmp_path):
    for script, extra in (("snap_coverage.py", []),
                          ("validate_extract.py", ["--quiet"])):
        stdout = run_pass(script, tmp_path / script.replace(".", "_"), extra)
        assert "skip" in stdout.lower(), (
            f"{script} skipped the row silently; the count is part of the "
            "report (standing rule 9)")
