#!/usr/bin/env python3
"""The held-out sitting for pipeline/paper.py, drawn under a frozen mechanism.

Spends nothing. No API calls.

docs/labeling-protocol-paper.md, written before any of these pairs was looked
at. The mechanism and every constant it uses were frozen in commit
4868fdd3f714a38f9117b81b2b1c5f57a7c2b642 first.

**The sheet is blind, and that is the point.** Alex identified the punch rim as
the signal and has matched pages by eye using it. If he judges these pairs the
same way, the sitting measures whether an algorithm agrees with a human reading
the same pixels — a consistency check dressed as validation. So every mark the
mechanism detected is painted out of the images he sees, rows are shuffled,
page numbers are stripped, and the mechanism's verdicts are hashed before the
sheet goes out.

What is left to judge on: ink show-through, torn edges, staple marks, fold
lines, crop and skew geometry, missing corners.

    --screen   report the go/no-go count and write nothing
    (default)  build the sheet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper                          # noqa: E402
from pipeline import pageclass as pc                # noqa: E402
from pipeline import papermatch                     # noqa: E402
from pipeline import render                         # noqa: E402
from pipeline.guard import refuse_if_filled          # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
CACHE = ROOT / "data" / "cache" / "paper"
SHEET = ROOT / "tests" / "fixtures" / "paper_sitting.csv"
IMAGES = ROOT / "data" / "labelset" / "paper_sitting"
VERDICTS = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"

#: Records whose marks I have inspected by eye. Burned for the mechanism.
INSPECTED = ("1493608", "1495414", "1774674")

#: Records whose pages ALEX has looked at, named in conversation rather than
#: written to a sheet. DEFECTS #56: the frame originally excluded only the
#: records that had informed the CODE, and never asked which had informed the
#: JUDGE. He did not read identity fields in those sittings; he looked at
#: photographs of the paper, which is exactly what this sitting asks for.
SHOWN_IN_CONVERSATION = ("1495193", "1912687", "1500024", "1495195",
                         "1493608", "1495414", "1774674")
SECTIONS = {"sec_ii", "sec_iii", "continuation"}
BACKISH = SECTIONS | {"back_instructions"}

SEED = 20260906

#: Below this many scoreable likely-true pairs the sitting does not run as
#: designed and the choice is Alex's, taken with the number in hand.
FLOOR = 10

#: How much of the page around a mark is painted out. The shape is what the
#: mechanism reads, so the shape is what has to go; the blank square left
#: behind says a mark was there and says nothing about its edge.
MASK_PAD_IN = 0.06


def seen_by_alex() -> set:
    """Every record he has already looked at, derived and not remembered.

    Built from the verification sheets themselves so it cannot drift, plus the
    records whose pages were displayed in conversation.
    """
    import csv
    import io
    out = set(INSPECTED) | set(SHOWN_IN_CONVERSATION)
    for path in sorted((ROOT / "tests" / "fixtures").glob("attachment_verify*.csv")):
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for row in csv.DictReader(io.StringIO(raw)):
            if row.get("record_id"):
                out.add(row["record_id"].strip())
    return out


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def pdf_of(recs, record_id, file_index) -> Path:
    return RAW / record_id / recs[record_id]["files"][file_index]["name"]


def pages_by_file():
    out = defaultdict(dict)
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        record_id, file_index, page = pc.parse_page_id(row["page_id"])
        out[(record_id, file_index)][page] = row
    return out


def frame(by_file, exclude):
    """The held-out strata, defined in the protocol before anything was drawn."""
    likely_true, likely_false = [], []
    for (record_id, file_index), pages in sorted(by_file.items()):
        if record_id in exclude:
            continue
        for page, row in sorted(pages.items()):
            if row.get("error") or row.get("form_class") not in ("g1", "w2"):
                continue
            if row.get("part") != "face":
                continue
            nxt = pages.get(page + 1)
            if nxt and not nxt.get("error"):
                same_family = nxt.get("form_class") == row.get("form_class")
                if nxt.get("part") in SECTIONS and same_family:
                    likely_true.append((record_id, file_index, page, page + 1))
                elif nxt.get("part") in BACKISH and not same_family:
                    # Adjacent, so proximity says pair and the paper does not.
                    likely_false.append((record_id, file_index, page, page + 1))
            later = [p for p, r in sorted(pages.items())
                     if p > page + 2 and not r.get("error")
                     and r.get("part") in BACKISH]
            if later:
                likely_false.append((record_id, file_index, page, later[0]))
    return likely_true, likely_false


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--screen", action="store_true",
                    help="report the go/no-go count and write nothing")
    ap.add_argument("--size", type=int, default=30)
    args = ap.parse_args()

    render.preflight()
    recs = records()
    by_file = pages_by_file()
    exclude = seen_by_alex()
    likely_true, likely_false = frame(by_file, exclude)
    print(f"records excluded because Alex has seen their pages: "
          f"{len(exclude)} (DEFECTS #56)")
    cache = papermatch.MarkCache(CACHE)
    hashes: dict = {}

    def marks(record_id, file_index, page):
        pdf = pdf_of(recs, record_id, file_index)
        hashes.setdefault(pdf, render.doc_hash(pdf))
        return papermatch.page_marks(pdf, page, cache, hashes[pdf])

    def screen(pairs, label):
        keep, thin, unreadable = [], 0, 0
        for n, (record_id, file_index, a, b) in enumerate(pairs, 1):
            try:
                ma, mb = (marks(record_id, file_index, a),
                          marks(record_id, file_index, b))
            except Exception:                           # noqa: BLE001
                # Counted, not swallowed. It used to `continue` silently, so a
                # pair dropped for being unreadable was reported as though it
                # had never been considered (DEFECTS #68).
                unreadable += 1
                continue
            if min(len(ma), len(mb)) >= paper.MIN_MARKS_AGREEING:
                keep.append((record_id, file_index, a, b))
            else:
                thin += 1
            if n % 40 == 0:
                print(f"    {label}: {n}/{len(pairs)}", flush=True)
        if unreadable:
            print(f"    {label}: {unreadable} pairs unreadable, excluded "
                  f"and counted (DEFECTS #68)")
        return keep, thin

    print(f"held-out frame, from the protocol:")
    print(f"  likely-true  {len(likely_true):3d} pairs")
    print(f"  likely-false {len(likely_false):3d} pairs\n")
    print("screening for scoreability under the FROZEN mechanism "
          f"({paper.MIN_MARKS_AGREEING} marks on both pages)\n")

    true_ok, true_thin = screen(likely_true, "likely-true")
    false_ok, false_thin = screen(likely_false, "likely-false")

    print(f"\n  likely-true  scoreable {len(true_ok):3d}, too few marks "
          f"{true_thin:3d}")
    print(f"  likely-false scoreable {len(false_ok):3d}, too few marks "
          f"{false_thin:3d}")
    print(f"\nGO/NO-GO: {len(true_ok)} scoreable likely-true pairs against a "
          f"floor of {FLOOR}.")
    if len(true_ok) < FLOOR:
        print("  BELOW FLOOR. The sitting does not run as designed. The choice")
        print("  of widening the frame or fetching more records is Alex's, and")
        print("  the protocol says fetch about 110 more records rather than")
        print("  weaken the bar.")
    else:
        print("  Clear. The sitting runs.")

    if args.screen:
        print("\n--screen: nothing written.")
        return

    if len(true_ok) < FLOOR:
        raise SystemExit("\nrefusing to build a sheet below the floor.")

    refuse_if_filled(SHEET, "verdict")
    # Two thirds likely-true, one third likely-false. The denominator that
    # matters is the pairs Alex judges same-sheet and the rule needs at least
    # 8 of them, so the true stratum is sized to clear that with room; the
    # false stratum is there to catch a false confirmation with a human label
    # on it, and Part A already carries the statistical weight on that side.
    rng = random.Random(SEED)
    want_true = min(2 * args.size // 3, len(true_ok))
    want_false = min(args.size - want_true, len(false_ok))
    chosen = ([("likely_true",) + p
               for p in rng.sample(true_ok, want_true)]
              + [("likely_false",) + p
                 for p in rng.sample(false_ok, want_false)])
    rng.shuffle(chosen)
    print(f"\ndrawing {want_true} likely-true and {want_false} likely-false, "
          f"seed {SEED}")

    IMAGES.mkdir(parents=True, exist_ok=True)
    VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    rows, sealed = [], {}
    for index, (stratum, record_id, file_index, a, b) in enumerate(chosen, 1):
        item = f"pair-{index:02d}"
        verdict = paper.compare(marks(record_id, file_index, a),
                                marks(record_id, file_index, b))
        sealed[item] = {"stratum": stratum, "record_id": record_id,
                        "file_index": file_index, "pages": [a, b],
                        "confirmed": verdict.confirmed,
                        "margins": [round(m, 4) for m in verdict.margins],
                        "transform": verdict.transform,
                        "reason": verdict.reason}
        for side, page in (("A", a), ("B", b)):
            write_masked(recs, record_id, file_index, page,
                         marks(record_id, file_index, page),
                         IMAGES / f"{item}_{side}.png")
        rows.append({"item": item, "sheet_A": f"{item}_A.png",
                     "sheet_B": f"{item}_B.png", "verdict": "",
                     "evidence": "", "note": ""})

    import csv
    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    blob = json.dumps(sealed, sort_keys=True).encode()
    VERDICTS.write_text(json.dumps(
        {"sha256": hashlib.sha256(blob).hexdigest(), "verdicts": sealed},
        indent=2, sort_keys=True))
    print(f"\nsheet:      {SHEET}  ({len(rows)} rows, shuffled)")
    print(f"images:     {IMAGES}")
    print(f"verdicts:   {VERDICTS}  sha256 "
          f"{hashlib.sha256(blob).hexdigest()[:16]}")
    print("\nThe verdicts are sealed and hashed before the sheet is judged. "
          "Row ids\ncarry no record, no page number and no stratum.")


def _hidden(dark, marks, rounds: int = 4):
    """Pixels to paint out so the mechanism finds nothing on this page.

    Iterated, and that is not belt-and-braces. Masking one component can leave
    a fragment that the opening then reads as a mark in its own right; a single
    pass left a surviving mark on one page of thirty. The loop re-detects and
    masks again until nothing is found, so the property the sitting depends on
    is established rather than assumed.
    """
    from scipy import ndimage

    height, width = dark.shape
    pad = max(1, int(MASK_PAD_IN * 300))
    hide = np.zeros_like(dark)

    for _ in range(rounds):
        if not marks:
            break
        labels, _ = ndimage.label(ndimage.binary_opening(
            dark & ~hide, structure=np.ones((3, 3))))
        for mark in marks:
            cx = min(max(int(mark.x * width), 0), width - 1)
            cy = min(max(int(mark.y * height), 0), height - 1)
            index = labels[cy, cx]
            if index:
                hide |= labels == index
            else:
                # A crescent can put its centroid outside itself.
                side = pad * 4
                hide[max(0, cy - side):cy + side,
                     max(0, cx - side):cx + side] = True
        hide = ndimage.binary_dilation(hide, structure=np.ones((pad, pad)))
        marks = paper.solid_marks(dark & ~hide)
    return hide, marks


def write_masked(recs, record_id, file_index, page, marks, out: Path) -> None:
    """The page with every detected mark painted out.

    The mechanism reads the SHAPE of a mark, so the shape is what has to go.
    The actual connected component is masked rather than a square derived from
    the mark's area: the corner blot on 1495414 is 197x148 px and an
    area-derived square is 142x142, so a third of every irregular mark
    survived. Recomputed here rather than carried on `Mark`, because
    `pipeline/paper.py` is frozen and masking is presentation, not mechanism.
    """
    pdf = pdf_of(recs, record_id, file_index)
    array = np.asarray(render.extract_page_image(pdf, page).convert("L"))
    hide, left = _hidden(array < 128, marks)
    if left:
        raise SystemExit(
            f"{record_id}-{file_index} p{page}: {len(left)} marks survive "
            f"masking. The sitting would not be blind; refusing to write it.")
    shown = np.where(hide, 255, array).astype(np.uint8)
    render.downscale_image(Image.fromarray(shown, mode="L").convert("RGB"),
                           cap=2400).save(out)


def masking_is_complete(recs, record_id, file_index, page, marks) -> bool:
    """Would the mechanism still find anything on the masked page?

    If a mark survives, the sitting is not blind and the result means nothing.
    """
    pdf = pdf_of(recs, record_id, file_index)
    array = np.asarray(render.extract_page_image(pdf, page).convert("L"))
    return not _hidden(array < 128, marks)[1]


if __name__ == "__main__":
    main()
