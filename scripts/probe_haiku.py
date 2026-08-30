#!/usr/bin/env python3
"""Bounded probe: two API calls, one page, before any corpus run.

CLAUDE.md rule 2 says never send an external API a parameter value not
observed from a working client without a bounded test first. That rule came
from Neubus (DEFECTS #3, where strict:"false" silently disabled all filtering
while echoing the filters back). It applies to our own vendor too.

Two unknowns, answered here rather than assumed:

  1. Does `output_config.format` bind on claude-haiku-4-5 from this account?
     If it does, the classifier can stop parsing prose-wrapped JSON. If it
     does not, we keep the strict plain-JSON parser, which already works.
  2. What does a page image actually cost? pageclass.estimate_image_tokens is
     the published width*height/750 rule of thumb and is marked UNVERIFIED.
     count_tokens replaces it with a measured figure, because CLAUDE.md rule 8
     says numbers are measured or absent.

Costs about a tenth of a cent. Writes nothing; print the output into
docs/modules/classify.md under "Probe results".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify   # noqa: E402
from pipeline import pageclass as pc   # noqa: E402
from pipeline import render     # noqa: E402

# Record 1501720 page 2 is the G-1 face of the demo document: known ground
# truth, so a nonsense answer is visible immediately.
PDF = ROOT / "data" / "raw" / "1501720" / "Neubus0_17-1501720_3833992.pdf"
PAGE = 2

SCHEMA = {
    "type": "object",
    "properties": {
        "form_class": {"type": "string",
                       "enum": [c.value for c in pc.PageClass]},
        "part": {"type": ["string", "null"],
                 "enum": [p.value for p in pc.Part] + [None]},
        "orientation": {"type": "string",
                        "enum": [o.value for o in pc.Orientation]},
        "confidence": {"type": "string",
                       "enum": [c.value for c in pc.Confidence]},
        "alt_class": {"type": ["string", "null"],
                      "enum": [c.value for c in pc.PageClass] + [None]},
    },
    "required": ["form_class", "part", "orientation", "confidence", "alt_class"],
    "additionalProperties": False,
}


def main() -> None:
    render.preflight()
    if not PDF.exists():
        sys.exit(f"missing {PDF}; the corpus lives in data/raw (git-ignored)")

    api = classify.client()

    print("=" * 72)
    print("1. measured image tokens vs the w*h/750 estimate")
    print("=" * 72)
    for arm in ("vision_1000", "vision_1568"):
        content, sent = classify.build_content(arm, PDF, PAGE)
        counted = api.messages.count_tokens(
            model=classify.MODEL, system=classify.SYSTEM,
            messages=[{"role": "user", "content": content}])
        estimate = pc.estimate_image_tokens(*sent)
        total_pages = 3689
        print(f"  {arm}: sent {sent[0]}x{sent[1]}")
        print(f"    counted {counted.input_tokens:,} input tokens "
              f"(image estimate alone was {estimate:,})")
        cost = total_pages * counted.input_tokens * classify.PRICE_IN / 1e6
        print(f"    full corpus: {total_pages * counted.input_tokens:,} tokens, "
              f"${cost:,.2f} standard, ${cost / 2:,.2f} batched")

    content, sent = classify.build_content("text", PDF, PAGE)
    counted = api.messages.count_tokens(
        model=classify.MODEL, system=classify.SYSTEM,
        messages=[{"role": "user", "content": content}])
    print(f"  text: counted {counted.input_tokens:,} input tokens for this page")

    print()
    print("=" * 72)
    print("2. does output_config.format bind on this model?")
    print("=" * 72)
    content, _ = classify.build_content("vision_1568", PDF, PAGE)
    message = [{"role": "user", "content": content}]

    structured_ok, structured_body = False, ""
    try:
        response = api.messages.create(
            model=classify.MODEL, max_tokens=classify.MAX_TOKENS,
            system=classify.SYSTEM, messages=message,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        structured_body = "".join(
            b.text for b in response.content if b.type == "text")
        json.loads(structured_body)
        structured_ok = True
        print("  ACCEPTED. Response parsed as JSON without prose stripping.")
        print(f"    {structured_body}")
    except Exception as exc:                      # noqa: BLE001 - probe
        print(f"  REJECTED: {type(exc).__name__}: {str(exc)[:400]}")
        print("  Keep the plain-JSON parser. Do not wire structured outputs.")

    print()
    print("=" * 72)
    print("3. control: the plain path the classifier uses today")
    print("=" * 72)
    attempt = classify.classify_page(
        api, "vision_1568", PDF, PAGE, record_id="1501720", file_index=0)
    print(f"  label: {attempt.label}")
    print(f"  error: {attempt.error}")
    print(f"  tokens in/out: {attempt.input_tokens:,}/{attempt.output_tokens:,}"
          f"  cost ${attempt.cost_usd():.5f}")
    print()
    print("  Ground truth for this page: g1 / face / up.")
    print(f"  structured outputs usable: {structured_ok}")


if __name__ == "__main__":
    main()
