#!/usr/bin/env python3
"""Measure what one identity read costs. Two or three pages, no more.

Approved 2026-09-03 to replace an estimated per-page cost with a measured
one. The full run over the ~274 candidate pages stays gated and lands with
the full extraction run as one spend decision.

Prints tokens and cost per page, and the projected corpus figure, so the
gated decision is made against a number rather than an estimate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import identity                      # noqa: E402
from pipeline import pageclass as pc               # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"

PRICE_IN, PRICE_OUT = 2.0, 10.0                    # claude-sonnet-5, per 1M


def candidates():
    out = []
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        cls, part = row.get("form_class"), row.get("part")
        if cls == "other_form" or (cls in ("w2", "g1")
                                   and part in ("continuation", "sec_ii",
                                                "sec_iii")):
            out.append(pc.parse_page_id(row["page_id"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args()
    if args.pages > 3:
        sys.exit("this probe is capped at 3 pages; the full run is gated")

    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    pool = candidates()
    print(f"{len(pool)} candidate pages in the corpus; probing {args.pages}\n")

    import anthropic
    client = anthropic.Anthropic()
    total_in = total_out = 0
    for record_id, file_index, page in pool[:args.pages]:
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        response = client.messages.create(
            model=identity.MODEL, max_tokens=identity.MAX_TOKENS,
            system=identity.SYSTEM,
            messages=[{"role": "user",
                       "content": identity.build_content(pdf, page)}])
        usage = response.usage
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        body = response.content[0].text
        try:
            values = identity.parse(body, page)
            read = identity.identity_for(values)
            present = {k: v for k, v in read.items() if v}
        except Exception as exc:                   # noqa: BLE001
            present = f"parse failed: {exc}"
        cost = (usage.input_tokens * PRICE_IN
                + usage.output_tokens * PRICE_OUT) / 1e6
        print(f"  {record_id}-{file_index}-{page}: "
              f"in {usage.input_tokens:,} out {usage.output_tokens:,} "
              f"${cost:.4f}  stop={response.stop_reason}")
        print(f"     {present}")

    per_page = (total_in * PRICE_IN + total_out * PRICE_OUT) / 1e6 / args.pages
    print(f"\n  measured: {total_in // args.pages:,} in, "
          f"{total_out // args.pages:,} out per page")
    print(f"  ${per_page:.4f} per page standard, "
          f"${per_page / 2:.4f} batched")
    print(f"\n  projected over {len(pool)} candidate pages: "
          f"${per_page * len(pool):.2f} standard, "
          f"${per_page * len(pool) / 2:.2f} batched")
    print("  that run is GATED and lands with the full extraction run")


if __name__ == "__main__":
    main()
