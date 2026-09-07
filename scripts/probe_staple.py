#!/usr/bin/env python3
"""Is there a same-sheet signal BELOW the mark-area floor, and is it safe?

Spends nothing. No API calls, no model calls, no fetch.

**Why.** `pipeline/paper.py` confirms 4 of the 16 pairs Alex judged same-sheet
on 2026-09-06, and 15 of those 16 calls cite staple marks, which sit under
`MIN_MARK_AREA`. DEFECTS #53 fixed that floor where it is because bold printed
glyphs are the same size, so the floor cannot be lowered. Anything under it
needs a different discriminator, and this probe measures whether one exists
before a single record is fetched.

**The staple model in the plan is not what the paper supports, and this probe
is how that was found.** "Two marks about 10 mm apart near a corner" fires on 1
of the 8 pairs where a flip beat the control; the others sit 1.6 to 9.2 inches
apart. What carries the signal is small marks generally.

**The discriminators, in the order they cut.** Below the area floor, on the
sheet rather than in the scanner surround, roughly equant, near the paper's own
edge, and with at most one comparable neighbour within a character pitch, which
is what removes printing: glyphs come in runs, in rows and in dotted rules, and
damage does not.

**The statistic is the margin, as everywhere else in this module (R4):** marks
agreeing under a legitimate flip, minus marks agreeing under the best
orientation-preserving control. Marks are matched one at a time and **no rigid
offset is searched**. That is not an oversight. Searching a shared offset was
measured and it lifted the controls exactly as searching rotations did in the
original work (R1): false confirmations went from 0 to 2 of 120 cross-record
and from 3 to 11 of 160 same-file.

**Everything here is development data**, drawn from the 91 development records
of tests/fixtures/paper_record_split.csv, and every constant below was chosen
while looking at it. The rule was chosen after seeing both the positive and the
negative results. It has no held-out support of any kind, exactly like the
ambiguity rule of DEFECTS #55 when it was written.

    --positives   the 16 pairs Alex judged same-sheet, and the 8 he judged not
    --cross       guaranteed-false pairs from two different records
    --samefile    non-adjacent pages of one file: one punch, one staple
    (default)     all three
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import papermatch, render                    # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SPLIT = ROOT / "tests" / "fixtures" / "paper_record_split.csv"
SHEET = ROOT / "tests" / "fixtures" / "paper_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"

#: Chosen on development data, 2026-09-06. Not frozen and not pre-registered:
#: freezing them is the next step and it happens in its own commit.
AREA_PX = (25, 1800)        #: below MIN_MARK_AREA's 1,800 px at 300 dpi
MAX_ASPECT = 2.5            #: damage is roughly equant
EDGE_IN = 0.8               #: how near the paper's own edge a mark must sit
RUN_PITCH_IN = 0.35         #: a comparable neighbour this close makes it text
MAX_NEIGHBOURS = 1          #: a staple has a partner; a dotted rule has many
TOL = 0.008                 #: how close two marks must land, as a sheet fraction
AREA_RATIO = 3.0            #: one physical mark, read twice
MIN_AGREEING = 2            #: R5's reason: one agreeing mark can be the stroke

TRANSFORMS = {"flip_v": lambda x, y: (x, 1 - y),
              "flip_h": lambda x, y: (1 - x, y)}
CONTROLS = {"same": lambda x, y: (x, y),
            "rot180": lambda x, y: (1 - x, 1 - y)}

_CACHE: dict = {}


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def development_records() -> set:
    rows = csv.DictReader(io.StringIO(SPLIT.read_text()))
    return {r["record_id"] for r in rows if r["half"] == "development"}


def small_marks(pdf: Path, page: int) -> list[tuple[float, float, int]]:
    """Candidate marks on one page, in coordinates of the SHEET.

    Not of the image: the sheet is inset in a larger scanner field and inset
    differently in the two scans of one pair, so image coordinates would
    compare two different frames.
    """
    key = (str(pdf), page)
    if key in _CACHE:
        return _CACHE[key]
    dpi = papermatch.page_dpi(pdf, page)
    array = np.asarray(render.extract_page_image(pdf, page).convert("L"))
    dark = array < 128

    # The sheet is the largest light region. Everything outside it is the
    # scanner backing, which is dark and would otherwise be one huge "mark".
    labels, count = ndimage.label(~dark)
    if count == 0:
        _CACHE[key] = []
        return []
    sizes = ndimage.sum(~dark, labels, range(1, count + 1))
    sheet = ndimage.binary_fill_holes(labels == int(np.argmax(sizes)) + 1)
    ys, xs = np.where(sheet)
    top, left = int(ys.min()), int(xs.min())
    height, width = int(ys.max()) - top, int(xs.max()) - left
    if height <= 0 or width <= 0:
        _CACHE[key] = []
        return []

    inside = dark & ndimage.binary_erosion(sheet, np.ones((9, 9)))
    marked, _ = ndimage.label(inside)
    found = []
    for index, box in enumerate(ndimage.find_objects(marked), start=1):
        area = int((marked[box] == index).sum())
        if not (AREA_PX[0] <= area <= AREA_PX[1]):
            continue
        bh = box[0].stop - box[0].start
        bw = box[1].stop - box[1].start
        if max(bh, bw) / min(bh, bw) > MAX_ASPECT:
            continue
        found.append((box[1].start + bw / 2, box[0].start + bh / 2, area, bh))

    to_edge = ndimage.distance_transform_edt(sheet) / dpi
    points = (np.array([[f[0], f[1]] for f in found]) if found
              else np.zeros((0, 2)))
    keep = []
    for cx, cy, area, bh in found:
        if to_edge[int(cy), int(cx)] > EDGE_IN:
            continue
        near = np.hypot(points[:, 0] - cx, points[:, 1] - cy) <= \
            RUN_PITCH_IN * dpi
        neighbours = sum(1 for j in np.where(near)[0]
                         if not (found[j][0] == cx and found[j][1] == cy)
                         and max(bh, found[j][3]) / min(bh, found[j][3]) <= 2.5)
        if neighbours > MAX_NEIGHBOURS:
            continue
        keep.append(((cx - left) / width, (cy - top) / height, area))
    _CACHE[key] = keep
    return keep


def agreeing(a, b, move) -> int:
    """Marks of b that land on a mark of a, one to one, under `move`."""
    hits, taken = 0, set()
    for ax, ay, aarea in a:
        pick, closest = None, TOL
        for j, (bx, by, barea) in enumerate(b):
            if j in taken:
                continue
            if max(aarea, barea) / min(aarea, barea) > AREA_RATIO:
                continue
            tx, ty = move(bx, by)
            distance = float(np.hypot(ax - tx, ay - ty))
            if distance < closest:
                pick, closest = j, distance
        if pick is not None:
            taken.add(pick)
            hits += 1
    return hits


def verdict(pdf_a: Path, page_a: int, pdf_b: Path, page_b: int):
    a, b = small_marks(pdf_a, page_a), small_marks(pdf_b, page_b)
    flip = max(agreeing(a, b, m) for m in TRANSFORMS.values())
    control = max(agreeing(a, b, m) for m in CONTROLS.values())
    return len(a), len(b), flip, control, flip >= MIN_AGREEING and flip > control


def pdf_of(recs, record_id, file_index) -> Path:
    return RAW / record_id / recs[record_id]["files"][file_index]["name"]


def judged(recs):
    """The 2026-09-06 sitting, which is the only human truth that exists."""
    sealed = json.loads(VERDICTS.read_text())["verdicts"]
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    sheet = {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}
    for item in sorted(sealed):
        call = (sheet[item]["verdict"] or "").strip().lower()
        if call in ("same-sheet", "not-same-sheet"):
            yield item, call, sealed[item]


def run_positives(recs) -> None:
    for want in ("same-sheet", "not-same-sheet"):
        print(f"\npairs Alex judged {want}")
        fired = total = 0
        for item, call, row in judged(recs):
            if call != want:
                continue
            pdf = pdf_of(recs, row["record_id"], row["file_index"])
            a, b = row["pages"]
            na, nb, flip, control, fires = verdict(pdf, a, pdf, b)
            total += 1
            fired += fires
            print(f"  {item} {row['record_id']}-{row['file_index']} p{a}+p{b}"
                  f"  marks {na:3d}/{nb:3d}  flip {flip:2d} control {control:2d}"
                  f"{'  FIRES' if fires else ''}"
                  f"{'   [paper.compare confirms]' if row['confirmed'] else ''}")
        print(f"  fired on {fired} of {total}")


def run_cross(recs, development, count=120, seed=20260906) -> None:
    print(f"\nguaranteed-false: two different records, different leases")
    rng = random.Random(seed)
    pool = [(r, pdf_of(recs, r, 0), recs[r]["files"][0].get("pages") or 2)
            for r in sorted(development) if r in recs]
    fired = total = 0
    for _ in range(count):
        (ra, pa, na), (rb, pb, nb) = rng.sample(pool, 2)
        page_a = rng.randint(1, min(na, 20))
        page_b = rng.randint(1, min(nb, 20))
        try:
            ca, cb, flip, control, fires = verdict(pa, page_a, pb, page_b)
        except Exception:                                   # noqa: BLE001
            continue
        total += 1
        fired += fires
        if fires:
            print(f"  FIRES {ra}-0 p{page_a} + {rb}-0 p{page_b}"
                  f"  marks {ca}/{cb} flip {flip} control {control}")
    print(f"  false confirmations: {fired} of {total}")


def run_samefile(recs, development, per_record=8, seed=20260906) -> None:
    print(f"\nhard negative: non-adjacent pages of ONE file, one punch stroke")
    print("  NOT guaranteed false. The protocol's own rule is that Alex")
    print("  adjudicates a confirmed pair here; I do not.")
    rng = random.Random(seed)
    fired = total = 0
    for record_id in sorted(development):
        if record_id not in recs:
            continue
        pages = recs[record_id]["files"][0].get("pages") or 0
        if pages < 6:
            continue
        pdf = pdf_of(recs, record_id, 0)
        tried = 0
        while tried < per_record:
            a, b = rng.randint(1, pages), rng.randint(1, pages)
            if abs(a - b) < 3:
                continue
            tried += 1
            try:
                ca, cb, flip, control, fires = verdict(pdf, a, pdf, b)
            except Exception:                               # noqa: BLE001
                continue
            total += 1
            fired += fires
            if fires:
                print(f"  FIRES {record_id}-0 p{a}+p{b}  marks {ca}/{cb} "
                      f"flip {flip} control {control}   -> for adjudication")
    print(f"  fired on {fired} of {total}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--positives", action="store_true")
    ap.add_argument("--cross", action="store_true")
    ap.add_argument("--samefile", action="store_true")
    ap.add_argument("--records", type=int, default=0,
                    help="cap development records used for the negative "
                         "strata, for a quick run")
    args = ap.parse_args()
    everything = not (args.positives or args.cross or args.samefile)

    render.preflight()
    recs = records()
    development = development_records()
    if args.records:
        development = set(sorted(development)[:args.records])
    print(f"development records in use: {len(development)} of "
          f"{len(development_records())}  (tests/fixtures/paper_record_split.csv)")
    print(f"constants: area {AREA_PX} px, aspect {MAX_ASPECT}, edge "
          f"{EDGE_IN} in, run pitch {RUN_PITCH_IN} in, tolerance {TOL}, "
          f"minimum agreeing {MIN_AGREEING}")

    if everything or args.positives:
        run_positives(recs)
    if everything or args.cross:
        run_cross(recs, development)
    if everything or args.samefile:
        run_samefile(recs, development)


if __name__ == "__main__":
    main()
