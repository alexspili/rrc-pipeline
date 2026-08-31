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
        ("completion reports, the extraction targets", pc.EXTRACTION_TARGETS),
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
    "confidence": ..., "alt_class": ...}}

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

    def build(payload: dict, cached: bool) -> Attempt:
        """One parse and one guard, shared by the cached and live paths.

        DEFECTS #14: these were two call sites, and only the live one caught a
        parse failure, so a run that tolerated bad pages on the way out died on
        the first one on the way back.
        """
        try:
            label = pc.parse_response(
                payload["body"], record_id=record_id, file_index=file_index,
                page=page, oversize=oversize)
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
