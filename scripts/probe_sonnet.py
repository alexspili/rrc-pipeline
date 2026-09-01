#!/usr/bin/env python3
"""Measure what one completion document costs to extract.

Same posture as scripts/probe_haiku.py: measure before a corpus run, and never
put an assumed number in prose (CLAUDE.md rule 8). Input tokens are counted
with the count_tokens endpoint, which costs nothing, at both candidate image
sizes. One real call then measures output tokens, which counting cannot.

The document is record 1493495 pages 9 and 10: a W-2 face and its Section II,
the worked example for two-phase reassembly. Between them they carry every v1
field, which is the point of choosing it.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                       # noqa: E402

MODEL = "claude-sonnet-5"
PRICE_IN = 2.00     # $/1M input tokens, claude-sonnet-5
PRICE_OUT = 10.00   # $/1M output tokens
BATCH_DISCOUNT = 0.5

RECORD, PAGES = "1493495", (9, 10)

SYSTEM = """\
You extract structured data from scanned Texas Railroad Commission oil and gas
completion reports, Form G-1 and Form W-2, imaged from paper filed between the
1950s and 2008.

You are given every page of one completion report. Return one JSON object.

Every extracted value is an object, never a bare scalar:

  {"value": <normalised>, "raw": <exactly as written>, "status": <see below>,
   "page": <1-based index of the page you read it from>,
   "box": [x0, y0, x1, y1], "correction": null}

status is one of:
  present            a value is written and you read it
  blank              the field exists on this form and is empty
  illegible          something is written and you cannot read it
  not_on_this_form   this form revision has no such field

The distinction matters. A 1975 Form W-2 has no API number field at all, which
is not_on_this_form, not blank. Never guess between them.

box locates the value on the page as fractions of page width and height, from
0 to 1, as [left, top, right, bottom]. It is a region locator for a human
reviewer, not a precise measurement. Give the smallest box that contains the
written value and its field label.

correction is for a value struck through and replaced by hand, which is common
on these forms. When you see one, put the struck-through original in
correction as {"raw": ..., "box": [...]} and the replacement in value and raw.
Otherwise null.

Fields to return:

identity: field_name, lease_name, well_number, operator_name, operator_address,
county, rrc_district, location_survey, distance_to_town, api_number,
rrc_well_id, purpose_of_filing, completion_date, pipeline_connection, logs_run

completion: type_of_completion, date_permit_issued, drilling_commenced,
drilling_completed, total_depth, plug_back_depth, top_of_pay, elevation,
directional_survey, drilling_contractor, casing_strings, liner_strings, tubing,
producing_intervals, treatments, formation_tops

test: date_of_test only

casing_strings, liner_strings, producing_intervals, treatments and
formation_tops are arrays of row objects, each field of each row in the value
shape above. tubing is one object.

Also return document: {"form_class": "g1" or "w2", "form_revision": <the Rev.
date printed by the form number, as a value object>}.

Return only the JSON object.
"""


def content_blocks(cap: int) -> list[dict]:
    manifest = {json.loads(l)["record_id"]: json.loads(l)
                for l in (ROOT / "data" / "manifest.jsonl").open()}
    pdf = (ROOT / "data" / "raw" / RECORD
           / manifest[RECORD]["files"][0]["name"])
    blocks = []
    for order, page in enumerate(PAGES, 1):
        png, sent = render.render_page_png(pdf, page, cap=cap)
        blocks.append({"type": "text", "text": f"Page {order} of {len(PAGES)}:"})
        blocks.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(png).decode()}})
        print(f"    page {page} rendered at {sent[0]}x{sent[1]}, "
              f"{len(png) / 1024:.0f} KB")
    blocks.append({"type": "text",
                   "text": "Extract this completion report."})
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cap", type=int, default=1568)
    ap.add_argument("--count-only", action="store_true",
                    help="count input tokens and stop; costs nothing")
    args = ap.parse_args()

    import anthropic
    client = anthropic.Anthropic()

    print(f"model {MODEL}, ${PRICE_IN}/${PRICE_OUT} per 1M\n")

    counts = {}
    for cap in (1000, 1568):
        print(f"  cap {cap}px:")
        blocks = content_blocks(cap)
        counted = client.messages.count_tokens(
            model=MODEL, system=SYSTEM,
            messages=[{"role": "user", "content": blocks}])
        counts[cap] = counted.input_tokens
        print(f"    counted input tokens: {counted.input_tokens:,}\n")

    if args.count_only:
        return

    print(f"  one real call at cap {args.cap}...")
    response = client.messages.create(
        model=MODEL, max_tokens=8000, system=SYSTEM,
        messages=[{"role": "user", "content": content_blocks(args.cap)}])
    usage = response.usage
    body = "".join(b.text for b in response.content if b.type == "text")

    out = ROOT / "data" / "probe_sonnet_extraction.json"
    out.write_text(body)

    cost = (usage.input_tokens * PRICE_IN
            + usage.output_tokens * PRICE_OUT) / 1e6
    print(f"\n  input  {usage.input_tokens:,} tokens")
    print(f"  output {usage.output_tokens:,} tokens")
    print(f"  stop_reason: {response.stop_reason}")
    print(f"\n  this document: ${cost:.4f} standard, "
          f"${cost * BATCH_DISCOUNT:.4f} batched")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
