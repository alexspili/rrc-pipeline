#!/usr/bin/env python3
"""Model calls for extraction. The prompt lives here; the schema lives in
pipeline/extract.py and the parsing with it.

Same split as the classifier: `pageclass` is pure domain and `classify` talks
to the API. Costs are measured, never assumed (DEFECTS #21).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from pipeline import extract as ex
from pipeline import pageclass as pc
from pipeline import render

MODEL = "claude-sonnet-5"

#: $ per 1M tokens, claude-sonnet-5. Not claude-sonnet-4-6's $3/$15, which is
#: the mistake DEFECTS #21 records.
PRICE_IN = 2.00
PRICE_OUT = 10.00
BATCH_DISCOUNT = 0.5

#: Long edge for the page images.
#:
#: 1568 rather than the classifier's 1000, and the reason is measured: output
#: tokens are 85% of the cost, so the larger image adds about $0.006 per
#: document. Extraction reads handwriting, struck-through corrections and
#: small figures off degraded microfilm. See docs/modules/extract.md.
IMAGE_CAP = 1568

#: 8000 truncated 4 of the first 14 smoke documents mid-string, and each one
#: surfaced as "malformed JSON" rather than as what it was. Completed
#: documents average about 5,100 output tokens, so the old cap was roughly
#: 1.6x the mean and not far enough above the tail.
MAX_TOKENS = 16000

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
written value and its field label. Set box to null, not to zeros, whenever
status is anything other than present.

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
directional_survey, drilling_contractor, casing_strings, liner_strings,
tubing, producing_intervals, treatments, formation_tops

test: date_of_test only. Return nothing else from the test sections.

casing_strings, liner_strings, tubing, producing_intervals, treatments and
formation_tops are arrays of row objects, each field of each row in the value
shape above.

page is the index of the page WITHIN THIS DOCUMENT, counting the pages shown
to you from 1. The first page shown is page 1, whatever it is called in the
file.

An array field with nothing in it is an empty array, []. Never return a value
object in place of a table.

Also return document, whose form_class is a bare string and whose
form_revision is a value object:

  "document": {"form_class": "w2",
               "form_revision": {"value": ..., "raw": "Rev. 6/30/75", ...}}

Return only the JSON object.
"""

PROMPT_HASH = pc.prompt_hash(SYSTEM)


@dataclass(frozen=True)
class Extraction:
    """One document's worth of extraction, with what it cost."""

    report: ex.CompletionReport | None
    record_id: str
    pages: tuple[int, ...]
    input_tokens: int
    output_tokens: int
    cached: bool
    error: str | None = None

    def cost_usd(self, batched: bool = False) -> float:
        rate = BATCH_DISCOUNT if batched else 1.0
        return rate * (self.input_tokens * PRICE_IN
                       + self.output_tokens * PRICE_OUT) / 1e6


def client():
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set; load .env first "
            "(set -a; . ./.env; set +a)")
    return anthropic.Anthropic()


def build_content(pdf: Path, pages, cap: int = IMAGE_CAP) -> list[dict]:
    """Every page of one document, in order, each announced by its index.

    The index is what the model puts in each value's `page` field, so it has
    to be the position within the document rather than within the file.
    """
    blocks: list[dict] = []
    for order, page in enumerate(pages, 1):
        png, _ = render.render_page_png(pdf, page, cap=cap)
        blocks.append({"type": "text",
                       "text": f"Page {order} of {len(pages)}:"})
        blocks.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(png).decode()}})
    blocks.append({"type": "text", "text": "Extract this completion report."})
    return blocks


def extract_document(api, pdf: Path, pages, *, record_id: str,
                     file_index: int, cache=None,
                     doc_hash: str | None = None) -> Extraction:
    """One document, one call.

    One parse and one guard shared by the cached and fresh paths, which is
    DEFECTS #14's lesson: a cache that changes the answer is worse than no
    cache.
    """
    pages = tuple(pages)

    def build(payload: dict, cached: bool) -> Extraction:
        try:
            report = ex.parse_report(
                payload["body"], record_id=record_id, file_index=file_index,
                pages=pages)
            error = None
        except ValueError as exc:
            report, error = None, str(exc)
        return Extraction(
            report=report, record_id=record_id, pages=pages,
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            cached=cached, error=error)

    key = None
    if cache is not None:
        key = cache.key(doc_hash or render.doc_hash(pdf),
                        pages[0], f"extract-{'-'.join(map(str, pages))}")
        hit = cache.get(key)
        if hit is not None:
            return build(hit, cached=True)

    response = api.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
        messages=[{"role": "user",
                   "content": build_content(pdf, pages)}])
    body = "".join(b.text for b in response.content if b.type == "text")
    payload = {"body": body,
               "input_tokens": response.usage.input_tokens,
               "output_tokens": response.usage.output_tokens,
               "stop_reason": response.stop_reason}

    # A truncated response is a truncation, not malformed JSON, and it must
    # never be cached: the cache key does not include max_tokens, so a stored
    # truncation would be served back forever with the cap already raised.
    if response.stop_reason == "max_tokens":
        return Extraction(
            report=None, record_id=record_id, pages=pages,
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"], cached=False,
            error=f"truncated at max_tokens ({MAX_TOKENS}); "
                  f"{payload['output_tokens']} output tokens")

    if cache is not None and key is not None:
        cache.put(key, payload)
    return build(payload, cached=False)
