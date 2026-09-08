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


#: An edge-flush box's Left plus Width lands a few parts per billion over
#: 1.0 in floating point, and three real pages were refused for it
#: (DEFECTS #76). Inside this tolerance the value is clamped to the bound;
#: beyond it the box is genuinely out of range and still raises. At most
#: 1e-6 of a page, three orders of magnitude under the registration
#: residuals it could perturb.
EDGE_EPS = 1e-6


def _ratio(name: str, value) -> float:
    if not isinstance(value, (int, float)):
        raise TextractShape(f"{name} out of [0, 1]: {value!r}")
    if not -EDGE_EPS <= value <= 1.0 + EDGE_EPS:
        raise TextractShape(f"{name} out of [0, 1]: {value!r}")
    return min(1.0, max(0.0, float(value)))


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


# --------------------------------------------------------------------------
# the alias harvest: observed spellings, never invented ones
# --------------------------------------------------------------------------
# A fuel page has two readings of the same paper: Textract's, which pools,
# and the embedded layer's, which is what a runtime page will offer. Where
# one clean word and one embedded word co-locate one-to-one, the embedded
# spelling is an OBSERVED alias of that token: `elevatlon` seen where
# `elevation` prints. Aliases are harvested and reported beside the
# stage-five probe and are NOT in its graded configuration, which stays
# exact-token; adopting them is a separate proposal argued from the
# harvest's own registration table.

#: Two words co-locate when their boxes overlap by at least this
#: intersection-over-union. Below it, neighbouring words on a dense line
#: start pairing; well above it, a one-character OCR insertion that shifts
#: the box breaks a genuine pair.
ALIAS_MIN_IOU = 0.3


def _iou(a, b) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def harvest_aliases(textract_words: list[Word], embedded_words: list[Word],
                    min_iou: float = ALIAS_MIN_IOU) -> dict[str, str]:
    """{clean token: embedded spelling} for one page, both sides unique.

    A pair is kept only when each word is unique on its own page (same rule
    that admits an anchor), the two boxes co-locate, the pairing is
    one-to-one in both directions, and the spellings differ. An identical
    spelling is not an alias, it is the exact match registration already
    makes.
    """
    from collections import Counter
    from pipeline.textlayer import norm

    def unique(words):
        counts = Counter(norm(w[4]) for w in words
                         if len(norm(w[4])) >= 4)
        return {norm(w[4]): tuple(w[:4]) for w in words
                if counts.get(norm(w[4])) == 1}

    t_unique, e_unique = unique(textract_words), unique(embedded_words)
    pairs = []
    for t_token, t_box in t_unique.items():
        for e_token, e_box in e_unique.items():
            if _iou(t_box, e_box) >= min_iou:
                pairs.append((t_token, e_token))
    t_counts = Counter(t for t, _ in pairs)
    e_counts = Counter(e for _, e in pairs)
    return {t: e for t, e in pairs
            if t_counts[t] == 1 and e_counts[e] == 1 and t != e}


def expand_anchors(anchors: dict, aliases: dict[str, list[str]]) -> dict:
    """The anchor table with observed aliases as extra exact-match keys.

    An alias that is itself a real anchor token is dropped: the real token
    owns its spelling. An alias observed for two different anchors is
    dropped: matching it would be a choice, and the settled rule forbids
    making that choice. The returned table maps each surviving alias to its
    anchor's own entry, so registration code needs no change at all.
    """
    from collections import Counter
    claims = Counter()
    for token, spellings in aliases.items():
        for spelling in set(spellings):
            claims[spelling] += 1
    out = dict(anchors)
    for token, spellings in aliases.items():
        if token not in anchors:
            continue
        for spelling in set(spellings):
            if spelling in anchors or claims[spelling] > 1:
                continue
            out[spelling] = anchors[token]
    return out
