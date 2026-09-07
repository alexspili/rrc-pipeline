#!/usr/bin/env python3
"""Model calls for extraction. The prompt lives here; the schema lives in
pipeline/extract.py and the parsing with it.

Same split as the classifier: `pageclass` is pure domain and `classify` talks
to the API. Costs are measured, never assumed (DEFECTS #21).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from pipeline import classify
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
#: surfaced as "malformed JSON" rather than as what it was.
#:
#: Re-measured 2026-09-05 over the 20 documents of the finished smoke run,
#: because the figure written here when the cap was raised ("about 5,100
#: output tokens") was taken before the run completed and is not what the run
#: produced. Split by page count, since the two differ a lot:
#:
#:   1-page documents  n=13   mean 5,851 output tokens   worst  9,706
#:   2-page documents  n= 7   mean 8,480 output tokens   worst 13,122
#:
#: 16000 sat 1.22x above the worst of those 20, which is thin, and the reason
#: it is thin is not document size. **About three quarters of what we are
#: billed for as output is not in the response.** claude-sonnet-5 runs adaptive
#: thinking whenever no `thinking` parameter is passed, and thinking tokens are
#: billed and counted against this cap while never appearing in the text
#: blocks. The worst document in the smoke run returned 5,607 characters of
#: JSON, roughly 1,600 tokens, and was billed 13,122.
#:
#: That changes what this number guards. The cap is not bounding how much
#: document there is to describe; it is bounding how long the model chooses to
#: think, which does not scale with anything we can see in advance. So the
#: headroom has to be generous rather than snug.
#:
#: 32000 is 2.4x the worst observed. It costs nothing until it is used, since
#: billing is on tokens produced and not on the ceiling, and claude-sonnet-5
#: accepts up to 128,000. `scripts/estimate_batch.py` prints the ratio against
#: the measured worst case on every run so this cannot go stale again.
MAX_TOKENS = 32000

SYSTEM = """\
You extract structured data from scanned Texas Railroad Commission oil and gas
completion reports, Form G-1 and Form W-2, imaged from paper filed between the
1950s and 2008.

You are given every page of one completion report. Return one JSON object.

Every extracted value is an object, never a bare scalar:

  {"value": <normalised>, "raw": <exactly as written>, "status": <see below>,
   "page": <1-based index of the page you read it from>,
   "box": [x0, y0, x1, y1], "found_in": <printed label of the box>,
   "correction": null}

status is one of:
  present               a value is written and you read it
  blank                 the field exists on this form and is empty
  illegible             something is written and you cannot read it
  not_on_this_form      this form revision has no such field
  page_not_in_document  the form has this field, on a page you were not given

The distinctions matter and you must not collapse them.

not_on_this_form is a fact about the form family and revision: it does not
print this field anywhere. page_not_in_document is a fact about this document:
the family prints the field, on a page you were not given. "This form" always
means the form family, never the page in front of you, so a W-2 Section II
separated from its face has page_not_in_document for the lease name, because
Form W-2 prints one even though Section II does not.

A 1975 Form W-2 has no API number field anywhere on it. That is
not_on_this_form, not blank.

A Form W-2 face says "if well is newly completed or recompleted, fill in
reverse side also", and the completion and casing data lives on that reverse.
If you were not given the reverse, every field that lives on it is
page_not_in_document. It is not blank, because nobody left it empty, and it is
not not_on_this_form, because the form has it. Most documents in this archive
were imaged front only.

box locates the value on the page as fractions of page width and height, from
0 to 1, as [left, top, right, bottom]. It is a region locator for a human
reviewer, not a precise measurement. Give the smallest box that contains the
written value and its field label. Set box to null, not to zeros, whenever
status is anything other than present.

found_in is the PRINTED LABEL of the box you took the value from, copied as it
appears on the page, with its field number if the form prints one. For example
"26. Notice of Intention to Drill this Well was filed in Name of", or "32.
Location of Well, Relative to Lease Boundaries", or "14. Completion Date". Give
it whenever status is present, and null otherwise. If you took a value from a
box whose label you cannot fully read, put what you can read.

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


def recorded_prompt_hash(results: Path) -> str:
    """The prompt hash a finished run recorded, else the current prompt's.

    The result cache is keyed on (document, prompt), so reading a finished run
    back with today's hash looks under a key nothing was written to the moment
    the prompt moves on (DEFECTS #28). Three scripts were each carrying their
    own copy of this; one copy, here, next to the hash it falls back to.
    """
    if results.exists():
        for line in results.open():
            if line.strip():
                recorded = json.loads(line).get("prompt_hash")
                if recorded:
                    return recorded
    return PROMPT_HASH


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


def cache_key(cache, pdf: Path, pages, doc_hash: str | None = None) -> str:
    """The one place the extraction cache key is spelled.

    It was spelled inline in `extract_document` and nowhere else, which was
    fine while there was one caller. The batch path is a second caller and a
    second spelling would be a cache that silently misses.
    """
    pages = tuple(pages)
    return cache.key(doc_hash or render.doc_hash(pdf), pages[0],
                     f"extract-{'-'.join(map(str, pages))}")


def payload_of(message) -> dict:
    """A model response reduced to what the cache stores.

    `stop_reason` is part of it because a truncation has to stay recognisable
    after it has been written down. See `_extraction`.
    """
    body = "".join(b.text for b in message.content if b.type == "text")
    return {"body": body,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "stop_reason": message.stop_reason}


def _extraction(payload: dict, *, record_id: str, file_index: int,
                pages: tuple[int, ...], cached: bool,
                cache=None, key=None) -> Extraction:
    """One parse and one guard, shared by every path that has a payload.

    Three paths now have one: a cache hit, a live call and a batch result.
    DEFECTS #14's lesson is that a cache which changes the answer is worse
    than no cache, and the only way to keep that true with three paths is for
    them to converge here before anything is decided.

    **The truncation guard runs before the cache is consulted, not after.**
    That is DEFECTS #47. A response cut off at max_tokens arrives as malformed
    JSON and reports itself as malformed JSON, which is why the guard exists
    at all. It also refuses to store the fragment, because the cache key does
    not include max_tokens and a stored truncation would outlive every raise
    of the cap. Both halves apply to a fragment that was stored before the
    guard existed, and there are four of those on disk.
    """
    tokens = {"input_tokens": payload["input_tokens"],
              "output_tokens": payload["output_tokens"]}

    if payload.get("stop_reason") == "max_tokens":
        return Extraction(
            report=None, record_id=record_id, pages=pages, **tokens,
            cached=cached,
            error=f"truncated at max_tokens ({MAX_TOKENS}); "
                  f"{payload['output_tokens']} output tokens")

    if not cached and cache is not None and key is not None:
        cache.put(key, payload)

    try:
        report = ex.parse_report(payload["body"], record_id=record_id,
                                 file_index=file_index, pages=pages)
        error = None
    except ValueError as exc:
        report, error = None, str(exc)
    return Extraction(report=report, record_id=record_id, pages=pages,
                      **tokens, cached=cached, error=error)


def extract_document(api, pdf: Path, pages, *, record_id: str,
                     file_index: int, cache=None,
                     doc_hash: str | None = None) -> Extraction:
    """One document, one call."""
    pages = tuple(pages)

    key = None
    if cache is not None:
        key = cache_key(cache, pdf, pages, doc_hash)
        hit = cache.get(key)
        if hit is not None:
            return _extraction(hit, record_id=record_id,
                               file_index=file_index, pages=pages, cached=True)

    # Streamed, and the reason is the cap above rather than any wish to show
    # progress. A response allowed to run to 32,000 tokens can outlast the
    # SDK's request timeout on a plain create(); the documented remedy is to
    # stream and take the final message. The batch path needs none of this,
    # because a batch is asynchronous by construction.
    with api.messages.stream(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
            messages=[{"role": "user",
                       "content": build_content(pdf, pages)}]) as stream:
        response = stream.get_final_message()
    return _extraction(payload_of(response), record_id=record_id,
                       file_index=file_index, pages=pages, cached=False,
                       cache=cache, key=key)


# ------------------------------------------------------------------ batch path

#: Anthropic documents 256 MB and 100,000 requests per batch. The classifier
#: holds both well clear for a one-page vision request; an extraction request
#: carries every page of a document at 1568 px, so it is several times larger
#: and the byte ceiling is the one that binds. Measured on this corpus rather
#: than assumed: scripts/estimate_batch.py reports the real serialised size.
BATCH_MAX_BYTES = classify.BATCH_MAX_BYTES
BATCH_MAX_REQUESTS = 1_000

#: How long to wait between polls of a submitted batch. Anthropic's stated
#: ceiling is 24 hours and most batches finish inside one.
BATCH_POLL_SECONDS = 30


def build_request(pdf: Path, pages, *, custom_id: str) -> dict:
    """One document as a batch request.

    Same model, same cap and the same SYSTEM constant as the live call, which
    is the point: DEFECTS #45 is what happens when two code paths build two
    prompts and only one of them gets measured.
    """
    return {"custom_id": custom_id,
            "params": {"model": MODEL, "max_tokens": MAX_TOKENS,
                       "system": SYSTEM,
                       "messages": [{"role": "user",
                                     "content": build_content(pdf, pages)}]}}


def run_batched(api, documents, *, cache=None, doc_hashes: dict | None = None,
                on_progress=None, max_bytes: int = BATCH_MAX_BYTES,
                max_requests: int = BATCH_MAX_REQUESTS) -> dict:
    """Extract many documents through the Batch API. Returns {custom_id: Extraction}.

    Half the price of the live path and that is the whole reason it exists.

    `documents` is a sequence of dicts with custom_id, record_id, file_index,
    pdf and pages. The custom_id names the document and is what results come
    back keyed by; nothing here may rely on the order they arrive in, because
    the API does not promise one. A document missing from the results comes
    back as an Extraction carrying an error rather than vanishing, which is
    standing rule 9 applied to a run of 238 documents: a hole nobody counts is
    a hole nobody can argue with.

    Cached documents never become requests (CLAUDE.md rule 7).
    """
    import time

    out: dict[str, Extraction] = {}
    requests: list[dict] = []
    meta: dict[str, dict] = {}

    for doc in documents:
        custom_id = doc["custom_id"]
        if custom_id in meta:
            raise ValueError(
                f"two documents share the custom_id {custom_id!r}; results "
                "come back keyed by it and one would overwrite the other")
        pages = tuple(doc["pages"])
        meta[custom_id] = {"record_id": doc["record_id"],
                           "file_index": doc["file_index"],
                           "pages": pages, "pdf": doc["pdf"], "key": None}

        if cache is not None:
            hashes = doc_hashes or {}
            key = cache_key(cache, doc["pdf"], pages, hashes.get(doc["pdf"]))
            meta[custom_id]["key"] = key
            hit = cache.get(key)
            if hit is not None:
                out[custom_id] = _extraction(
                    hit, record_id=doc["record_id"],
                    file_index=doc["file_index"], pages=pages, cached=True)
                continue
        requests.append(build_request(doc["pdf"], pages, custom_id=custom_id))

    if not requests:
        return out

    chunks = classify.chunk_requests(requests, max_bytes=max_bytes,
                                     max_requests=max_requests)
    for n, chunk in enumerate(chunks, 1):
        batch = api.messages.batches.create(requests=chunk)
        if on_progress:
            on_progress(f"batch {n}/{len(chunks)} submitted as {batch.id}, "
                        f"{len(chunk)} documents")
        while getattr(batch, "processing_status", "ended") != "ended":
            time.sleep(BATCH_POLL_SECONDS)
            batch = api.messages.batches.retrieve(batch.id)

        seen = set()
        for entry in api.messages.batches.results(batch.id):
            custom_id = entry.custom_id
            seen.add(custom_id)
            info = meta[custom_id]
            if entry.result.type != "succeeded":
                # The API says why in the result's error object; dropping it
                # turned a dated usage cap into ten identical unknowns
                # (DEFECTS #72).
                detail = getattr(entry.result, "error", None)
                message = getattr(getattr(detail, "error", None),
                                  "message", None) or (
                    str(detail) if detail else "")
                out[custom_id] = Extraction(
                    report=None, record_id=info["record_id"],
                    pages=info["pages"], input_tokens=0, output_tokens=0,
                    cached=False,
                    error=f"batch result {entry.result.type}"
                          + (f": {message}" if message else ""))
                continue
            out[custom_id] = _extraction(
                payload_of(entry.result.message),
                record_id=info["record_id"], file_index=info["file_index"],
                pages=info["pages"], cached=False,
                cache=cache, key=info["key"])

        for request in chunk:
            custom_id = request["custom_id"]
            if custom_id in seen:
                continue
            info = meta[custom_id]
            out[custom_id] = Extraction(
                report=None, record_id=info["record_id"],
                pages=info["pages"], input_tokens=0, output_tokens=0,
                cached=False,
                error="no result returned for this document in the batch")

    return out
