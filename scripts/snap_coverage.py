#!/usr/bin/env python3
"""Measure how many extracted values the embedded text layer can locate.

The model's provenance boxes are confabulated (DEFECTS #29); the page's
embedded text layer carries word-level boxes (`pdftotext -bbox`) that are
measured, not modelled. This script asks, for every `present` value in the
finished smoke run: can the value's raw text be matched to word boxes on its
page, and how confidently?

One number, three decisions. The match rate says whether snapping is a viable
geometry mechanism; the residue says how much load a widened-band fallback
must carry; and the residue is also Textract's ceiling, since word inventory
is the only thing Textract would add.

Matching is deliberately conservative, per the approved rule: a snapped box
that is wrong is worse than a schematic one, because it looks grounded. So a
value counts as snapped only when its anchor word matches uniquely, or when
the model's own box disambiguates decisively. Everything else is reported as
residue, never guessed.

No API calls. Reads the run's cache under the prompt hash the run recorded.

Coordinate caveat, stated rather than hidden: word boxes are fractions of the
PDF page box; model boxes are fractions of the embedded scan image. On this
corpus the scan fills the page, so the spaces align; a page where they did
not would shear every distance in the disambiguation step.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import pageclass as pc              # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
OUT = ROOT / "data" / "extract" / "snap_coverage.jsonl"

_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)"'
    r'>([^<]*)</word>')
_PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')

#: An anchor word is selective enough to match on: four or more characters,
#: or three or more digits. "of", "3" and "N/A" match half a page each.
_MIN_ALPHA = 4
_MIN_DIGITS = 3

#: OCR digit confusions folded on BOTH sides before comparing. Narrow on
#: purpose; a wide table would merge words that are genuinely different.
_FOLD = str.maketrans({"o": "0", "l": "1", "i": "1"})

#: The model box is trusted only this far as a tiebreak: a candidate within
#: this centre distance, in page fractions, with the measured downward bias
#: meaning the true word usually sits at or above the box.
_PRIOR_RADIUS = 0.30


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def fold(text: str) -> str:
    return norm(text).translate(_FOLD)


def is_anchor(word: str) -> bool:
    cleaned = norm(word)
    digits = sum(c.isdigit() for c in cleaned)
    return len(cleaned) >= _MIN_ALPHA or digits >= _MIN_DIGITS


def page_words(pdf: Path, page: int):
    """(x0, y0, x1, y1, text) in page fractions, from the embedded layer."""
    html = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page),
         str(pdf), "-"], capture_output=True, text=True).stdout
    size = _PAGE.search(html)
    if not size:
        return []
    width, height = float(size.group(1)), float(size.group(2))
    words = []
    for m in _WORD.finditer(html):
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        words.append((x0 / width, y0 / height, x1 / width, y1 / height,
                      m.group(5)))
    return words


def classify_snap(raw: str, box, words):
    """One of: unique, disambiguated, ambiguous, no_match, unanchored."""
    anchors = [w for w in (raw or "").split() if is_anchor(w)]
    if not anchors:
        return "unanchored", None
    best = None
    for anchor in anchors:
        target = fold(anchor)
        matches = [w for w in words if fold(w[4]) == target]
        if matches and (best is None or len(matches) < len(best)):
            best = matches
            if len(best) == 1:
                break
    if best is None:
        return "no_match", None
    if len(best) == 1:
        return "unique", best[0]
    if box is not None:
        bx, by = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        close = [w for w in best
                 if ((w[0] + w[2]) / 2 - bx) ** 2
                 + ((w[1] + w[3]) / 2 - by) ** 2 <= _PRIOR_RADIUS ** 2
                 and (w[1] + w[3]) / 2 <= by + 0.05]
        if len(close) == 1:
            return "disambiguated", close[0]
    return "ambiguous", None


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(
        CACHE, prompt_hash=extractor.recorded_prompt_hash(SMOKE))

    by_outcome: Counter = Counter()
    by_era = defaultdict(Counter)
    by_kind = defaultdict(Counter)
    per_doc = []

    with OUT.open("w") as out:
        for line in SMOKE.open():
            if not line.strip():
                continue
            doc = json.loads(line)
            record_id, file_index, _ = pc.parse_page_id(doc["page_id"])
            entry = records[record_id]
            pdf = RAW / record_id / entry["files"][file_index]["name"]
            result = extractor.extract_document(
                None, pdf, tuple(doc["pages"]), record_id=record_id,
                file_index=file_index, cache=cache)
            if result.report is None:
                continue

            words = {page: page_words(pdf, page) for page in doc["pages"]}
            era = doc.get("form_revision") or "unknown"
            counts: Counter = Counter()
            for name, value in result.report.named_values():
                if value.region is None:
                    continue
                outcome, hit = classify_snap(
                    value.raw or value.value or "", value.region.box,
                    words.get(value.region.page, []))
                counts[outcome] += 1
                by_outcome[outcome] += 1
                by_era[era][outcome] += 1
                kind = "table" if "[" in name else "scalar"
                by_kind[kind][outcome] += 1
                out.write(json.dumps({
                    "record_id": record_id, "pages": doc["pages"],
                    "field": name, "raw": value.raw, "outcome": outcome,
                    "snapped_box": list(hit[:4]) if hit else None,
                    "snapped_word": hit[4] if hit else None}) + "\n")
            per_doc.append((record_id, doc["pages"], era, counts))

    def rate(counts: Counter) -> str:
        total = sum(counts.values())
        snapped = counts["unique"] + counts["disambiguated"]
        return (f"{snapped:3d}/{total:<3d} {snapped / total:6.1%}  "
                f"(u {counts['unique']}, d {counts['disambiguated']}, "
                f"ambig {counts['ambiguous']}, none {counts['no_match']}, "
                f"unanchored {counts['unanchored']})") if total else "  none"

    print("SNAP COVERAGE: values the embedded text layer can locate\n")
    print(f"  overall            {rate(by_outcome)}\n")
    print("  by era (geometry expected to follow the value-accuracy "
          "gradient; stated, not hidden):")
    for era in sorted(by_era):
        print(f"    {era:16s} {rate(by_era[era])}")
    print("\n  by kind:")
    for kind in sorted(by_kind):
        print(f"    {kind:16s} {rate(by_kind[kind])}")
    print("\n  per document:")
    for record_id, pages, era, counts in per_doc:
        print(f"    {record_id} {str(pages):10s} {era:16s} {rate(counts)}")
    print(f"\n  the residue (ambig + none + unanchored) is the widened-band "
          "fallback's load, and Textract's ceiling")
    print(f"\n{OUT}")


if __name__ == "__main__":
    main()
