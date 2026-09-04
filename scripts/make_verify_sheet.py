#!/usr/bin/env python3
"""Build the reassembly verification sitting: sheet plus page images.

The sample and the decision rule were fixed in
docs/labeling-protocol-reassemble.md before this script drew anything. Read
that first. This only carries the sampling out.

Three parts on one sheet:

  A  eight attachments, to be judged as pairs against the paper. This is the
     only part that decides anything, and it gates the corpus spend.
  B  found_in spot-checks on the pages in part A.
  C  the contradicted-but-agreeing list, plus the Crawford/Triolo pair from
     outside the ground-truth set.

No API calls.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import identity                      # noqa: E402
from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"
REPORT = ROOT / "data" / "extract" / "reassemble_report.txt"
CACHE = ROOT / "data" / "extract" / "cache_identity.jsonl"
SHEET = ROOT / "tests" / "fixtures" / "attachment_verify.csv"
OUT = ROOT / "data" / "labelset" / "verify_pairs"

SEED = 20260903

#: Fixed in the protocol before the draw.
GROUND_TRUTH = {("1493495", 0, 10, 9), ("1495193", 0, 8, 7)}
HIGHEST_RISK = {("1495195", 0, 87, 52), ("1495195", 0, 114, 89)}
SAMPLE_SIZE = 8

#: found_in rows are all written out, because a reader wants to see them
#: beside the page anyway, but only this many are marked for checking. All 72
#: would be a second sitting, and found_in does not gate anything.
CHECK_SOURCES = 12

#: Outside the ground-truth set, carried into part C because it was the first
#: contradicted pair ever flagged and has never been resolved.
CRAWFORD = ("1493399", 0, (21, 29))


def attachments():
    out = []
    for line in DOCS.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        for page in doc["pages"]:
            if page != doc["face"]:
                out.append((doc["record_id"], doc["file_index"], page,
                            doc["face"],
                            dict(doc["evidence"]).get(page, [])))
    return sorted(out)


def draw(all_pairs):
    keyed = {(r, f, p, face): ev for r, f, p, face, ev in all_pairs}
    picked = [k for k in keyed if k in GROUND_TRUTH]
    picked += [k for k in keyed if k in HIGHEST_RISK and k not in picked]
    rest = sorted(k for k in keyed if k not in picked)
    random.Random(SEED).shuffle(rest)
    picked += rest[:SAMPLE_SIZE - len(picked)]
    return [(k, keyed[k]) for k in picked]


def render_pages(records, wanted):
    render.preflight()
    OUT.mkdir(parents=True, exist_ok=True)
    for record_id, file_index, pages in sorted(wanted):
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        for page in pages:
            name = f"{record_id}-{file_index}_p{page:03d}.png"
            if (OUT / name).exists():
                continue
            image = render.downscale_image(
                render.extract_page_image(pdf, page).convert("RGB"), cap=2400)
            image.save(OUT / name)


def main() -> None:
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(CACHE, prompt_hash=identity.PROMPT_HASH)
    sample = draw(attachments())

    rows, wanted = [], set()
    for (record_id, file_index, page, face), evidence in sample:
        why = ("ground truth" if (record_id, file_index, page, face)
               in GROUND_TRUTH else
               "flagged highest risk" if (record_id, file_index, page, face)
               in HIGHEST_RISK else "random, seed 20260903")
        rows.append({
            "part": "A", "item": f"{record_id}-{file_index} p{page}+p{face}",
            "record_id": record_id, "file_index": file_index,
            "pages": f"{face} {page}", "detail": f"joined on {', '.join(evidence)}",
            "in_sample_because": why, "verdict": "", "note": ""})
        wanted.add((record_id, file_index, (face, page)))

    # Part B: what the reader says each value came from, on those pages.
    for record_id, file_index, pages in sorted(wanted):
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        for page in pages:
            hit = cache.get(cache.key(render.doc_hash(pdf), page, "identity"))
            if hit is None:
                continue
            read = identity.parse(hit["body"], page)
            for field, label in sorted(read.found_in.items()):
                if not label:
                    continue
                rows.append({
                    "part": "B", "item": f"{record_id}-{file_index} p{page}",
                    "record_id": record_id, "file_index": file_index,
                    "pages": str(page),
                    "detail": f"{field} = {read.values[field].raw!r} "
                              f"<- {label}",
                    "in_sample_because": "on a part A page",
                    "verdict": "", "note": ""})

    # Part C: the contradicted-but-agreeing list, verbatim from the report.
    if REPORT.exists():
        block = REPORT.read_text().split("CONTRADICTED BUT AGREEING", 1)
        if len(block) > 1:
            current = None
            for line in block[1].splitlines():
                if line.startswith("  ") and " vs face p" in line:
                    current = line.strip()
                elif current and line.strip().startswith(
                        ("DISAGREE", "agreed on")):
                    rows.append({
                        "part": "C", "item": current, "record_id": "",
                        "file_index": "", "pages": "",
                        "detail": line.strip(),
                        "in_sample_because": "contradicted but agreeing",
                        "verdict": "", "note": ""})
    rows.append({
        "part": "C", "item": f"{CRAWFORD[0]} p21 vs p29",
        "record_id": CRAWFORD[0], "file_index": 0, "pages": "21 29",
        "detail": "operator 'Crawford Energy, Inc.' vs 'Crawford Energy. Inc.' "
                  "(folds to one); lease 'TRIOLO # 1' vs 'C.A. Triola Unit' "
                  "(does not fold)",
        "in_sample_because": "first pair ever flagged; outside the "
                             "ground-truth set; never resolved",
        "verdict": "", "note": ""})
    wanted.add((CRAWFORD[0], 0, CRAWFORD[2]))

    # Mark the found_in rows to actually check. Drawn rather than chosen,
    # because the failure this is looking for is invisible: a value from the
    # wrong box looks exactly like one from the right box, so picking the
    # suspicious-looking ones would look everywhere except where it hides.
    part_b = [r for r in rows if r["part"] == "B"]
    for row in part_b:
        row["check"] = ""
    for row in random.Random(SEED + 1).sample(
            part_b, min(CHECK_SOURCES, len(part_b))):
        row["check"] = "CHECK"
    for row in rows:
        row.setdefault("check", "")

    render_pages(records, wanted)
    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    counts = {p: sum(1 for r in rows if r["part"] == p) for p in "ABC"}
    print(f"sheet: {SHEET}")
    print(f"  part A, the gate: {counts['A']} pairs")
    marked = sum(1 for r in rows if r["part"] == "B" and r["check"])
    print(f"  part B, found_in: {counts['B']} values, {marked} marked CHECK")
    print(f"  part C, contradicted: {counts['C']} lines")
    print(f"images: {OUT}  ({len(list(OUT.glob('*.png')))} pages)")
    print("\npart A sample and why each is in it:")
    for row in rows:
        if row["part"] == "A":
            print(f"  {row['item']:26s} {row['in_sample_because']:22s} "
                  f"{row['detail']}")


if __name__ == "__main__":
    main()
