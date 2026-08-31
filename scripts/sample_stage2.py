#!/usr/bin/env python3
"""Draw the stage-2 labelled page sample and render it for hand labelling.

Stratified over the census predictions, seeded, blinded. The design and the
reasoning for every stratum are in docs/labeling-protocol-stage2.md, which was
written and committed before this script ran.

Two seeds, both fixed in the protocol before the draw:

  DRAW_SEED    which pages are taken from each stratum
  ORDER_SEED   the row order of the sheet, shuffled across strata so that
               position leaks nothing about which stratum a page came from

Blinding is the reason this script writes two files. The workbook carries no
predicted class, no confidence and no OCR token. The stratum assignment goes to
a separate file that is committed for reproducibility and is not to be opened
while labelling.

Thumbnails land in data/ and stay there: they are page images of real records
and carry surface owners' names, addresses and phone numbers (CLAUDE.md rule 3).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # scripts/ is not a package

from pipeline import formscan                # noqa: E402
from pipeline import pageclass as pc         # noqa: E402
from pipeline import render                  # noqa: E402
from pipeline import stage2                  # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
VERIFIED = ROOT / "data" / "census" / "verify.csv"
THUMBS = ROOT / "data" / "labelset" / "thumbs_stage2"
HEADER_CACHE = ROOT / "data" / "stage2_headers.json"
TEMPLATE = ROOT / "tests" / "fixtures" / "labels_stage2.csv"
STRATA = ROOT / "tests" / "fixtures" / "stage2_strata.csv"

DRAW_SEED = 20260831
ORDER_SEED = 20260901

THUMB_CAP = 1400          # readable enough to find a form number by eye

#: Oversize pages are rendered to this short edge instead of the flat cap.
#:
#: A 11,264 x 3,040 fold-out at a 1400px long edge has a 378px short edge. The
#: model sees a squashed thumbnail and that is the point of R1, but ground
#: truth should be the best view available, not the model's view.
OVERSIZE_MIN_SHORT_EDGE = 600

COLUMNS = ["seq", "page_id", "record_id", "file_index", "page",
           "native_w", "native_h", "oversize",
           "form_class", "part", "orientation", "form_number_legible", "note"]


def header_tokens_by_page() -> dict[str, set[str]]:
    """OCR header tokens for every page, cached against the scanner's source.

    The cache key is a hash of pipeline/formscan.py. DEFECTS #15 left
    data/form_headers.json keyed on nothing at all, so a scanner change did not
    invalidate it and the fixed scanner kept returning the broken counts until
    somebody deleted the file by hand. #16 recorded that as an open gap. This
    cache does not repeat it.
    """
    fingerprint = hashlib.sha256(
        (ROOT / "pipeline" / "formscan.py").read_bytes()).hexdigest()[:16]

    if HEADER_CACHE.exists():
        cached = json.loads(HEADER_CACHE.read_text())
        if cached.get("formscan") == fingerprint:
            return {k: set(v) for k, v in cached["pages"].items()}
        print("  scanner changed since the cache was written; rescanning")

    tokens = {
        pc.page_id(record_id, file_index, page): formscan.header_tokens(text)
        for (record_id, file_index, page), text
        in formscan.page_texts(MANIFEST, RAW).items()
    }
    HEADER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    HEADER_CACHE.write_text(json.dumps(
        {"formscan": fingerprint,
         "pages": {k: sorted(v) for k, v in tokens.items()}}))
    return tokens


def census_rows() -> list[dict]:
    if not CENSUS.exists():
        sys.exit(f"missing {CENSUS}; run `make census` first")
    return [json.loads(line) for line in CENSUS.open() if line.strip()]


def verified_records() -> set[str]:
    """Records Alex rendered whole while verifying the census headline.

    Those judgements were made with the neighbouring pages visible, which the
    labelling rule forbids, so pages from these records are flagged and
    reported separately rather than dropped. Dropping them would bias the
    frame toward records nobody has looked at.
    """
    if not VERIFIED.exists():
        return set()
    with VERIFIED.open(encoding="latin-1") as fh:
        return {row["record_id"] for row in csv.DictReader(fh)}


def strata_of(rows: list[dict], tokens: dict[str, set[str]]) -> dict[str, str]:
    return {
        row["page_id"]: stage2.assign_stratum(
            row["form_class"], row["part"], bool(row["oversize"]),
            bool(row.get("error")), tokens.get(row["page_id"], set()))
        for row in rows
    }


def draw(assignment: dict[str, str]) -> dict[str, list[str]]:
    """Simple random sample without replacement inside each stratum.

    No per-record cap. Three records carry 12 predicted W-2 faces each, so the
    draws are not independent and the error bar the estimator reports is a
    floor. A cap would trade that reportable variance for an unreportable bias;
    the protocol says so and the spread is printed below.
    """
    frames: dict[str, list[str]] = defaultdict(list)
    for page_id, stratum in assignment.items():
        if stratum is not None:
            frames[stratum].append(page_id)

    rng = random.Random(DRAW_SEED)
    drawn = {}
    for stratum, size in stage2.ALLOCATION.items():
        frame = sorted(frames[stratum])
        if len(frame) < size:
            sys.exit(f"{stratum}: allocation {size} exceeds frame {len(frame)}")
        drawn[stratum] = sorted(rng.sample(frame, size))
    return drawn


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-thumbs", action="store_true",
                    help="rewrite the CSV without re-rendering thumbnails")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the frames and the draw, write nothing")
    args = ap.parse_args()

    rows = census_rows()
    by_id = {row["page_id"]: row for row in rows}
    print(f"{len(rows):,} census rows, "
          f"{sum(1 for r in rows if r.get('error'))} parse failures")

    tokens = header_tokens_by_page()
    assignment = strata_of(rows, tokens)
    frames = Counter(s for s in assignment.values() if s is not None)
    drawn = draw(assignment)
    verified = verified_records()

    print(f"\n{'stratum':32s} {'frame':>6s} {'drawn':>6s} {'records':>8s}")
    for stratum in stage2.ALLOCATION:
        pages = drawn[stratum]
        records = len({p.split("-")[0] for p in pages})
        print(f"{stratum:32s} {frames[stratum]:6d} {len(pages):6d} {records:8d}")
    total = sum(len(p) for p in drawn.values())
    scored = sum(len(drawn[s]) for s in stage2.SCORED)
    print(f"{'':32s} {sum(frames.values()):6d} {total:6d}")
    print(f"\n{scored} scored, {total - scored} in the two add-ons")

    sample = [(stratum, page_id)
              for stratum, pages in drawn.items() for page_id in pages]
    seen = sum(1 for _, p in sample if p.split("-")[0] in verified)
    print(f"{seen} of {total} pages are in a record already rendered for "
          f"verify.csv; flagged, not dropped")

    random.Random(ORDER_SEED).shuffle(sample)

    if args.dry_run:
        print("\ndry run: nothing written")
        return

    if not args.no_thumbs:
        THUMBS.mkdir(parents=True, exist_ok=True)
        for stale in THUMBS.glob("*.png"):
            stale.unlink()
        render.preflight()

    sheet, key = [], []
    for seq, (stratum, page_id) in enumerate(sample, 1):
        row = by_id[page_id]
        record_id, file_index, page = page_id.rsplit("-", 2)
        file_index, page = int(file_index), int(page)
        pdf = pdf_path(record_id, file_index)
        width, height = render.page_dimensions(pdf)[page - 1]
        oversize = pc.is_oversize(width, height)

        if not args.no_thumbs:
            cap = THUMB_CAP
            if oversize:
                short = min(width, height)
                cap = max(cap, round(max(width, height)
                                     * OVERSIZE_MIN_SHORT_EDGE / short))
            png, _ = render.render_page_png(pdf, page, cap=cap)
            (THUMBS / f"{seq:03d}_{page_id}.png").write_bytes(png)

        sheet.append({
            "seq": seq, "page_id": page_id, "record_id": record_id,
            "file_index": file_index, "page": page,
            "native_w": width, "native_h": height,
            "oversize": "yes" if oversize else "no",
            "form_class": "", "part": "", "orientation": "",
            "form_number_legible": "", "note": "",
        })
        key.append({
            "seq": seq, "page_id": page_id, "stratum": stratum,
            "predicted_class": row["form_class"] or "",
            "predicted_part": row["part"] or "",
            "confidence": row["confidence"] or "",
            "header_tokens": " ".join(sorted(tokens.get(page_id, ()))),
            "seen_in_verify": "yes" if record_id in verified else "no",
        })

    write_csv(TEMPLATE, COLUMNS, sheet)
    write_csv(STRATA, list(key[0]), key)

    print(f"\nthumbnails: {THUMBS}")
    print(f"template:   {TEMPLATE}")
    print(f"strata key: {STRATA}   DO NOT OPEN WHILE LABELLING")
    print("\nfill form_class, part, orientation and form_number_legible.")
    print("docs/labeling-protocol-stage2.md, then "
          "docs/labeling-protocol.md for the class list.")


def pdf_path(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["record_id"] == record_id:
            return RAW / record_id / record["files"][file_index]["name"]
    sys.exit(f"{record_id} is not in the manifest")


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
