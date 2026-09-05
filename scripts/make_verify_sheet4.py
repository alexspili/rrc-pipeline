#!/usr/bin/env python3
"""The fourth verification sitting: the whole held-out population.

docs/labeling-protocol-reassemble.md, "The fourth sitting", written on
2026-09-05 before any of the twenty-one was looked at. There is no draw: every
attachment not judged in an earlier sitting goes on the sheet, so precision
comes out a counted fact rather than an estimate.

Each row carries what the attachment rested on: the fields that agreed, the
printed box the reader says each value came from, and the received stamps of
both pages. A pair fails if the pages are not one report **or** if a value the
attachment depended on came from the wrong box, so both are on one sheet.

Refuses to overwrite a sheet that has been keyed. sheet 2's builder had no such
guard, and DEFECTS #26 is what happens without one: a rerun replaced 405
hand-keyed rows with blanks.

No API calls. Everything comes from the identity cache.
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
from pipeline.guard import refuse_if_filled        # noqa: E402
from pipeline import identity                      # noqa: E402
from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_identity.jsonl"
FIXTURES = ROOT / "tests" / "fixtures"
EARLIER = ("attachment_verify.csv", "attachment_verify_2.csv",
           "attachment_verify_3.csv")
SHEET = FIXTURES / "attachment_verify_4.csv"
OUT = ROOT / "data" / "labelset" / "verify_pairs_4"

#: Pre-registered regression conditions. Reported beside the count, never
#: traded against it.
PINS = {"A": (("1493495", 0, 10), 9, "must attach"),
        "B": (("1495193", 0, 8), 7, "must attach"),
        "E": (("1495193", 0, 8), 9, "must NOT attach")}


def already_judged() -> set:
    """Every (record, file, pages) an earlier sitting put in front of Alex.

    Read tolerantly: a sheet comes back from a spreadsheet and has arrived
    with Mac Roman dashes before, which a strict utf-8 read refuses.
    """
    out = set()
    for name in EARLIER:
        path = FIXTURES / name
        if not path.exists():
            continue
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for row in csv.DictReader(io.StringIO(raw)):
            if row.get("part", "A") != "A":
                continue
            try:
                pages = tuple(sorted(int(x) for x in row["pages"].split()))
                out.add((row["record_id"].strip(),
                         int(row["file_index"])) + pages)
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
    return out


def main() -> None:
    # Before anything is built, and before any file is touched. The guard in
    # sheet 3's builder ran thirty lines after the deletion it guarded
    # (DEFECTS #34), so this one runs first or not at all.
    refuse_if_filled(SHEET, "verdict")

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
            key = ((doc["record_id"], int(doc["file_index"]))
                   + tuple(sorted((page, doc["face"]))))
            if key not in judged:
                pool.append((doc, page))

    rows, wanted = [], set()
    for doc, page in sorted(pool, key=lambda x: (x[0]["record_id"],
                                                 x[0]["file_index"], x[1])):
        rid, fi, face = doc["record_id"], int(doc["file_index"]), doc["face"]
        fields = dict(doc["evidence"]).get(page, [])
        a, b = read(rid, fi, face), read(rid, fi, page)
        boxes = "; ".join(
            f"{f}: p{face} <- {(a.found_in.get(f) or '?')[:40]} | "
            f"p{page} <- {(b.found_in.get(f) or '?')[:40]}"
            for f in fields if f != "received_stamps" and a and b)
        stamps = (f"p{face}: "
                  + ("; ".join(f"{o} {d}" for o, d in a.stamps) or "none"
                     if a else "unread")
                  + f"   /   p{page}: "
                  + ("; ".join(f"{o} {d}" for o, d in b.stamps) or "none"
                     if b else "unread"))
        rows.append({
            "item": f"{rid}-{fi} p{page}+p{face}",
            "record_id": rid, "file_index": fi, "pages": f"{face} {page}",
            "joined_on": ", ".join(fields),
            "where_each_value_came_from": boxes,
            "received_stamps": stamps,
            "verdict": "", "note": ""})
        wanted.add((rid, fi, (face, page)))

    if not rows:
        raise SystemExit("nothing unjudged left; the population is exhausted")

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

    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"attached pages corpus-wide:          {attachments}")
    print(f"already judged in earlier sittings:  {attachments - len(pool)}")
    print(f"on this sheet:                       {len(pool)}")
    print("  the protocol takes the whole population, not a sample, so this "
          "is\n  everything left rather than a draw.\n")

    home = {}
    for doc in docs:
        for page in doc["pages"]:
            if page != doc["face"]:
                home[(doc["record_id"], int(doc["file_index"]), page)] = \
                    doc["face"]
    print("pre-registered pins, reported and not traded:")
    for name, (target, face, kind) in PINS.items():
        got = home.get(target)
        ok = (got == face) if kind == "must attach" else (got != face)
        print(f"  {name} {target} {kind} {face}: "
              f"{'PASS' if ok else 'FAIL'} (attached to {got})")

    print(f"\nsheet:  {SHEET}")
    print(f"images: {OUT}  ({len(list(OUT.glob('*.png')))} pages)\n")
    for row in rows:
        print(f"  {row['item']:26s} joined on {row['joined_on']}")


if __name__ == "__main__":
    main()
