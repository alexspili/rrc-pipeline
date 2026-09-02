#!/usr/bin/env python3
"""Crop a page to what the model says it read, at full resolution.

Takes the region the model returned alongside a value and cuts that part of the
page out of the source scan with no downscaling, so a human can check the claim
against the paper.

Two things at once. It settles whether a disputed value was read or invented,
and it is the first test of whether the provenance boxes land on the field they
name, which nothing has measured yet.

    python scripts/inspect_values.py 2:identity.completion_date ...
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw                   # noqa: E402

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import render                       # noqa: E402

TRUTH = ROOT / "tests" / "fixtures" / "extract_truth.csv"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "labelset" / "inspect"

#: How much of the page around the box to keep, as a fraction of the page.
#: A box with no context is unreadable: a reviewer needs the field label
#: beside the value to judge whether the value belongs to it.
PAD = 0.06


def documents():
    docs = {}
    for row in csv.DictReader(TRUTH.open(encoding="utf-8-sig")):
        seq = int(row["seq"])
        doc = docs.setdefault(seq, {"record_id": row["record_id"],
                                    "pages": tuple(int(p) for p in
                                                   row["pages"].split()),
                                    "fields": {}})
        doc["fields"][row["field"]] = row
    return docs


def files_of(record_id: str):
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            return json.loads(line)["files"]
    sys.exit(f"{record_id} not in the manifest")


def report_for(doc):
    pdf = RAW / doc["record_id"] / files_of(doc["record_id"])[0]["name"]
    cache = classify.ResultCache(CACHE, prompt_hash=extractor.PROMPT_HASH)
    result = extractor.extract_document(
        None, pdf, doc["pages"], record_id=doc["record_id"], file_index=0,
        cache=cache)
    return pdf, result.report


def value_of(report, name):
    group, _, field = name.partition(".")
    if group == "document":
        return report.form_revision
    return {"identity": report.identity, "completion": report.completion,
            "test": report.test}.get(group, {}).get(field)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="+", metavar="SEQ:field")
    args = ap.parse_args()

    docs = documents()
    OUT.mkdir(parents=True, exist_ok=True)
    render.preflight()

    for target in args.targets:
        seq_text, _, name = target.partition(":")
        seq = int(seq_text)
        doc = docs[seq]
        pdf, report = report_for(doc)
        value = value_of(report, name) if report else None

        label = doc["fields"].get(name, {})
        print(f"\ndoc {seq}  {doc['record_id']}  {name}")
        print(f"   labelled  {label.get('status','?'):22s} "
              f"{label.get('value','')[:44]!r}")
        if value is None:
            print("   model     (field absent from the response)")
            continue
        print(f"   model     {value.status.value:22s} "
              f"{(value.raw or value.value or '')[:44]!r}")
        if value.region is None:
            print("   no region: nothing to crop")
            continue

        page = value.region.page
        image = render.extract_page_image(pdf, page)
        width, height = image.size
        left, top, right, bottom = value.region.box
        box = (max(0, int((left - PAD) * width)),
               max(0, int((top - PAD) * height)),
               min(width, int((right + PAD) * width)),
               min(height, int((bottom + PAD) * height)))

        crop = image.crop(box).convert("RGB")
        draw = ImageDraw.Draw(crop)
        draw.rectangle(
            [int((left * width) - box[0]), int((top * height) - box[1]),
             int((right * width) - box[0]), int((bottom * height) - box[1])],
            outline=(220, 0, 0), width=max(2, width // 500))

        stem = f"{seq:02d}_{doc['record_id']}_p{page:03d}_{name.replace('.', '-')}"
        crop.save(OUT / f"{stem}.png")
        print(f"   crop      {crop.size[0]}x{crop.size[1]}px from a "
              f"{width}x{height} page -> {stem}.png")
        print(f"   the red box is the region the model reported")

    print(f"\n{OUT}")


if __name__ == "__main__":
    main()
