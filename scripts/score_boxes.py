#!/usr/bin/env python3
"""Score the box grades against the pre-registered protocol.

The splits and the decision rule were fixed in
docs/labeling-protocol-extract.md before a single box was graded: rates
overall and by era, scalar against table cell, face against section page, top
against bottom half of the page. hit+near at or above 90% overall and 80% in
every era bucket keeps region provenance with a widened band; miss above 20%
in any bucket makes model boxes unusable as locators there. hit alone governs
nothing.

Also joins each graded box to its snap outcome from
scripts/snap_coverage.py, which is the number the decision memo needs: where
the model box misses, can the text layer take over?

No API calls; reads the sheet, the cache and the snap results.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402

SHEET = ROOT / "tests" / "fixtures" / "box_grades.csv"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
SNAP = ROOT / "data" / "extract" / "snap_coverage.jsonl"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"

ERA = {"1493608": "1966", "1495195": "1975", "1912687": "1983",
       "1495193": "unreadable"}

#: Which graded pages are a completion face and which are a section. Document
#: 3's page 6 is its own Section II; document 6 is a section separated from
#: its face (DEFECTS #25).
SECTION_PAGES = {("1493608", 6), ("1495193", 8)}


def regions():
    """(record_id, box_num) -> region, re-walked from the cached run with the
    same enumeration that numbered the overlays."""
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(
        CACHE, prompt_hash=extractor.recorded_prompt_hash(SMOKE))
    out = {}
    for line in SMOKE.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        record_id = doc["page_id"].rsplit("-", 2)[0]
        if record_id not in ERA:
            continue
        file_index = int(doc["page_id"].rsplit("-", 2)[1])
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        result = extractor.extract_document(
            None, pdf, tuple(doc["pages"]), record_id=record_id,
            file_index=file_index, cache=cache)
        number = 0
        for name, value in result.report.named_values():
            if value.region is None:
                continue
            number += 1
            out[(record_id, str(number))] = value.region
    return out


def snap_outcomes():
    out = {}
    if SNAP.exists():
        for line in SNAP.open():
            row = json.loads(line)
            out[(row["record_id"], row["field"])] = row["outcome"]
    return out


def rate(counts: Counter) -> str:
    total = sum(counts.values())
    if not total:
        return "  none"
    landing = counts["hit"] + counts["near"]
    return (f"hit {counts['hit']:3d}  near {counts['near']:3d}  "
            f"miss {counts['miss']:3d}   hit+near {landing / total:6.1%}  "
            f"miss {counts['miss'] / total:6.1%}")


def main() -> None:
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))
    if not all(r["grade"].strip() for r in rows):
        sys.exit("the sheet is not fully graded")
    boxes = regions()
    snaps = snap_outcomes()

    overall: Counter = Counter()
    splits = defaultdict(Counter)
    cross = defaultdict(Counter)
    for row in rows:
        grade = row["grade"].strip()
        overall[grade] += 1
        splits[("era", ERA[row["record_id"]])][grade] += 1
        kind = "table" if "[" in row["field"] else "scalar"
        splits[("kind", kind)][grade] += 1
        page_type = ("section" if (row["record_id"], int(row["page"]))
                     in SECTION_PAGES else "face")
        splits[("page", page_type)][grade] += 1
        region = boxes.get((row["record_id"], row["box_num"]))
        if region is not None:
            half = "top" if (region.box[1] + region.box[3]) / 2 < 0.5 else "bottom"
            splits[("half", half)][grade] += 1
        snap = snaps.get((row["record_id"], row["field"]), "?")
        snapped = snap in ("unique", "disambiguated")
        cross[grade]["snapped" if snapped else "unsnapped"] += 1

    print(f"BOX GRADES, {len(rows)} boxes over 4 documents\n")
    print(f"  overall            {rate(overall)}\n")
    for group in ("era", "kind", "page", "half"):
        for (kind, name), counts in sorted(splits.items()):
            if kind == group:
                print(f"  {kind}: {name:12s} {rate(counts)}")
        print()

    landing = (overall["hit"] + overall["near"]) / len(rows)
    worst_miss = max(
        counts["miss"] / sum(counts.values())
        for (kind, _), counts in splits.items() if kind == "era")
    print("PRE-REGISTERED DECISION RULE")
    print(f"  hit+near overall {landing:.1%}  (rule: at least 90%)")
    print(f"  worst era-bucket miss {worst_miss:.1%}  (rule: at most 20%)")
    verdict = (landing >= 0.90 and worst_miss <= 0.20)
    print(f"  -> {'region provenance survives with a widened band' if verdict else 'model boxes are unusable as field locators; the memo weighs snap, label-anchor and page-level'}")

    print("\nGRADE AGAINST SNAP (can the text layer take over where the box fails?)")
    for grade in ("hit", "near", "miss"):
        counts = cross[grade]
        total = sum(counts.values())
        if total:
            print(f"  {grade:5s} {total:3d} boxes: snapped {counts['snapped']:3d} "
                  f"({counts['snapped'] / total:.0%}), "
                  f"unsnapped {counts['unsnapped']:3d}")
    misses = cross["miss"]
    rescued = misses["snapped"]
    print(f"\n  of the {sum(misses.values())} misses, the text layer rescues "
          f"{rescued}; {sum(misses.values()) - rescued} are located by "
          "neither the model nor the layer")


if __name__ == "__main__":
    main()
