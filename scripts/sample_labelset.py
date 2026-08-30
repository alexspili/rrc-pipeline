#!/usr/bin/env python3
"""Draw the stage-1 labelled page sample and render it for hand labelling.

Uniform random over all 3,689 pages, seeded. Uniform is the only sample that
gives an unbiased estimate of overall accuracy and of the true class prior;
stratifying by anything would bias both, and there is no metadata to stratify
on anyway (document_type is "SUPPORTING DOCUMENT" on all 249 files).

At n=60 the error bar on overall accuracy is roughly +/-6pp at 90%. That goes
in the README rather than being hidden. Stage 2 adds pages stratified by
predicted class to get per-class precision, after the smoke run.

Thumbnails land in data/ and stay there: they are page images of real records
and carry surface owners' names, addresses and phone numbers (CLAUDE.md rule
3). The CSV carries class names and page coordinates only, no text off the
page, so it is safe to commit once filled.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # scripts/ is not a package

from pipeline import pageclass as pc   # noqa: E402
from pipeline import render            # noqa: E402
MANIFEST = ROOT / "data" / "manifest.jsonl"
THUMBS = ROOT / "data" / "labelset" / "thumbs"
TEMPLATE = ROOT / "tests" / "fixtures" / "labels_stage1.csv"

SEED = 20260830
SIZE = 60
THUMB_CAP = 1400          # readable enough to find a form number by eye

COLUMNS = ["page_id", "record_id", "file_index", "page",
           "native_w", "native_h", "oversize",
           "form_class", "part", "orientation", "note"]


def all_pages() -> list[tuple[str, int, int, str]]:
    pages = []
    for line in MANIFEST.open():
        if not line.strip():
            continue
        record = json.loads(line)
        for index, entry in enumerate(record["files"]):
            for page in range(1, (entry.get("pages") or 0) + 1):
                pages.append((record["record_id"], index, page, entry["name"]))
    return pages


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", type=int, default=SIZE)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--no-thumbs", action="store_true",
                    help="rewrite the CSV template without re-rendering")
    args = ap.parse_args()

    render.preflight()
    pages = all_pages()
    print(f"{len(pages):,} pages in the corpus")

    sample = sorted(random.Random(args.seed).sample(pages, args.size))
    THUMBS.mkdir(parents=True, exist_ok=True)

    rows = []
    dims_cache: dict[Path, list[tuple[int, int]]] = {}
    for record_id, file_index, page, name in sample:
        pdf = ROOT / "data" / "raw" / record_id / name
        if pdf not in dims_cache:
            dims_cache[pdf] = render.page_dimensions(pdf)
        width, height = dims_cache[pdf][page - 1]
        page_id = pc.page_id(record_id, file_index, page)

        if not args.no_thumbs:
            png, _ = render.render_page_png(pdf, page, cap=THUMB_CAP)
            (THUMBS / f"{page_id}.png").write_bytes(png)

        rows.append({
            "page_id": page_id, "record_id": record_id,
            "file_index": file_index, "page": page,
            "native_w": width, "native_h": height,
            "oversize": "yes" if pc.is_oversize(width, height) else "no",
            "form_class": "", "part": "", "orientation": "", "note": "",
        })
        print(f"  {page_id}  {width}x{height}")

    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    with TEMPLATE.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nthumbnails: {THUMBS}")
    print(f"template:   {TEMPLATE}")
    print("\nfill form_class, part and orientation for each row.")
    print("\n  form_class, extraction targets:")
    print("    " + "  ".join(sorted(c.value for c in pc.EXTRACTION_TARGETS)))
    print("  form_class, identity-bearing:")
    print("    " + "  ".join(sorted(c.value for c in pc.IDENTITY_BEARING)))
    print("  form_class, census only:")
    print("    " + "  ".join(sorted(c.value for c in pc.CENSUS_ONLY)))
    print("  part (leave blank for census-only classes):")
    print("    " + "  ".join(p.value for p in pc.Part))
    print("  orientation:")
    print("    " + "  ".join(o.value for o in pc.Orientation))


if __name__ == "__main__":
    main()
