#!/usr/bin/env python3
"""Match two pages by the solid marks on the paper: blots, holes, damage.

Spends nothing. No API calls.

**Why marks and not the outline.** The paper-outline probe of 2026-09-05 is
closed: it scored the same under a transform the sheet can perform and one it
cannot, so it was not reading the sheet. It also needed a black scanner border,
which 42% of the relevant pages do not have. Marks need no border, and on
1495414 p6+p7 the corner blot matched to 0.026 in under the right flip against
2.37 in under the wrong one.

**The transforms, and this is the part I had wrong.** Turning a sheet over is a
reflection, and the operator can turn it about either edge:

    flip_v   (x, y) -> (x, 1 - y)     turned top over bottom
    flip_h   (x, y) -> (1 - x, y)     turned left over right

Both are legitimate and we do not know which the scanner operator used, so both
are tried. The two transforms a turned-over sheet **cannot** produce are the
orientation-preserving ones:

    same     (x, y) -> (x, y)         not turned over at all
    rot180   (x, y) -> (1 - x, 1 - y) turned over and back again

Those are the control. Two options on each side, so the best-of on the real
side is not being handed a freedom the control lacks.

**Detection.** A solid mark is compact and dense. The form's printed rules are
one enormous hollow shape, so a density cut separates them. Before labelling,
a morphological opening severs hairline connections: without it a mark touching
a printed rule is absorbed into an eight-inch-wide component and thrown away
with it, which is what lost both punch holes on 1495414 p7.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
FIXTURES = ROOT / "tests" / "fixtures"
OUT = ROOT / "data" / "probe"

DPI = 300.0

#: Smallest mark worth keeping, in square inches. 0.008 in2 is a disc about
#: 0.1 in across, which is smaller than a punch hole and larger than a letter.
MIN_AREA = 0.008

#: Ink density: filled area over bounding-box area. A printed table runs 0.03
#: to 0.12; the corner blot on 1495414 p6 and p7 is 0.37 on both pages.
MIN_FILL = 0.30

#: Opening radius in pixels. Severs connections thinner than this, so a mark
#: sitting on a printed rule survives as its own component. A 300 dpi form
#: rule is 2 to 4 px; 3 cuts them without eating a 30 px blot.
OPEN_RADIUS = 3

#: Two marks are the same mark if they land this close, as a fraction of page
#: height, AFTER the two pages have been brought into alignment.
#:
#: Alignment is not optional and the first version omitted it. On 1495414 the
#: two scans are cropped about 0.07 in apart vertically, so the punch hole —
#: x 0.657 against 0.658, area 0.0521 against 0.0492, density 0.76 against
#: 0.77, plainly the same hole — landed 0.073 in away and was rejected by a
#: 0.066 in tolerance. The offset is a property of the scanner, not of the
#: sheet, and it has to be removed before the sheet can be read.
TOLERANCE = 0.003

#: Candidate offsets are proposed by every pair of marks that could be the
#: same mark, and the offset with the most agreement wins. A page cannot sit
#: further out than this, so an offset larger than it is not considered.
MAX_OFFSET = 0.06

#: And if their areas agree this well. A mark can be read slightly differently
#: on the two sides of a sheet; it cannot double in size.
AREA_RATIO = 1.6

TRANSFORMS = {
    "flip_v": lambda x, y: (x, 1.0 - y),
    "flip_h": lambda x, y: (1.0 - x, y),
}
CONTROLS = {
    "same": lambda x, y: (x, y),
    "rot180": lambda x, y: (1.0 - x, 1.0 - y),
}

_cache: dict = {}


def pdf_of(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            name = json.loads(line)["files"][file_index]["name"]
            return RAW / record_id / name
    raise KeyError(record_id)


def marks(record_id: str, file_index: int, number: int) -> list[dict]:
    """Every solid mark on one page, in page fractions."""
    key = (record_id, file_index, number)
    if key in _cache:
        return _cache[key]

    img = render.extract_page_image(pdf_of(record_id, file_index),
                                    number).convert("L")
    dark = np.asarray(img) < 128
    height, width = dark.shape

    # Sever hairlines so a mark touching a printed rule keeps its own identity.
    opened = ndimage.binary_opening(
        dark, structure=np.ones((OPEN_RADIUS, OPEN_RADIUS)))

    labels, _ = ndimage.label(opened)
    out = []
    for index, box in enumerate(ndimage.find_objects(labels), start=1):
        blob = labels[box] == index
        area = int(blob.sum())
        if area < MIN_AREA * DPI * DPI:
            continue
        box_h = box[0].stop - box[0].start
        box_w = box[1].stop - box[1].start
        fill = area / (box_h * box_w)
        if fill < MIN_FILL:
            continue
        cy, cx = ndimage.center_of_mass(blob)
        out.append({"x": (box[1].start + cx) / width,
                    "y": (box[0].start + cy) / height,
                    "area": area / DPI ** 2, "fill": fill})
    _cache[key] = sorted(out, key=lambda m: -m["area"])
    return _cache[key]


def _count(a, moved, offset) -> tuple[int, float]:
    """Marks that agree once the pages are shifted into line.

    Greedy and one-to-one: a mark on one page may explain at most one mark on
    the other, so a page speckled with blobs cannot manufacture matches.
    """
    taken, count, area = set(), 0, 0.0
    dx, dy = offset
    for mark, (tx, ty) in sorted(moved, key=lambda p: -p[0]["area"]):
        tx, ty = tx + dx, ty + dy
        best, best_distance = None, TOLERANCE
        for i, other in enumerate(a):
            if i in taken:
                continue
            ratio = max(mark["area"], other["area"]) / min(
                mark["area"], other["area"])
            if ratio > AREA_RATIO:
                continue
            distance = ((other["x"] - tx) ** 2 + (other["y"] - ty) ** 2) ** 0.5
            if distance < best_distance:
                best, best_distance = i, distance
        if best is not None:
            taken.add(best)
            count += 1
            area += min(mark["area"], a[best]["area"])
    return count, area


def match(a: list[dict], b: list[dict], transform) -> tuple[int, float]:
    """Best agreement between two pages under one transform.

    The two scans are cropped differently, so a rigid offset is estimated
    before anything is counted. Every pair of marks that could be the same
    mark proposes the offset that would align them; the offset with the most
    agreement wins. Every transform, real and control alike, gets exactly this
    same freedom, so the search cannot flatter the real ones.
    """
    moved = [(mark, transform(mark["x"], mark["y"])) for mark in b]
    candidates = {(0.0, 0.0)}
    for mark, (tx, ty) in moved:
        for other in a:
            ratio = max(mark["area"], other["area"]) / min(
                mark["area"], other["area"])
            if ratio > AREA_RATIO:
                continue
            dx, dy = other["x"] - tx, other["y"] - ty
            if abs(dx) <= MAX_OFFSET and abs(dy) <= MAX_OFFSET:
                candidates.add((round(dx, 5), round(dy, 5)))

    best = (0, 0.0)
    for offset in candidates:
        result = _count(a, moved, offset)
        if result > best:
            best = result
    return best


def score_pair(record_id: str, file_index: int, child: int,
               face: int) -> dict:
    a, b = marks(record_id, file_index, face), marks(record_id, file_index,
                                                     child)
    row = {"marks_face": len(a), "marks_child": len(b)}
    if not a or not b:
        row["abstained"] = "no solid mark found on " + (
            "either page" if not a and not b
            else f"p{face}" if not a else f"p{child}")
        return row

    real = {name: match(a, b, fn) for name, fn in TRANSFORMS.items()}
    ctrl = {name: match(a, b, fn) for name, fn in CONTROLS.items()}
    best_name = max(real, key=lambda k: (real[k][0], real[k][1]))
    ctrl_name = max(ctrl, key=lambda k: (ctrl[k][0], ctrl[k][1]))

    row["abstained"] = ""
    row["matched"] = real[best_name][0]
    row["matched_area_in2"] = round(real[best_name][1], 4)
    row["flip"] = best_name
    row["control_matched"] = ctrl[ctrl_name][0]
    row["control_area_in2"] = round(ctrl[ctrl_name][1], 4)
    row["control_transform"] = ctrl_name
    row["margin"] = row["matched"] - row["control_matched"]
    for name, (n, _) in {**real, **ctrl}.items():
        row[f"n_{name}"] = n
    return row


def sheet_rows(path: Path):
    raw = path.read_bytes().decode("utf-8", errors="replace")
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("part", "A") != "A" or "+" not in row.get("item", ""):
            continue
        child, face = (int(x.lstrip("p"))
                       for x in row["item"].split()[-1].split("+"))
        yield row, child, face


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default="attachment_verify_4.csv")
    args = ap.parse_args()

    source = FIXTURES / args.sheet
    target = OUT / f"mark_scores_{source.stem}.csv"
    OUT.mkdir(parents=True, exist_ok=True)

    fields = ["item", "record_id", "file_index", "child_page", "face_page",
              "your_verdict", "matched", "control_matched", "margin", "flip",
              "control_transform", "matched_area_in2", "control_area_in2",
              "n_flip_v", "n_flip_h", "n_same", "n_rot180",
              "marks_face", "marks_child", "abstained"]
    rows = []
    print(f"{'pair':26s} {'match':>5s} {'ctrl':>5s} {'flip':>7s}  "
          f"{'you':9s} note")
    for row, child, face in sheet_rows(source):
        scored = score_pair(row["record_id"].strip(), int(row["file_index"]),
                            child, face)
        record = {"item": row["item"], "record_id": row["record_id"].strip(),
                  "file_index": row["file_index"], "child_page": child,
                  "face_page": face,
                  "your_verdict": (row.get("verdict") or "").strip(),
                  **{k: v for k, v in scored.items()}}
        rows.append(record)
        print(f"  {row['item']:24s} "
              f"{str(scored.get('matched','-')):>5s} "
              f"{str(scored.get('control_matched','-')):>5s} "
              f"{str(scored.get('flip','-')):>7s}  "
              f"{record['your_verdict']:9s} {scored.get('abstained','')}")

    with target.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    scored = [r for r in rows if r.get("matched") is not None]
    yes = [r for r in scored if r["your_verdict"] == "yes"]
    no = [r for r in scored if r["your_verdict"] != "yes"]
    print(f"\n{len(rows)} pairs, {len(scored)} scored, "
          f"{len(rows) - len(scored)} abstained for want of a mark")
    if yes and no:
        print(f"  you said yes ({len(yes):2d}): matched "
              f"{min(r['matched'] for r in yes)}-"
              f"{max(r['matched'] for r in yes)}   control "
              f"{min(r['control_matched'] for r in yes)}-"
              f"{max(r['control_matched'] for r in yes)}")
        print(f"  you said no  ({len(no):2d}): matched "
              f"{min(r['matched'] for r in no)}-"
              f"{max(r['matched'] for r in no)}   control "
              f"{min(r['control_matched'] for r in no)}-"
              f"{max(r['control_matched'] for r in no)}")
    print(f"\nspreadsheet: {target}")


if __name__ == "__main__":
    main()
