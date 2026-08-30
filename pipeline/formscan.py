#!/usr/bin/env python3
"""Find RRC form numbers in a page's OCR text.

Not a classifier. This exists to answer one question cheaply and without a
model: which form numbers actually occur as page headers across the corpus,
and therefore which ones the taxonomy has to cover.

The distinction that matters is a form's own header against a reference to
some other form. A P-4 face carries "Operator name exactly as shown on Form
P-5 Organization Report" in its third field, so a naive count says P-5 appears
on 373 pages when it is mostly P-4s pointing at it. Header tokens sit in the
first few hundred characters, in the top-right of the page, and are not
preceded by "shown on", "see", "per" and friends.

The OCR is poor. "FORM G-1" reads as "F(R)lC7lbP G(o)IL" on the one page known
to be a G-1 face, so every count here is a floor and never an estimate.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

#: A form number: one or two letters, a hyphen, one or two digits, maybe a
#: trailing letter. W-2, P-17, W-4A, GT-1.
FORM_TOKEN = re.compile(r"\b(?:FORM\s+)?([A-Z]{1,2}-\d{1,2}[A-Z]?)\b")

#: Prefixes that are never RRC form numbers, however form-shaped they look.
#:
#: "A-38" is the abstract number of an original Texas land survey, as in
#: "L. McLaughlin A-38, Robertson County". Plats carry several each, and this
#: corpus is full of plats, so without this the scanner reports a dozen form
#: families that do not exist (DEFECTS #11).
NOT_FORM_PREFIXES = frozenset({"A"})

#: Wording that makes the following token a reference to a different form.
#:
#: The leading \b is load-bearing. Without it the bare "on" alternative also
#: matches the tail of "DIVISION", and "RAILROAD COMMISSION OF TEXAS / OIL AND
#: GAS DIVISION" is the standard header block immediately before the form
#: number on these forms, so every such header was silently discarded.
CROSS_REFERENCE = re.compile(
    r"\b(shown on|as per|as shown|see|per|filed on|filed with|attached|"
    r"copy of|copies of|accompanying|pursuant to|on)\s+(RRC\s+)?(FORM\s+)?$",
    re.I)

#: How far back to look for that wording. "pursuant to Form " is 17
#: characters, so a 16-character window silently let it through.
LOOKBACK_CHARS = 28

#: How much of a page counts as its header region. The form number is printed
#: top-right, which lands early in OCR reading order.
HEADER_CHARS = 400


def header_tokens(text: str, header_chars: int = HEADER_CHARS) -> set[str]:
    """Form numbers that look like this page's own header.

    Pure. Excludes tokens introduced by cross-referencing wording, which is
    what separates a P-4 from a P-4's mention of the P-5 it derives from.
    """
    head = text[:header_chars]
    found = set()
    for match in FORM_TOKEN.finditer(head):
        token = match.group(1).upper()
        if token.split("-", 1)[0] in NOT_FORM_PREFIXES:
            continue
        preceding = head[max(0, match.start() - LOOKBACK_CHARS):match.start()]
        if CROSS_REFERENCE.search(preceding):
            continue
        found.add(token)
    return found


# ------------------------------------------------------------------- corpus

def page_texts(manifest: Path, raw: Path) -> dict[tuple[str, int, int], str]:
    """OCR text for every page, one pdftotext call per file.

    Splitting on form feed is far cheaper than 3,689 per-page calls.
    """
    import subprocess

    out: dict[tuple[str, int, int], str] = {}
    for line in manifest.open():
        if not line.strip():
            continue
        record = json.loads(line)
        for index, entry in enumerate(record["files"]):
            pdf = raw / record["record_id"] / entry["name"]
            if not pdf.exists():
                continue
            text = subprocess.run(
                ["pdftotext", str(pdf), "-"],
                capture_output=True, text=True).stdout
            parts = text.split("\f")
            for page in range(1, (entry.get("pages") or 0) + 1):
                body = parts[page - 1] if page - 1 < len(parts) else ""
                out[(record["record_id"], index, page)] = body
    return out


def scan_corpus(manifest: Path, raw: Path, cache: Path | None = None) -> Counter:
    """Header-token counts across every page, cached.

    The scan costs about half a minute of pdftotext; the cache keeps tier 2
    fast after the first run. Cached under data/, which is git-ignored, since
    it is derived from records carrying personal data.
    """
    if cache is not None and cache.exists():
        return Counter(json.loads(cache.read_text()))

    counts: Counter = Counter()
    for text in page_texts(manifest, raw).values():
        for token in header_tokens(text):
            counts[token] += 1

    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(dict(counts), indent=2, sort_keys=True))
    return counts
