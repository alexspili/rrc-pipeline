#!/usr/bin/env python3
"""Render the pages of every document in the ground-truth template.

One folder, named so that sorting by filename walks the sheet in order:
seq, record, then page. The sheet's `pages` column lists the same pages.

Thumbnails stay under data/, which is git-ignored: they are page images of
real records and carry personal information (CLAUDE.md rule 3).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                      # noqa: E402

TEMPLATE = ROOT / "tests" / "fixtures" / "extract_truth.csv"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "labelset" / "thumbs_extract"

CAP = 2000                     # readable enough to key figures by hand
MIN_SHORT_EDGE = 700           # fold-outs stay legible


def files_of(record_id: str):
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            return json.loads(line)["files"]
    sys.exit(f"{record_id} not in the manifest")


def main() -> None:
    rows = list(csv.DictReader(TEMPLATE.open()))
    docs = []
    for row in rows:
        key = (int(row["seq"]), row["record_id"], row["pages"])
        if key not in docs:
            docs.append(key)

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.png"):
        stale.unlink()
    render.preflight()

    for seq, record_id, pages in sorted(docs):
        pdf = RAW / record_id / files_of(record_id)[0]["name"]
        for page in [int(p) for p in pages.split()]:
            width, height = render.page_dimensions(pdf)[page - 1]
            cap = CAP
            short = min(width, height)
            if short and round(max(width, height) * MIN_SHORT_EDGE / short) > cap:
                cap = round(max(width, height) * MIN_SHORT_EDGE / short)
            png, sent = render.render_page_png(pdf, page, cap=cap)
            name = f"{seq:02d}_{record_id}_p{page:03d}.png"
            (OUT / name).write_bytes(png)
            print(f"  {name}  {sent[0]}x{sent[1]}")

    print(f"\n{len(docs)} documents, "
          f"{len(list(OUT.glob('*.png')))} pages -> {OUT}")


if __name__ == "__main__":
    main()
