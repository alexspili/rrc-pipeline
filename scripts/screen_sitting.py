#!/usr/bin/env python3
"""How many adjacent page pairs in the district 02 frame can be scored at all?

Spends nothing. No API calls, no model calls.

**Why this comes before the sitting rather than after.** The sitting's size is
decided by how many pairs the mechanism can score, and that number has never
been measured on this population. Guessing it and then discovering the sheet is
too thin is how the 2026-09-06 sitting nearly failed to run (DEFECTS #56's
measured cost paragraph). So the count is taken first and reported to Alex
before a single pair is drawn.

**No classifier is involved and that is deliberate.** The paper channels do not
need to know what form a page is, so the frame is plain adjacent pairs. That
also avoids the trap of DEFECTS #62, where `form_class` was asked to say which
pairs were not one sheet and was wrong six times in seven.

**Scoreable means both pages carry at least `MIN_SMALL_AGREEING` small marks.**
A pair the mechanism cannot score is not evidence about anything, and counting
it as a pass would inflate safety by dilution.

    --records N   stop after N records, for a quick look
    --limit N     cap pages read per file (the frame holds one 288-page file)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper, papermatch, render                # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SPLIT = ROOT / "tests" / "fixtures" / "paper_record_split.csv"
CACHE = ROOT / "data" / "cache" / "paper_small"
REPORT = ROOT / "data" / "probe" / "sitting_screen.jsonl"

#: The half these records were reserved as. Development and held_out are not
#: touched here: this measures the population the sitting will be drawn from.
FRAME = "sitting_frame"

#: A file longer than this is a bound volume rather than a filing, and its
#: adjacent pairs are not the thing being measured. The frame holds one file of
#: 288 pages against a median of 11.
MAX_PAGES = 60


def frame_records() -> set:
    rows = csv.DictReader(io.StringIO(SPLIT.read_text()))
    return {r["record_id"] for r in rows if r["half"] == FRAME}


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=int, default=0)
    ap.add_argument("--limit", type=int, default=MAX_PAGES)
    args = ap.parse_args()

    render.preflight()
    recs = records()
    wanted = sorted(frame_records())
    if args.records:
        wanted = wanted[:args.records]
    cache = papermatch.SmallMarkCache(CACHE)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    print(f"screening {len(wanted)} records of the {FRAME}, "
          f"pages capped at {args.limit} a file")
    print(f"scoreable = both pages carry at least "
          f"{paper.MIN_SMALL_AGREEING} small marks\n")

    counts = Counter()
    per_record = Counter()
    rows = []
    for n, record_id in enumerate(wanted, 1):
        record = recs.get(record_id)
        if not record:
            continue
        for file_index, entry in enumerate(record["files"]):
            pages = entry.get("pages") or 0
            if pages > args.limit:
                counts["pages_skipped_long_file"] += pages
                continue
            pdf = RAW / record_id / entry["name"]
            if not pdf.exists():
                continue
            doc = render.doc_hash(pdf)
            marks = {}
            for page in range(1, pages + 1):
                try:
                    marks[page] = papermatch.page_small_marks(
                        pdf, page, cache, doc)
                except Exception:                            # noqa: BLE001
                    counts["pages_unreadable"] += 1
            for page in range(1, pages):
                a, b = marks.get(page), marks.get(page + 1)
                if a is None or b is None:
                    continue
                counts["adjacent_pairs"] += 1
                ok = min(len(a), len(b)) >= paper.MIN_SMALL_AGREEING
                counts["scoreable" if ok else "too_few_marks"] += 1
                if ok:
                    per_record[record_id] += 1
                rows.append({"record_id": record_id,
                             "file_index": file_index,
                             "pages": [page, page + 1],
                             "marks": [len(a), len(b)],
                             "scoreable": ok})
        if n % 10 == 0:
            print(f"  {n}/{len(wanted)} records, "
                  f"{counts['scoreable']} scoreable pairs so far", flush=True)

    with REPORT.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    print(f"\nadjacent pairs seen        {counts['adjacent_pairs']:6d}")
    print(f"  scoreable                {counts['scoreable']:6d}")
    print(f"  too few marks            {counts['too_few_marks']:6d}")
    if counts["adjacent_pairs"]:
        rate = counts["scoreable"] / counts["adjacent_pairs"]
        print(f"  scoreable rate           {rate:6.1%}")
    print(f"records with a scoreable pair {len(per_record):5d} "
          f"of {len(wanted)}")
    if counts["pages_skipped_long_file"]:
        print(f"pages skipped, long files  {counts['pages_skipped_long_file']:6d}")
    if counts["pages_unreadable"]:
        print(f"pages unreadable           {counts['pages_unreadable']:6d}")
    print(f"\nrows: {REPORT}")
    print("\nThe sitting is capped at one pair per record, so the number that\n"
          "sizes it is 'records with a scoreable pair', not the pair count.")


if __name__ == "__main__":
    main()
