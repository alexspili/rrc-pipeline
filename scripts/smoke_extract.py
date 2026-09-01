#!/usr/bin/env python3
"""Run extraction over 20 completion documents and write the labelling template.

Not the full run. Twenty documents is the tiered-eval smoke slice from
HANDOFF: enough to see whether the code path works and what it costs, cheap
enough to repeat on every iteration.

**Why the draw is not stratified by form revision.** That was the plan, and the
text layer cannot support it. A revision date is recoverable from the OCR on 62
of the 238 predicted completion faces, and those are overwhelmingly the
cleanest modern forms: every year found is 1983 or later. Stratifying on it
would systematically over-sample the newest paper, which is the opposite of
what era stratification is for.

So the draw is stratified on a proxy that does not degrade with age, and the
era stratification moves to where the evidence actually is. The probe read
"Rev. 6/30/75" correctly off an image whose text layer yields nothing, so the
model reports the revision and the 15-document ground-truth subset is drawn to
span the revisions extraction actually found. One step later, and on a signal
that works.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import formscan                     # noqa: E402
from pipeline import pageclass as pc              # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
OUT = ROOT / "data" / "extract"
CACHE = OUT / "cache_smoke.jsonl"
RESULTS = OUT / "smoke.jsonl"
TEMPLATE = ROOT / "tests" / "fixtures" / "extract_truth.csv"

SIZE = 20
SEED = 20260901

#: Forced into the draw: the document scripts/probe_sonnet.py measured, so the
#: coded path can be compared against the probe on identical input.
ANCHOR = "1493495-0-9"

REVISION = re.compile(r"Rev[.\s]*\s*\d{1,2}\s*[/\-]", re.I)

#: Pages that belong with a face, when the census says so. A placeholder for
#: the reassembly step, which is its own piece of work: only 79 of 238 faces
#: are followed by a completion page at all, and 46 are followed by another
#: face. Every document records the pages that went into it.
CONTINUATION_PARTS = {"sec_ii", "sec_iii", "continuation", "back_instructions",
                      "unknown"}


def census():
    return {json.loads(l)["page_id"]: json.loads(l)
            for l in CENSUS.open() if l.strip()}


def files_of(record_id: str):
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            return json.loads(line)["files"]
    return []


def stratum(page_id: str, texts, headers) -> str:
    record, index, page = pc.parse_page_id(page_id)
    head = texts.get((record, index, page), "")[:800]
    if REVISION.search(head):
        return "A_revision_legible"
    if {"G-1", "W-2"} & headers.get(page_id, set()):
        return "B_form_number_legible"
    return "C_neither"


def document_pages(page_id: str, rows) -> tuple[int, ...]:
    record, index, page = pc.parse_page_id(page_id)
    pages = [page]
    nxt = rows.get(pc.page_id(record, index, page + 1))
    if nxt and not nxt.get("error"):
        completion = (nxt["form_class"] in ("g1", "w2")
                      and nxt["part"] in CONTINUATION_PARTS)
        unnamed = (nxt["form_class"] == "other_form"
                   and nxt["part"] in CONTINUATION_PARTS)
        if completion or unnamed:
            pages.append(page + 1)
    return tuple(pages)


def select(rows, texts, headers):
    faces = sorted(p for p, r in rows.items()
                   if not r.get("error") and r["form_class"] in ("g1", "w2")
                   and r["part"] == "face")
    by = {}
    for page_id in faces:
        by.setdefault(stratum(page_id, texts, headers), []).append(page_id)

    sizes = {"A_revision_legible": 5, "B_form_number_legible": 3,
             "C_neither": SIZE - 8}
    rng = random.Random(SEED)
    chosen = []
    for name, want in sizes.items():
        frame = [p for p in by.get(name, []) if p != ANCHOR]
        if name == stratum(ANCHOR, texts, headers):
            chosen.append(ANCHOR)
            want -= 1
        chosen.extend(sorted(rng.sample(frame, min(want, len(frame)))))
    return sorted(chosen), {k: len(v) for k, v in by.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = census()
    texts = formscan.page_texts(MANIFEST, RAW)
    headers = {pc.page_id(*k): formscan.header_tokens(v)
               for k, v in texts.items()}
    chosen, frames = select(rows, texts, headers)

    print(f"frame: 238 predicted completion faces")
    for name in sorted(frames):
        print(f"   {name:24s} {frames[name]:4d}")
    print(f"\ndrawing {len(chosen)} documents, seed {SEED}, "
          f"anchor {ANCHOR} forced\n")

    docs = []
    for page_id in chosen:
        record, index, _ = pc.parse_page_id(page_id)
        pages = document_pages(page_id, rows)
        docs.append({"page_id": page_id, "record_id": record,
                     "file_index": index, "pages": pages,
                     "stratum": stratum(page_id, texts, headers),
                     "predicted": rows[page_id]["form_class"]})
        print(f"   {page_id:16s} {rows[page_id]['form_class']:3s} "
              f"pages {list(pages)}")
    multi = sum(1 for d in docs if len(d["pages"]) > 1)
    print(f"\n   {multi} of {len(docs)} documents carry a continuation page")

    if args.dry_run:
        return

    OUT.mkdir(parents=True, exist_ok=True)
    api = extractor.client()
    cache = classify.ResultCache(CACHE, prompt_hash=extractor.PROMPT_HASH)
    spend = notional = 0.0
    written = []

    with RESULTS.open("w") as out:
        for i, doc in enumerate(docs, 1):
            pdf = RAW / doc["record_id"] / files_of(doc["record_id"])[doc["file_index"]]["name"]
            result = extractor.extract_document(
                api, pdf, doc["pages"], record_id=doc["record_id"],
                file_index=doc["file_index"], cache=cache)
            notional += result.cost_usd()
            if not result.cached:
                spend += result.cost_usd()
            report = result.report
            out.write(json.dumps({
                "page_id": doc["page_id"], "stratum": doc["stratum"],
                "pages": list(doc["pages"]),
                "predicted_class": doc["predicted"],
                "form_class": report.form_class if report else None,
                "form_revision": (report.form_revision.raw
                                  if report else None),
                "values": len(list(report.values())) if report else 0,
                "present": report.present if report else 0,
                "located": report.located if report else 0,
                "dropped": list(report.dropped) if report else [],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cached": result.cached, "error": result.error,
            }) + "\n")
            written.append((doc, result))
            mark = "!" if result.error else " "
            rev = (report.form_revision.raw if report
                   and report.form_revision.raw else "-")
            klass = str(report.form_class) if report else "FAIL"
            note = f"  {result.error[:60]}" if result.error else ""
            print(f"  {i:2d}/{len(docs)} {mark} {doc['page_id']:16s} "
                  f"{klass:4s} rev={str(rev)[:14]:14s} "
                  f"{report.present if report else 0:3d} present{note}")

    print(f"\nspent: ${spend:.2f}   (${notional:.2f} if the cache were cold)")
    print(f"results: {RESULTS}")
    write_template(written)


def write_template(written) -> None:
    """The 15-document ground-truth sheet, stratified by the revision the
    extraction actually read, which is the signal the text layer could not
    give before the run.
    """
    ok = [(d, r) for d, r in written if r.report]
    buckets = {}
    for doc, result in ok:
        raw = result.report.form_revision.raw or ""
        year = re.search(r"(\d{2,4})\s*$", raw.strip())
        key = year.group(1) if year else "unknown"
        buckets.setdefault(key, []).append((doc, result))

    rng = random.Random(SEED + 1)
    picked, order = [], sorted(buckets, key=lambda k: (k == "unknown", k))
    while len(picked) < min(15, len(ok)):
        for key in order:
            if buckets[key] and len(picked) < 15:
                picked.append(buckets[key].pop(rng.randrange(len(buckets[key]))))

    fields = (["document.form_revision"]
              + [f"identity.{f}" for f in __import__(
                  "pipeline.extract", fromlist=["x"]).IDENTITY_FIELDS]
              + [f"completion.{f}" for f in __import__(
                  "pipeline.extract", fromlist=["x"]).COMPLETION_FIELDS]
              + ["test.date_of_test"])

    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    with TEMPLATE.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["seq", "record_id", "pages", "field", "value",
                         "status", "note"])
        for seq, (doc, _) in enumerate(sorted(picked, key=lambda p: p[0]["page_id"]), 1):
            for name in fields:
                writer.writerow([seq, doc["record_id"],
                                 " ".join(map(str, doc["pages"])),
                                 name, "", "", ""])
    print(f"template: {TEMPLATE}  "
          f"({len(picked)} documents x {len(fields)} fields)")
    print("  revision buckets drawn from:",
          dict(Counter(r.report.form_revision.raw or "unknown"
                       for _, r in ok)))


if __name__ == "__main__":
    main()
