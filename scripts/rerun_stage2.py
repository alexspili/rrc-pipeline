#!/usr/bin/env python3
"""Re-classify the 143 stage-2 labelled pages under the current prompt.

The "after" half of the before-and-after recorded in docs/modules/classify.md.
Small and synchronous rather than batched: 143 pages is not worth a batch
turnaround, and the comparison is the point of the run. CLAUDE.md rule 7's
batch default is about corpus-scale spend, which this is not.

The result cache still applies and is keyed on the prompt hash, so the prompt
change makes every page a miss and a re-run after no change costs nothing.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                    # noqa: E402
from pipeline import pageclass as pc             # noqa: E402

LABELS = ROOT / "tests" / "fixtures" / "labels_stage2.csv"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "census" / "stage2_after.jsonl"
CACHE = ROOT / "data" / "census" / "cache_stage2_after.jsonl"
ARM = "vision_1000"


def pdf_for(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["record_id"] == record_id:
            return RAW / record_id / record["files"][file_index]["name"]
    sys.exit(f"{record_id} not in the manifest")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="first N pages, for a smoke run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(LABELS.open(encoding="utf-8-sig")))
    if args.limit:
        rows = rows[:args.limit]

    print(f"{len(rows)} pages, arm {ARM}, prompt {classify.PROMPT_HASH}")
    if args.dry_run:
        return

    api = classify.client()
    cache = classify.ResultCache(CACHE)
    spend = 0.0
    written = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as out:
        for i, row in enumerate(rows, 1):
            record_id, file_index, page = pc.parse_page_id(row["page_id"])
            attempt = classify.classify_page(
                api, ARM, pdf_for(record_id, file_index), page,
                record_id=record_id, file_index=file_index, cache=cache)
            spend += attempt.cost_usd()
            label = attempt.label
            out.write(json.dumps({
                "page_id": row["page_id"],
                "form_class": label.form_class.value if label else None,
                "part": label.part.value if label and label.part else None,
                "orientation": label.orientation.value if label else None,
                "confidence": label.confidence.value if label else None,
                "alt_class": (label.alt_class.value
                              if label and label.alt_class else None),
                "form_number_legible": (label.form_number_legible
                                        if label else None),
                "oversize": label.oversize if label else None,
                "input_tokens": attempt.input_tokens,
                "output_tokens": attempt.output_tokens,
                "cached": attempt.cached,
                "error": attempt.error,
            }) + "\n")
            written += 1
            mark = "!" if attempt.error else " "
            klass = label.form_class.value if label else "PARSE FAIL"
            print(f"  {i:3d}/{len(rows)} {mark} {row['page_id']:16s} {klass}")

    print(f"\nwrote {written} rows to {OUT}")
    print(f"spent this run: ${spend:.2f} standard")


if __name__ == "__main__":
    main()
