#!/usr/bin/env python3
"""Draw every provenance box on its whole page, numbered, with a legend.

Origin: DEFECTS #29. The crop-based check cropped to the model's own box, so
it showed the wrong region and tested the model against itself. These
overlays show the entire page with every present-value box on it, which is
what lets a human see whether the drift is systematic.

Also computes, per document, the one anchor whose true position is known a
priori on every form: `form_revision` is printed in the top-right corner, so
its box centre across all documents is a free estimate of the bias.

With --sheet, writes the grading sheet for the four documents named in the
protocol, numbered identically to the overlays, behind the overwrite guard
(DEFECTS #26).

No API calls: reads the finished run's cache under the prompt hash the run
recorded.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import pageclass as pc              # noqa: E402
from pipeline import render                       # noqa: E402
from pipeline.guard import refuse_if_filled       # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
OUT = ROOT / "data" / "labelset" / "overlay"
SHEET = ROOT / "tests" / "fixtures" / "box_grades.csv"

CAP = 2000
MIN_SHORT_EDGE = 700

#: The four graded documents, fixed in the protocol before grading: one per
#: era bucket, about 110 present-value boxes between them, including a G-1
#: and a section page. Ground-truth sheet seq numbers 3, 7, 14 and 6.
GRADED_DOCS = [("1493608", 0, (5, 6)),      # 1966, two pages
               ("1495195", 0, (15,)),       # 1975
               ("1912687", 0, (2,)),        # 1983, G-1
               ("1495193", 0, (8,))]        # unknown era, section page


def manifest():
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def walk_values(report):
    """Every present value with a region, in the schema's stable order."""
    return [(name, value) for name, value in report.named_values()
            if value.region is not None]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true",
                    help="also write the grading sheet for the four "
                         "protocol documents")
    args = ap.parse_args()

    records = manifest()
    cache = classify.ResultCache(CACHE,
                                 prompt_hash=extractor.recorded_prompt_hash(SMOKE))
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*"):
        stale.unlink()
    render.preflight()

    anchors = []
    sheet_rows = []
    documents = [json.loads(l) for l in SMOKE.open() if l.strip()]
    for doc in documents:
        record_id, file_index, _ = pc.parse_page_id(doc["page_id"])
        entry = records[record_id]
        pdf = RAW / record_id / entry["files"][file_index]["name"]
        result = extractor.extract_document(
            None, pdf, tuple(doc["pages"]), record_id=record_id,
            file_index=file_index, cache=cache)
        if result.report is None:
            continue

        values = walk_values(result.report)
        rev = result.report.form_revision
        if rev.region is not None:
            anchors.append((record_id, rev.region.box))

        graded = (record_id, file_index, tuple(doc["pages"])) in \
            [(r, f, p) for r, f, p in GRADED_DOCS]

        by_page = {}
        for number, (name, value) in enumerate(values, 1):
            by_page.setdefault(value.region.page, []).append(
                (number, name, value))
            if args.sheet and graded:
                sheet_rows.append({
                    "record_id": record_id, "file_index": file_index,
                    "pages": " ".join(map(str, doc["pages"])),
                    "page": value.region.page, "box_num": number,
                    "field": name, "raw": (value.raw or "")[:60],
                    "grade": "", "handwritten": "", "note": ""})

        for page, entries in sorted(by_page.items()):
            image = render.extract_page_image(pdf, page).convert("RGB")
            width, height = image.size
            cap = CAP
            short = min(width, height)
            if short and round(max(width, height) * MIN_SHORT_EDGE / short) > cap:
                cap = round(max(width, height) * MIN_SHORT_EDGE / short)
            image = render.downscale_image(image, cap=cap)
            width, height = image.size
            render.draw_numbered_boxes(
                image, [(number, value.region.box)
                        for number, _, value in entries])
            legend = [f"{number:3d}  {name:36s} {value.raw!r}"
                      for number, name, value in entries]

            mark = "GRADED_" if graded else ""
            stem = f"{mark}{record_id}_f{file_index}_p{page:03d}"
            image.save(OUT / f"{stem}.png")
            (OUT / f"{stem}.txt").write_text(
                f"{record_id} file {file_index} page {page}: "
                f"{len(entries)} boxes\n" + "\n".join(legend) + "\n")
            print(f"  {stem}.png  {len(entries):3d} boxes")

    print("\nrevision anchor, the one field whose true position is known "
          "a priori (top-right corner):")
    if anchors:
        xs = [(b[0] + b[2]) / 2 for _, b in anchors]
        ys = [(b[1] + b[3]) / 2 for _, b in anchors]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sx = (sum((x - mx) ** 2 for x in xs) / len(xs)) ** 0.5
        sy = (sum((y - my) ** 2 for y in ys) / len(ys)) ** 0.5
        print(f"  {len(anchors)} documents: centre x {mx:.3f} +/- {sx:.3f}, "
              f"y {my:.3f} +/- {sy:.3f}")
        low = [r for r, b in anchors if (b[1] + b[3]) / 2 > 0.20]
        print(f"  boxes whose centre sits below y 0.20, nowhere near a "
              f"top-right corner: {len(low)} {low}")

    if args.sheet and sheet_rows:
        refuse_if_filled(SHEET, "grade")
        with SHEET.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(sheet_rows[0]))
            writer.writeheader()
            writer.writerows(sheet_rows)
        print(f"\ngrading sheet: {SHEET}  ({len(sheet_rows)} boxes over "
              f"{len(GRADED_DOCS)} documents)")

    print(f"\noverlays: {OUT}")


if __name__ == "__main__":
    main()
