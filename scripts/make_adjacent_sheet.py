#!/usr/bin/env python3
"""The district 02 sitting: 40 adjacent pairs, judged with a three-way label.

Spends nothing. No API calls.

`docs/labeling-protocol-adjacent.md`, written before any pair was drawn. The
mechanism and every constant were frozen first, in commit
1a0182976062931bdcf416f3a104975f91d3cac6.

**What it buys.** `compare_small` has a measured false-confirmation rate on
pairs from two different records, 1 of 400. It has none at all on ADJACENT
pairs that are not one sheet, which is the only regime reassembly would put to
it, and no trustworthy label for that regime exists anywhere (DEFECTS #62).

**There is no masking, and the protocol says so out loud.** The channel now
reads small specks near the paper edge, which is what Alex reads; masking them
would blank the page edges and leave nothing to judge. What guards the failure
mode instead is the three-way label: a staple or punch goes through every sheet
of a bundle at the same place, so the machine's one predicted failure is
confirming a bundle-mate, and `same-bundle` is what makes that visible.

    --screen   report the counts and write nothing
    (default)  build the sheet
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper, papermatch, render                 # noqa: E402
from pipeline.guard import refuse_if_filled                    # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SPLIT = ROOT / "tests" / "fixtures" / "paper_record_split.csv"
SCREEN = ROOT / "data" / "probe" / "sitting_screen.jsonl"
CACHE = ROOT / "data" / "cache" / "paper_small"
SHEET = ROOT / "tests" / "fixtures" / "adjacent_sitting.csv"
IMAGES = ROOT / "data" / "labelset" / "adjacent_sitting"
VERDICTS = ROOT / "data" / "probe" / "adjacent_sitting_verdicts.json"

SEED = 20260907
SIZE = 40

#: Below this many records holding a scoreable pair the sitting does not run as
#: designed. 40 pairs need 40 records, one pair each.
FLOOR = SIZE


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def frame_records() -> set:
    rows = csv.DictReader(io.StringIO(SPLIT.read_text()))
    return {r["record_id"] for r in rows if r["half"] == "sitting_frame"}


def scoreable() -> dict:
    """Scoreable adjacent pairs, grouped by record. From the screen, which ran
    before the draw and whose count went to Alex first."""
    by_record: dict = {}
    for line in SCREEN.open():
        row = json.loads(line)
        if row["scoreable"]:
            by_record.setdefault(row["record_id"], []).append(row)
    return by_record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--screen", action="store_true")
    ap.add_argument("--size", type=int, default=SIZE)
    args = ap.parse_args()

    render.preflight()
    recs = records()
    frame = frame_records()
    pool = {k: v for k, v in scoreable().items() if k in frame}

    print(f"records in the sitting frame        {len(frame):4d}")
    print(f"records holding a scoreable pair    {len(pool):4d}")
    print(f"scoreable pairs available           "
          f"{sum(len(v) for v in pool.values()):4d}")
    print(f"\nGO/NO-GO: {len(pool)} records against a floor of {FLOOR}.")
    if len(pool) < FLOOR:
        print("  BELOW FLOOR. The sitting does not run as designed.")
    else:
        print("  Clear. The sitting runs.")
    if args.screen:
        print("\n--screen: nothing written.")
        return
    if len(pool) < FLOOR:
        raise SystemExit("\nrefusing to build a sheet below the floor.")

    refuse_if_filled(SHEET, "verdict")
    rng = random.Random(SEED)
    chosen_records = rng.sample(sorted(pool), args.size)
    chosen = [rng.choice(sorted(pool[r], key=lambda p: p["pages"]))
              for r in chosen_records]
    rng.shuffle(chosen)
    print(f"\ndrawing {len(chosen)} pairs, one per record, seed {SEED}")

    IMAGES.mkdir(parents=True, exist_ok=True)
    VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    cache = papermatch.SmallMarkCache(CACHE)
    rows, sealed = [], {}
    tally = Counter()
    for index, pair in enumerate(chosen, 1):
        item = f"pair-{index:02d}"
        record_id, file_index = pair["record_id"], pair["file_index"]
        page_a, page_b = pair["pages"]
        pdf = RAW / record_id / recs[record_id]["files"][file_index]["name"]
        doc = render.doc_hash(pdf)
        a = papermatch.page_small_marks(pdf, page_a, cache, doc)
        b = papermatch.page_small_marks(pdf, page_b, cache, doc)
        verdict = paper.compare_small(a, b)
        tally[verdict.confirmed] += 1
        sealed[item] = {"record_id": record_id, "file_index": file_index,
                        "pages": [page_a, page_b],
                        "starts_on": "even" if page_a % 2 == 0 else "odd",
                        "confirmed": verdict.confirmed,
                        "transform": verdict.transform,
                        "agreeing": verdict.agreeing,
                        "control": verdict.control,
                        "marks": [len(a), len(b)],
                        "reason": verdict.reason}
        for side, page in (("A", page_a), ("B", page_b)):
            image = render.extract_page_image(pdf, page)
            render.downscale_image(image.convert("RGB"), cap=2400).save(
                IMAGES / f"{item}_{side}.png")
        rows.append({"item": item, "sheet_A": f"{item}_A.png",
                     "sheet_B": f"{item}_B.png", "verdict": "",
                     "evidence": "", "note": ""})
        if index % 10 == 0:
            print(f"    {index}/{len(chosen)}", flush=True)

    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    blob = json.dumps(sealed, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    VERDICTS.write_text(json.dumps({"sha256": digest, "verdicts": sealed},
                                   indent=2, sort_keys=True))

    print(f"\nsheet:      {SHEET}  ({len(rows)} rows, shuffled)")
    print(f"images:     {IMAGES}")
    print(f"verdicts:   {VERDICTS}  sha256 {digest[:16]}")
    print(f"\nthe mechanism confirms {tally[True]} of {len(chosen)} on this "
          f"sheet, sealed before it goes out")
    print("\nverdict column takes one of: same-sheet, same-bundle, different, "
          "cannot-tell.\n'same-bundle' means one filing or one stapled bundle "
          "but NOT one sheet;\nit is the machine's predicted failure and the "
          "reason the label has three values.")


if __name__ == "__main__":
    main()
