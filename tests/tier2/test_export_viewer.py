"""Tier 2: the viewer exporter's join logic, and the bundle's invariants.

The exporter projects a finished run into the static bundle the viewer
reads. The parts worth testing are the joins: which region a value ships
(the three honesty tiers), and which channel an attachment is credited to.
Both are pure functions and are tested without I/O; the end-to-end pass
runs only when a finished run is on disk, as data/ is never committed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pipeline import extract as ex

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "extract" / "corpus.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_corpus.jsonl"


def _exporter():
    spec = importlib.util.spec_from_file_location(
        "export_viewer", ROOT / "scripts" / "export_viewer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODEL_REGION = {"page": 9, "box": [0.1, 0.2, 0.4, 0.25], "source": "model"}


def test_a_snapped_value_ships_the_line_run_as_text_layer():
    xv = _exporter()
    snap = {"outcome": "unique", "display_box": [0.11, 0.21, 0.39, 0.24]}
    region = xv.viewer_region({"region": dict(MODEL_REGION)}, snap)
    assert region == {"page": 9, "box": [0.11, 0.21, 0.39, 0.24],
                      "source": "text_layer"}


def test_an_unsnapped_value_ships_the_model_box_untouched():
    """The viewer widens the model band at display time (R5); the exporter
    must not pre-widen, or the raw claim is hidden inside the coordinates.
    """
    xv = _exporter()
    for snap in (None, {"outcome": "ambiguous", "display_box": None},
                 {"outcome": "unique", "display_box": None}):
        region = xv.viewer_region({"region": dict(MODEL_REGION)}, snap)
        assert region == MODEL_REGION


def test_a_value_with_no_region_stays_on_the_page_floor():
    xv = _exporter()
    assert xv.viewer_region({"region": None}, {"outcome": "unique"}) is None


TEMPLATE_REGION = {"page": 9, "box": [0.09, 0.19, 0.41, 0.26],
                   "source": "template"}


def test_the_template_tier_beats_the_model_box():
    xv = _exporter()
    region = xv.viewer_region({"region": dict(MODEL_REGION)}, None,
                              dict(TEMPLATE_REGION))
    assert region == TEMPLATE_REGION


def test_snap_still_beats_the_template_tier():
    xv = _exporter()
    snap = {"outcome": "unique", "display_box": [0.11, 0.21, 0.39, 0.24]}
    region = xv.viewer_region({"region": dict(MODEL_REGION)}, snap,
                              dict(TEMPLATE_REGION))
    assert region["source"] == "text_layer"


def test_the_template_tier_lifts_a_value_off_the_page_floor():
    """The point of the tier: a field the model gave no box still gets a
    located region when a registered template knows where it is."""
    xv = _exporter()
    region = xv.viewer_region({"region": None}, None,
                              dict(TEMPLATE_REGION))
    assert region == TEMPLATE_REGION


def test_attachments_name_their_channel():
    """A page attached on agreeing identity fields is identity's; a page
    attached with none is the paper confirmer's, the only other way into a
    document (reassemble.group). The face is not an attachment.
    """
    xv = _exporter()
    row = {"face": 5, "pages": [5, 6, 13],
           "evidence": [[13, ["operator_name", "lease_name"]]]}
    assert xv.attachment_rows(row) == [
        {"page": 6, "channel": "paper", "fields": []},
        {"page": 13, "channel": "identity",
         "fields": ["operator_name", "lease_name"]}]


def test_value_rows_carry_the_status_vocabulary_and_nothing_else():
    xv = _exporter()
    present = ex.Value(status=ex.Status.PRESENT, raw="EXAMPLE", value="EXAMPLE",
                       region=ex.Region(page=9, box=(0.1, 0.2, 0.4, 0.25)),
                       found_in="18. Lease Name")
    row = xv.value_row("identity.lease_name", present)
    assert row["group"] == "identity"
    assert row["status"] == "present" and row["found_in"] == "18. Lease Name"
    assert row["region"]["source"] == "model"

    blank = ex.Value(status=ex.Status.BLANK)
    row = xv.value_row("completion.total_depth", blank)
    assert row["region"] is None and row["raw"] is None

    cell = ex.Value(status=ex.Status.PRESENT, raw="9 5/8", value="9 5/8",
                    region=ex.Region(page=9, box=(0.1, 0.2, 0.4, 0.25)))
    assert xv.value_row("casing[0].size", cell)["group"] == "casing"


@pytest.mark.skipif(not (RESULTS.exists() and CACHE.exists()),
                    reason="needs a finished corpus run under data/extract")
def test_the_bundle_holds_its_invariants(tmp_path):
    """One document end to end: every region's source is in the vocabulary,
    every region cites a page of its own document, and every cited page has
    an image and metadata in the bundle.
    """
    import subprocess
    import sys
    out = tmp_path / "viewer"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_viewer.py"),
         "--limit", "1", "--out", str(out)],
        check=True, capture_output=True)
    bundle = json.loads((out / "documents.json").read_text())
    assert bundle["documents"], "no document exported"
    allowed = ex.SOURCES
    for doc in bundle["documents"]:
        for value in doc["values"]:
            region = value["region"]
            if region is None:
                continue
            assert region["source"] in allowed
            assert region["page"] in doc["pages"]
            page_key = f"{doc['record_id']}-{doc['file_index']}-{region['page']}"
            assert page_key in bundle["pages"]
            assert (out / "pages" / f"{page_key}.jpg").exists()
    meta = json.loads((out / "meta.json").read_text())
    assert meta["documents"] == len(bundle["documents"])
