#!/usr/bin/env python3
"""Export a finished extraction run as the static bundle the viewer reads.

No API calls. Everything here is a projection of files already on disk: the
run's results and cache, the reassembly grouping, the snap pass, the findings
pass and the manifest. Run those first; this script joins, it does not infer.

The bundle lands in data/viewer/ by default, which is inside data/ and so
never committed (CLAUDE.md rule 3): the page images and extracted values
carry personal information. The viewer's code is committable; its data is
not, and the split is load-bearing, not incidental.

Region tiers, as shipped and measured (docs/modules/extract.md, mechanism
decision of 2026-09-03):

  text_layer  the snap pass matched the value uniquely or disambiguated it;
              the exported box is the matched line run
  model       the model's own box, exported untouched; the viewer widens it
              upward at display time (R5), because widening is a display
              rule and baking it into coordinates would hide the raw claim
  (no region) page plus raw text, the floor that is never wrong

The source tag on every region is the honesty tier and the viewer renders
the tiers distinctly (DEFECTS #29's design rule).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import extractor                     # noqa: E402
from pipeline import pageclass as pc               # noqa: E402
from pipeline import render                        # noqa: E402
from pipeline import textlayer                     # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
EXTRACT = ROOT / "data" / "extract"
OUT = ROOT / "data" / "viewer"

#: Long edge of an exported page image. Larger than the 1568 sent to the
#: model, because a human zooms in where the model saw a fixed cap.
PAGE_LONG_EDGE = 1600

#: What travels with the bundle so the viewer can say it out loud. Every
#: number is measured and lives with its measurement in the module docs.
CAVEATS = [
    "A highlight is shown for 77.3% of extracted values overall; "
    "100% on 1983 paper, 54.3% on 1966 (docs/modules/extract.md).",
    "Model-box bands land 60.9% of the time overall and 11.4% on 1966 "
    "paper; that tier is the weakest thing shipped and is tagged.",
    "At least 1 snap in 15 lands on the wrong field (DEFECTS #32).",
    "Regions are locators for a reviewer, not measurements.",
]

SNAPPED = ("unique", "disambiguated")


def viewer_region(value_dict: dict, snap_row: dict | None) -> dict | None:
    """The region the viewer shows for one value, tiered. Pure.

    `value_dict` is {"region": {"page": int, "box": [l,t,r,b], "source": str}
    or None}; `snap_row` is the snap pass's row for this value, or None.
    A snapped match replaces the box with the matched line run and the source
    with text_layer; anything else ships the region it has; no region is the
    page-plus-raw floor and stays None.
    """
    region = value_dict.get("region")
    if region is None:
        return None
    if snap_row and snap_row.get("outcome") in SNAPPED \
            and snap_row.get("display_box"):
        return {"page": region["page"],
                "box": list(snap_row["display_box"]),
                "source": "text_layer"}
    return dict(region)


def value_row(name: str, value) -> dict:
    """One Value as the viewer's JSON. Pure given a pipeline Value."""
    group = name.split(".")[0].split("[")[0]
    region = None
    if value.region is not None:
        region = {"page": value.region.page,
                  "box": list(value.region.box),
                  "source": value.region.source}
    return {"field": name, "group": group,
            "status": value.status.value,
            "value": value.value, "raw": value.raw,
            "found_in": value.found_in,
            "correction": value.correction.raw if value.correction else None,
            "region": region}


def attachment_rows(grouping_row: dict) -> list[dict]:
    """Which channel attached each non-face page. Pure.

    The grouping's evidence lists the identity fields each attached page
    agreed on. A page attached with no agreeing fields was attached by the
    paper confirmer, which is the only other way in (reassemble.group).
    """
    fields_of = {int(p): list(f) for p, f in grouping_row.get("evidence", [])}
    out = []
    for page in grouping_row["pages"]:
        if page == grouping_row["face"]:
            continue
        fields = fields_of.get(int(page), [])
        out.append({"page": page,
                    "channel": "identity" if fields else "paper",
                    "fields": fields})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=EXTRACT / "corpus.jsonl")
    ap.add_argument("--cache", type=Path,
                    default=EXTRACT / "cache_corpus.jsonl")
    ap.add_argument("--grouping", type=Path,
                    default=EXTRACT / "reassemble.jsonl")
    ap.add_argument("--snap", type=Path,
                    default=EXTRACT / "snap_corpus.jsonl",
                    help="snap pass over the same run; absent is allowed "
                         "and exports the model tier only")
    ap.add_argument("--findings", type=Path,
                    default=EXTRACT / "findings_corpus.jsonl",
                    help="validation findings for the same run; absent is "
                         "allowed and exports none")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--limit", type=int, default=None,
                    help="first N documents, for a fast look")
    args = ap.parse_args()

    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    grouping = {}
    for line in args.grouping.open():
        if line.strip():
            row = json.loads(line)
            grouping[(row["record_id"], int(row["file_index"]),
                      int(row["face"]))] = row

    snap = {}
    if args.snap.exists():
        for line in args.snap.open():
            if line.strip():
                row = json.loads(line)
                snap[(row["record_id"], tuple(row["pages"]),
                      row["field"])] = row

    findings = {}
    if args.findings.exists():
        for line in args.findings.open():
            if line.strip():
                row = json.loads(line)
                findings[(row["record_id"], tuple(row["pages"]))] = \
                    row["findings"]

    cache = classify.ResultCache(
        args.cache, prompt_hash=extractor.recorded_prompt_hash(args.results))
    rows = [json.loads(l) for l in args.results.open() if l.strip()]
    if args.limit:
        rows = rows[:args.limit]

    pages_dir = args.out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    documents, search, unparsed = [], [], 0
    pages_meta: dict[str, dict] = {}
    source_counts: dict[str, int] = {}

    for row in rows:
        record_id, file_index, face = pc.parse_page_id(row["page_id"])
        entry = records[record_id]
        pdf = RAW / record_id / entry["files"][file_index]["name"]
        result = extractor.extract_document(
            None, pdf, tuple(row["pages"]), record_id=record_id,
            file_index=file_index, cache=cache)
        if result.report is None:
            unparsed += 1
            continue
        report = result.report

        values = []
        for name, value in report.named_values():
            v = value_row(name, value)
            snap_row = snap.get((record_id, tuple(row["pages"]), name))
            v["region"] = viewer_region(v, snap_row)
            tier = v["region"]["source"] if v["region"] else (
                "page" if v["status"] == "present" else "no_value")
            source_counts[tier] = source_counts.get(tier, 0) + 1
            values.append(v)

        for page in row["pages"]:
            page_key = pc.page_id(record_id, file_index, page)
            if page_key in pages_meta:
                continue
            img = render.downscale_image(
                render.extract_page_image(pdf, page), cap=PAGE_LONG_EDGE)
            img.save(pages_dir / f"{page_key}.jpg", quality=85)
            try:
                words = textlayer.page_words(pdf, page)
            except Exception:                       # noqa: BLE001
                words = []
            pages_meta[page_key] = {
                "width": img.width, "height": img.height,
                # textlayer's own statistic, the one snap grading used;
                # None when the page has no text layer at all.
                "line_height": (round(textlayer.line_height(words), 5)
                                if words else None)}

        doc = {
            "id": row["page_id"],
            "record_id": record_id, "file_index": file_index,
            "face": face, "pages": list(row["pages"]),
            "form_class": report.form_class,
            "form_revision": report.form_revision.raw,
            "attachments": attachment_rows(
                grouping[(record_id, file_index, face)]),
            "values": values,
            "findings": findings.get(
                (record_id, tuple(row["pages"])), []),
        }
        documents.append(doc)

        idv = {k: (report.identity.get(k).raw
                   if report.identity.get(k) else None)
               for k in ("operator_name", "lease_name", "well_number",
                         "field_name", "county", "api_number")}
        search.append({"id": doc["id"], "record_id": record_id,
                       "form_class": report.form_class,
                       "form_revision": report.form_revision.raw, **idv})

    (args.out / "documents.json").write_text(
        json.dumps({"documents": documents, "pages": pages_meta}))
    (args.out / "search.json").write_text(json.dumps(search))
    (args.out / "meta.json").write_text(json.dumps({
        "exported": date.today().isoformat(),
        "prompt_hash": extractor.recorded_prompt_hash(args.results),
        "documents": len(documents), "unparsed": unparsed,
        "pages": len(pages_meta),
        "regions_by_source": source_counts,
        "snap_joined": args.snap.exists(),
        "findings_joined": args.findings.exists(),
        "caveats": CAVEATS}))

    # Standing rule 9: say what the bundle does not carry, not just its size.
    print(f"documents exported: {len(documents)}   unparsed skipped: {unparsed}")
    print(f"pages rendered: {len(pages_meta)}")
    print("regions by tier:", dict(sorted(source_counts.items())))
    if not args.snap.exists():
        print("NO snap pass joined: every located value ships the model box")
    if not args.findings.exists():
        print("NO findings joined: the findings panel will be empty")
    print(args.out)


if __name__ == "__main__":
    main()
