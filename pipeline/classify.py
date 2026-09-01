#!/usr/bin/env python3
"""Classify one page of a fetched RRC file with Haiku.

Three arms compete before the corpus run: the page image at a 1000px long
edge, the same at 1568px, and the embedded OCR text layer. The arm is a
parameter rather than a decision baked into the code, because which one wins
is a measurement and not an opinion. docs/modules/classify.md records the
selection rule, written before any arm was run.

Structured outputs are NOT used yet. `output_config.format` has not been
observed working on this model from this account, and CLAUDE.md rule 2 says an
unobserved parameter value gets a bounded test before it reaches a corpus run.
That rule came from Neubus (DEFECTS #3) and applies just as well to our own
vendor. scripts/probe_haiku.py is the bounded test; until it passes, responses
are parsed as plain JSON, which pageclass.parse_response already does strictly.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from pipeline import formscan
from pipeline import pageclass as pc
from pipeline import render

MODEL = "claude-haiku-4-5"

# Anthropic list prices, USD per million tokens. Batch API halves both.
PRICE_IN, PRICE_OUT = 1.00, 5.00
BATCH_DISCOUNT = 0.5

ARMS = {
    "vision_1000": {"kind": "image", "cap": 1000},
    "vision_1568": {"kind": "image", "cap": 1568},
    "text": {"kind": "text", "cap": None},
}

MAX_TOKENS = 256          # the response is one small JSON object


def _vocabulary() -> str:
    """The class list with one line of gloss each.

    A bare token like `l1` or `gt1` tells the model nothing about what to look
    for. Naming the form costs a few hundred tokens on a prompt that is nowhere
    near any cache threshold anyway.
    """
    lines = []
    for title, classes in (
        ("completion reports, the extraction targets", pc.COMPLETION_FACES),
        ("other RRC forms that carry well identity", pc.IDENTITY_BEARING),
        ("everything else", pc.CENSUS_ONLY),
    ):
        lines.append(f"{title}:")
        for cls in sorted(classes, key=lambda c: c.value):
            lines.append(f"  {cls.value:<18} {pc.GLOSS[cls]}")
    return "\n".join(lines)


SYSTEM = f"""\
You classify single pages from scanned Texas Railroad Commission well records.
The files are imaged paper from the 1950s onward: typed and handwritten forms,
correspondence, plats, and cards, in no particular order within a file.

Return one JSON object and nothing else:

  {{"form_class": ..., "part": ..., "orientation": ...,
    "confidence": ..., "alt_class": ..., "form_number_legible": ...}}

form_class is one of:
{_vocabulary()}

part is a SEPARATE field from form_class. Never put a part value such as
back_instructions into form_class. Use null for anything that is not a form.
  face               the first page, carrying the form number and identity
  sec_ii             Section II
  sec_iii            Section III
  continuation       a later page of the same form, including a reverse that
                     carries a filled-in data table
  back_instructions  a reverse carrying pre-printed filing instructions and no
                     filled-in values. Real backs announce themselves: "Side
                     2", "Instructions Form G-5", "Continued from reverse
                     side". Beware: "READ INSTRUCTIONS ON BACK", "- OVER -"
                     and "REVERSE SIDE HEREOF" are printed on the FACE, so a
                     page carrying one of those is a face.
  unknown            plainly part of a form, but which page is not decidable

If a page is plainly a form but you cannot tell which one, use
form_class: other_form. If it is plainly a form BACK whose form you cannot
name, that is form_class: other_form with part: back_instructions.

Sections of a form are often not adjacent in the file. A Section III can sit
several pages away from its face with unrelated forms in between. Judge the
page in front of you; do not infer from where it sits.

orientation is how the page is rotated relative to upright text: up, cw90,
ccw90, or down. Report it, do not correct for it.

confidence is high, medium or low. Say low when the page is too degraded,
too generic, or too unfamiliar to place. Low is useful; a wrong high is not.

alt_class is your second choice, or null if nothing else is plausible.

form_number_legible is true or false: can you actually read a printed form
number on this page, whatever it says. Not whether you can guess the form from
its layout. A number you can see is there but cannot make out is false.

THE COMPLETION REPORT RULE. G-1 and W-2 are near-identical in layout and differ
in their printed number. So you may answer g1 or w2 ONLY when
form_number_legible is true and the number you read is that one. On a page that
is plainly the face of a completion report but whose number you cannot read,
answer completion_face_unknown_form, with form_number_legible false. Do not
guess between G-1 and W-2 from the layout; the layout does not carry the
answer, and a guess here was wrong every single time it was measured.

Some completion reports predate the numbering and are printed "Form 2",
"Form 3" or "GWT-1". Those are completion_face_legacy, with
form_number_legible true.

Both of those classes are faces: part is always face for them. A later page or
a printed back of such a form is other_form.

If the page is a form you cannot identify, use other_form. If it is not a form
at all, use other_nonform. Do not force a page into a class it does not fit.
"""

PROMPT_HASH = pc.prompt_hash(SYSTEM)


@dataclass(frozen=True)
class Attempt:
    """One classification, plus what it cost and where it came from."""
    label: pc.PageLabel | None
    arm: str
    sent_px: tuple[int, int] | None
    input_tokens: int
    output_tokens: int
    cached: bool
    error: str | None = None

    def cost_usd(self, batched: bool = False) -> float:
        rate = BATCH_DISCOUNT if batched else 1.0
        return rate * (self.input_tokens * PRICE_IN
                       + self.output_tokens * PRICE_OUT) / 1e6


# ---------------------------------------------------------------- request body

def build_content(arm: str, pdf: Path, page: int) -> tuple[list[dict], tuple[int, int] | None]:
    """The user content blocks for one page, and the pixel size actually sent.

    Raises render.PageNotSingleImage for a page that is not one embedded
    image. None exist in the closed corpus; if that changes the run should say
    so rather than quietly rasterising something different.
    """
    spec = ARMS[arm]
    if spec["kind"] == "text":
        text = render.page_text(pdf, page)
        if not text.strip():
            text = "(this page has no embedded text layer)"
        return ([{"type": "text",
                  "text": f"Classify this page.\n\n<page_text>\n{text}\n</page_text>"}],
                None)

    png, sent = render.render_page_png(pdf, page, cap=spec["cap"])
    return ([{"type": "image",
              "source": {"type": "base64", "media_type": "image/png",
                         "data": base64.standard_b64encode(png).decode()}},
             {"type": "text", "text": "Classify this page."}],
            sent)


# ----------------------------------------------------------------- result cache

class ResultCache:
    """CLAUDE.md rule 7: never re-infer an unchanged (document, prompt) pair.

    Our own cache, keyed on the file's content hash plus the page, arm and
    prompt hash. Not Anthropic prompt caching, which will not engage on a
    prompt this short.
    """

    def __init__(self, path: Path):
        self.path = path
        self._entries: dict[str, dict] = {}
        if path.exists():
            for line in path.open():
                if line.strip():
                    entry = json.loads(line)
                    self._entries[entry["key"]] = entry

    @staticmethod
    def key(doc_hash: str, page: int, arm: str) -> str:
        return pc.cache_key(f"{doc_hash}-{page}-{arm}", PROMPT_HASH)

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, key: str, payload: dict) -> None:
        entry = {"key": key, **payload}
        self._entries[key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")


# ------------------------------------------------------------------ model call

def client():
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. It belongs in .env alongside "
            "NEUBUS_TOKEN (CLAUDE.md, Environment). Load it with:\n"
            "  set -a; . ./.env; set +a")
    return anthropic.Anthropic()


def classify_page(api, arm: str, pdf: Path, page: int, *,
                  record_id: str, file_index: int,
                  cache: ResultCache | None = None,
                  doc_hash: str | None = None) -> Attempt:
    dims = render.page_dimensions(pdf)
    width, height = dims[page - 1]
    oversize = pc.is_oversize(width, height) if width and height else False

    cached_tokens: set[str] | None = None

    def header_tokens() -> set[str]:
        """The form numbers printed on this page, read from the text layer.

        Computed at most once per call and only when a label was parsed, so a
        page that never reaches reconciliation costs no pdftotext.
        """
        nonlocal cached_tokens
        if cached_tokens is None:
            cached_tokens = set(formscan.header_tokens(
                render.page_text(pdf, page)))
        return cached_tokens

    def build(payload: dict, cached: bool) -> Attempt:
        """One parse and one guard, shared by the cached and live paths.

        DEFECTS #14: these were two call sites, and only the live one caught a
        parse failure, so a run that tolerated bad pages on the way out died on
        the first one on the way back. The header reconciliation added for
        DEFECTS #19 lives here for the same reason: a correction that runs on
        fresh results and not on cached ones makes the cache change the answer.
        """
        try:
            label = pc.parse_response(
                payload["body"], record_id=record_id, file_index=file_index,
                page=page, oversize=oversize)
            label = pc.reconcile_with_header(label, header_tokens())
            error = None
        except ValueError as exc:
            label, error = None, str(exc)
        sent = payload.get("sent_px")
        return Attempt(
            label=label, arm=arm, sent_px=tuple(sent) if sent else None,
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            cached=cached, error=error)

    key = None
    if cache is not None:
        key = cache.key(doc_hash or render.doc_hash(pdf), page, arm)
        hit = cache.get(key)
        if hit is not None:
            return build(hit, cached=True)

    content, sent = build_content(arm, pdf, page)
    response = api.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
        messages=[{"role": "user", "content": content}])
    body = "".join(b.text for b in response.content if b.type == "text")

    payload = {"body": body, "sent_px": list(sent) if sent else None,
               "input_tokens": response.usage.input_tokens,
               "output_tokens": response.usage.output_tokens}
    if cache is not None and key is not None:
        cache.put(key, payload)

    return build(payload, cached=False)


# ------------------------------------------------------------------ batch path

#: Anthropic documents 256 MB and 100,000 requests per batch. Both are held
#: well clear: one vision_1000 request serialises to ~331 KB, so the census at
#: 3,689 pages is 1.22 GB and needs chunking regardless.
BATCH_MAX_BYTES = 180_000_000
BATCH_MAX_REQUESTS = 5_000

#: How long to wait between polls of a submitted batch.
BATCH_POLL_SECONDS = 30


def chunk_requests(requests: list[dict], max_bytes: int = BATCH_MAX_BYTES,
                   max_requests: int = BATCH_MAX_REQUESTS) -> list[list[dict]]:
    """Split requests into batches under both ceilings.

    A single request larger than max_bytes goes out alone rather than being
    dropped: an over-limit batch fails loudly, a dropped page becomes a hole in
    the census that nothing counts.
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for request in requests:
        weight = len(json.dumps(request))
        too_big = current and (size + weight > max_bytes
                               or len(current) >= max_requests)
        if too_big:
            chunks.append(current)
            current, size = [], 0
        current.append(request)
        size += weight
    if current:
        chunks.append(current)
    return chunks


def build_request(arm: str, pdf: Path, page: int, page_id: str) -> dict:
    content, _ = build_content(arm, pdf, page)
    return {"custom_id": page_id,
            "params": {"model": MODEL, "max_tokens": MAX_TOKENS,
                       "system": SYSTEM,
                       "messages": [{"role": "user", "content": content}]}}


def run_batched(api, arm: str, pages, *, cache: ResultCache | None,
                doc_hashes: dict, on_progress=None) -> dict:
    """Classify many pages through the Batch API. Returns {page_id: Attempt}.

    Results come back keyed by custom_id in arbitrary order, so nothing here
    may rely on position. A page absent from the results comes back as an
    Attempt carrying an error rather than vanishing.

    Cached pages never become requests (CLAUDE.md rule 7), which is what makes
    a died-at-page-3000 census resumable for nothing.
    """
    import time

    attempts: dict[str, Attempt] = {}
    requests: list[dict] = []
    meta: dict[str, tuple] = {}

    for record_id, file_index, page, pdf in pages:
        page_id = pc.page_id(record_id, file_index, page)
        dims = render.page_dimensions(pdf)
        width, height = dims[page - 1]
        oversize = pc.is_oversize(width, height) if width and height else False
        meta[page_id] = (record_id, file_index, page, oversize)

        key = None
        if cache is not None:
            key = cache.key(doc_hashes[pdf], page, arm)
            hit = cache.get(key)
            if hit is not None:
                attempts[page_id] = _attempt_from(
                    hit, arm, record_id, file_index, page, oversize, cached=True)
                continue
        requests.append(build_request(arm, pdf, page, page_id))

    if not requests:
        return attempts

    chunks = chunk_requests(requests)
    for n, chunk in enumerate(chunks, 1):
        batch = api.messages.batches.create(requests=chunk)
        if on_progress:
            on_progress(f"batch {n}/{len(chunks)} submitted as {batch.id}, "
                        f"{len(chunk)} pages")
        while getattr(batch, "processing_status", "ended") != "ended":
            time.sleep(BATCH_POLL_SECONDS)
            batch = api.messages.batches.retrieve(batch.id)

        seen = set()
        for entry in api.messages.batches.results(batch.id):
            page_id = entry.custom_id
            seen.add(page_id)
            record_id, file_index, page, oversize = meta[page_id]
            if entry.result.type != "succeeded":
                attempts[page_id] = Attempt(
                    label=None, arm=arm, sent_px=None, input_tokens=0,
                    output_tokens=0, cached=False,
                    error=f"batch result {entry.result.type}")
                continue
            message = entry.result.message
            body = "".join(b.text for b in message.content if b.type == "text")
            payload = {"body": body, "sent_px": None,
                       "input_tokens": message.usage.input_tokens,
                       "output_tokens": message.usage.output_tokens}
            if cache is not None:
                cache.put(cache.key(doc_hashes[_pdf_of(pages, page_id)],
                                    page, arm), payload)
            attempts[page_id] = _attempt_from(
                payload, arm, record_id, file_index, page, oversize,
                cached=False)

        for request in chunk:
            page_id = request["custom_id"]
            if page_id in seen:
                continue
            attempts[page_id] = Attempt(
                label=None, arm=arm, sent_px=None, input_tokens=0,
                output_tokens=0, cached=False,
                error="no result returned for this page in the batch")

    return attempts


def _pdf_of(pages, page_id: str) -> Path:
    record_id, file_index, page = pc.parse_page_id(page_id)
    for r, f, p, pdf in pages:
        if (r, f, p) == (record_id, file_index, page):
            return pdf
    raise KeyError(page_id)


def _attempt_from(payload: dict, arm: str, record_id: str, file_index: int,
                  page: int, oversize: bool, *, cached: bool) -> Attempt:
    """Same parse and guard the single-page path uses (DEFECTS #14)."""
    try:
        label = pc.parse_response(payload["body"], record_id=record_id,
                                  file_index=file_index, page=page,
                                  oversize=oversize)
        error = None
    except ValueError as exc:
        label, error = None, str(exc)
    sent = payload.get("sent_px")
    return Attempt(label=label, arm=arm,
                   sent_px=tuple(sent) if sent else None,
                   input_tokens=payload["input_tokens"],
                   output_tokens=payload["output_tokens"],
                   cached=cached, error=error)
