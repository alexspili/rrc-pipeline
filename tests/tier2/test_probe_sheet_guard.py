"""Tier 2: the stage-four sheet generator refuses before it destroys anything.

Origin: DEFECTS #34. `write_sheet` emptied its output directory and then,
thirty lines later, asked whether the grading sheet was already filled. The
sheet is filled, so re-running it would have deleted the answer key and both
graded overlays and only then raised. The key lives under data/, which is
git-ignored, so the commit habit that saved DEFECTS #26 would not have saved
this.

The test is deliberately about ordering rather than about the refusal. The
refusal already worked; it was standing in the wrong place.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _probe_module():
    spec = importlib.util.spec_from_file_location(
        "probe_boxes", ROOT / "scripts" / "probe_boxes.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_boxes"] = module
    spec.loader.exec_module(module)
    return module


def test_a_graded_sheet_refuses_before_the_output_directory_is_touched(
        tmp_path, monkeypatch):
    from pipeline.guard import RefusedToOverwrite

    probe = _probe_module()

    sheet = tmp_path / "box_grades_probe.csv"
    with sheet.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["box_num", "grade", "note"])
        writer.writeheader()
        writer.writerow({"box_num": "1", "grade": "hit", "note": ""})

    out = tmp_path / "overlay_probe"
    out.mkdir()
    key = out / "KEY_do_not_open_until_graded.csv"
    key.write_text("box_num,source\n1,text_layer\n")
    image = out / "PROBE_x_p001.png"
    image.write_bytes(b"not really a png")

    monkeypatch.setattr(probe, "PROBE_SHEET", sheet)
    monkeypatch.setattr(probe, "PROBE_OUT", out)

    with pytest.raises(RefusedToOverwrite):
        probe.write_sheet(Path("unused.pdf"), [], {}, {}, seed=1)

    assert key.exists(), "the answer key was deleted before the guard fired"
    assert image.read_bytes() == b"not really a png"
    assert sorted(p.name for p in out.iterdir()) == [
        "KEY_do_not_open_until_graded.csv", "PROBE_x_p001.png"]
