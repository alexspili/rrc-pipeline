#!/usr/bin/env python3
"""The second verification sitting, drawn under the rule fixed before the fixes.

docs/labeling-protocol-reassemble.md, "The fresh sitting", written on
2026-09-04 before any of the three fixes existed: eight pairs from the
attachments the changed module makes, seed 20260904, excluding every pair from
the first sitting, and **fewer than eight means all are judged and the count is
reported, never topped up**.

The changed module makes 11 attachments. Four are pairs Alex has already
judged, so the pool is 7 and all 7 are judged. That is the rule firing, not a
shortfall being papered over.

Each row carries what the attachment rested on: the fields that agreed, the
printed box the reader says each came from, and the received stamps of both
pages. The rule counts a pair as failed if the pages are not one report **or**
if a value the attachment depended on came from the wrong box, so both are on
the sheet rather than in a separate part.

No API calls.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import identity                      # noqa: E402
from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_identity.jsonl"
FIRST = ROOT / "tests" / "fixtures" / "attachment_verify.csv"
SHEET = ROOT / "tests" / "fixtures" / "attachment_verify_2.csv"
OUT = ROOT / "data" / "labelset" / "verify_pairs_2"

#: The three pairs judged correct in the first sitting. The pre-registered
#: regression condition is that all three still attach.
REGRESSION = {("1493495", 0, 10, 9), ("1495193", 0, 8, 7),
              ("1493608", 0, 6, 5)}


def already_judged():
    raw = FIRST.read_bytes().decode("utf-8", errors="replace")
    out = set()
    for row in csv.DictReader(io.StringIO(raw)):
        if row["part"] != "A":
            continue
        pages = tuple(sorted(int(x) for x in row["pages"].split()))
        out.add((row["record_id"], int(row["file_index"])) + pages)
    return out


def main() -> None:
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(CACHE, prompt_hash=identity.PROMPT_HASH)
    judged = already_judged()
    docs = [json.loads(l) for l in DOCS.open() if l.strip()]

    def read(record_id, file_index, page):
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        hit = cache.get(cache.key(render.doc_hash(pdf), page, "identity"))
        return identity.parse(hit["body"], page) if hit else None

    attachments, pool = 0, []
    for doc in docs:
        for page in doc["pages"]:
            if page == doc["face"]:
                continue
            attachments += 1
            key = (doc["record_id"], int(doc["file_index"])) + \
                tuple(sorted((page, doc["face"])))
            if key not in judged:
                pool.append((doc, page))

    rows, wanted = [], set()
    for doc, page in sorted(pool, key=lambda x: (x[0]["record_id"], x[1])):
        rid, fi, face = doc["record_id"], int(doc["file_index"]), doc["face"]
        fields = dict(doc["evidence"]).get(page, [])
        a, b = read(rid, fi, face), read(rid, fi, page)
        boxes = "; ".join(
            f"{f}: p{face} <- {(a.found_in.get(f) or '?')[:40]} | "
            f"p{page} <- {(b.found_in.get(f) or '?')[:40]}"
            for f in fields if f != "received_stamps" and a and b)
        stamps = (f"p{face}: " + ("; ".join(f"{o} {d}" for o, d in a.stamps)
                                  or "none")
                  + f"   /   p{page}: "
                  + ("; ".join(f"{o} {d}" for o, d in b.stamps) or "none"))
        rows.append({
            "item": f"{rid}-{fi} p{page}+p{face}",
            "record_id": rid, "file_index": fi, "pages": f"{face} {page}",
            "joined_on": ", ".join(fields),
            "where_each_value_came_from": boxes,
            "received_stamps": stamps,
            "verdict": "", "note": ""})
        wanted.add((rid, fi, (face, page)))

    render.preflight()
    OUT.mkdir(parents=True, exist_ok=True)
    for rid, fi, pages in sorted(wanted):
        pdf = RAW / rid / records[rid]["files"][fi]["name"]
        for page in pages:
            name = f"{rid}-{fi}_p{page:03d}.png"
            if (OUT / name).exists():
                continue
            render.downscale_image(
                render.extract_page_image(pdf, page).convert("RGB"),
                cap=2400).save(OUT / name)

    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"attachments the changed module makes: {attachments}")
    print(f"already judged in the first sitting:  {attachments - len(pool)}")
    print(f"pool for this sitting:                {len(pool)}")
    if len(pool) < 8:
        print("  fewer than eight, so ALL are judged and the count is "
              "reported. The rule forbids topping it up.")
    print(f"\nsheet:  {SHEET}")
    print(f"images: {OUT}  ({len(list(OUT.glob('*.png')))} pages)\n")
    for row in rows:
        print(f"  {row['item']:24s} joined on {row['joined_on']}")


if __name__ == "__main__":
    main()
