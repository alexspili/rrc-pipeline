#!/usr/bin/env python3
"""Textract word boxes as textlayer Words. Build-time only.

Parses a cached DetectDocumentText response into the same Word tuples
pipeline/textlayer.py produces from the embedded text layer, so everything
downstream of parsing (anchors, registration, labels) is source-blind. Pure:
dict in, Words out, no I/O and no boto3. The AWS call itself lives in
scripts/textract_read.py; nothing in pipeline/ may import boto3, which is
the one-API-key runtime property stage five preserves.

Textract returns BoundingBox Left/Top/Width/Height as fractions of the image
sent. The image sent is the page's embedded scan, and the scan fills the PDF
page box on this corpus (the assumption tests/tier2 pins for textlayer), so
these fractions and the embedded layer's live in one coordinate space. The
stage-five bounded probe verifies that empirically before anything else is
sent; this module verifies what it can locally: every ratio in [0, 1],
single-page responses only. Out-of-range geometry raises rather than clamps,
because a clamped box is a measurement quietly edited.

Confidence is parsed and returned beside the words but consumed by nothing.
Filtering on it would be a tuned threshold no measurement has asked for.
"""

from __future__ import annotations

from pipeline.textlayer import Word


class TextractShape(ValueError):
    """The response does not have the documented shape."""


def _ratio(name: str, value) -> float:
    if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise TextractShape(f"{name} out of [0, 1]: {value!r}")
    return float(value)


def words_from_response(response: dict) -> list[tuple[Word, float]]:
    """WORD blocks as (Word, confidence) pairs, in document order.

    Raises TextractShape on a multi-page response, a missing geometry, or a
    coordinate outside [0, 1]. Non-WORD blocks (PAGE, LINE) are skipped:
    lines duplicate their words' text and geometry at a coarser grain.
    """
    pages = response.get("DocumentMetadata", {}).get("Pages")
    if pages != 1:
        raise TextractShape(f"expected a single-page response, got {pages!r}")
    blocks = response.get("Blocks")
    if not isinstance(blocks, list):
        raise TextractShape("no Blocks list in response")
    out: list[tuple[Word, float]] = []
    for block in blocks:
        if block.get("BlockType") != "WORD":
            continue
        text = block.get("Text")
        if not text:
            raise TextractShape("WORD block without Text")
        try:
            box = block["Geometry"]["BoundingBox"]
        except (KeyError, TypeError):
            raise TextractShape(f"WORD block without a bounding box: {text!r}")
        left = _ratio("Left", box.get("Left"))
        top = _ratio("Top", box.get("Top"))
        right = _ratio("Left+Width", left + box.get("Width", -1.0))
        bottom = _ratio("Top+Height", top + box.get("Height", -1.0))
        if right <= left or bottom <= top:
            raise TextractShape(f"degenerate box for {text!r}")
        confidence = block.get("Confidence")
        if not isinstance(confidence, (int, float)):
            raise TextractShape(f"WORD block without Confidence: {text!r}")
        out.append(((left, top, right, bottom, text), float(confidence)))
    return out


def words_only(response: dict) -> list[Word]:
    """The words without their confidences, for source-blind callers."""
    return [word for word, _ in words_from_response(response)]
