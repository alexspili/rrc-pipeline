#!/usr/bin/env python3
"""The corpus extraction run, batched, over the documents reassembly built.

One command and one spend. Nothing here decides anything: the documents come
from data/extract/reassemble.jsonl exactly as the reassembly run grouped them,
and whether that grouping ships at all is the fourth sitting's decision
(docs/labeling-protocol-reassemble.md).

Two modes, and the sitting picks between them rather than this script:

  --grouped     documents as reassembly built them, attachments included
  --faces-only  every document reduced to its face page

`--faces-only` is the escape elected in advance for a failing sitting. It is
not a cheaper option chosen for cost: it gives up the casing, depth and
completion tables that live on a reverse side, on the documents that have one.

Costs money, so it refuses to start without --confirm and prints what it will
spend first. Cached documents are free and are never re-sent (CLAUDE.md rule
7), so a run that dies halfway resumes for nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import extractor                     # noqa: E402
from pipeline import pageclass as pc               # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"
OUT = ROOT / "data" / "extract"
CACHE = OUT / "cache_corpus.jsonl"
RESULTS = OUT / "corpus.jsonl"


def documents(faces_only: bool) -> list[dict]:
    """Every document reassembly built, as batch input.

    The custom_id is the face's page id. Results come back keyed by it and by
    nothing else, so it has to be unique; `run_batched` refuses a duplicate
    rather than letting one document overwrite another.
    """
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    out = []
    for line in DOCS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        rid, fi = row["record_id"], int(row["file_index"])
        pages = (row["face"],) if faces_only else tuple(sorted(row["pages"]))
        out.append({
            "custom_id": pc.page_id(rid, fi, row["face"]),
            "record_id": rid, "file_index": fi, "pages": pages,
            "pdf": RAW / rid / records[rid]["files"][fi]["name"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--grouped", action="store_true",
                      help="documents as reassembly grouped them")
    mode.add_argument("--faces-only", action="store_true",
                      help="face pages alone; the elected escape")
    ap.add_argument("--confirm", action="store_true",
                    help="actually spend money")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N documents only, for a live smoke test")
    args = ap.parse_args()

    docs = documents(args.faces_only)
    if args.limit:
        docs = docs[:args.limit]

    shape = Counter(len(d["pages"]) for d in docs)
    print(f"mode: {'faces only' if args.faces_only else 'grouped'}")
    print(f"documents: {len(docs)}  "
          + ", ".join(f"{n} x {p}-page" for p, n in sorted(shape.items())))

    OUT.mkdir(parents=True, exist_ok=True)
    cache = classify.ResultCache(CACHE, prompt_hash=extractor.PROMPT_HASH)
    fresh = [d for d in docs
             if cache.get(extractor.cache_key(cache, d["pdf"], d["pages"]))
             is None]
    print(f"cached already: {len(docs) - len(fresh)}   to send: {len(fresh)}")

    # Priced from the smoke run's measured tokens by the same function the
    # estimate script uses, so this number and that one cannot disagree.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "estimate_batch", ROOT / "scripts" / "estimate_batch.py")
    est = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(est)
    tokens = est.tokens_from_smoke()
    standard = sum(est.price(tokens, len(d["pages"])) for d in fresh)
    print(f"cost to send: ${standard:.2f} standard, "
          f"${standard * extractor.BATCH_DISCOUNT:.2f} batched")
    print(f"prompt hash: {extractor.PROMPT_HASH}")

    if not args.confirm:
        print("\ndry run. Nothing sent. Add --confirm to spend.")
        return

    api = extractor.client()
    results = extractor.run_batched(api, docs, cache=cache,
                                    on_progress=lambda m: print(f"  {m}"))

    spend = notional = 0.0
    errors = Counter()
    with RESULTS.open("w") as fh:
        for doc in docs:
            result = results[doc["custom_id"]]
            notional += result.cost_usd(batched=True)
            if not result.cached:
                spend += result.cost_usd(batched=True)
            report = result.report
            if result.error:
                errors[result.error.split(";")[0][:40]] += 1
            fh.write(json.dumps({
                "page_id": doc["custom_id"],
                "record_id": doc["record_id"],
                "file_index": doc["file_index"],
                "pages": list(doc["pages"]),
                "mode": "faces_only" if args.faces_only else "grouped",
                "prompt_hash": extractor.PROMPT_HASH,
                "form_class": report.form_class if report else None,
                "form_revision": (report.form_revision.raw
                                  if report else None),
                "values": len(list(report.values())) if report else 0,
                "present": report.present if report else 0,
                "located": report.located if report else 0,
                "labelled": sum(1 for v in report.values()
                                if v.found_in) if report else 0,
                "dropped": list(report.dropped) if report else [],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cached": result.cached, "error": result.error,
            }) + "\n")

    # Standing rule 9: the residue is counted before the run is called done.
    ok = sum(1 for d in docs if results[d["custom_id"]].report is not None)
    print(f"\ndocuments extracted: {ok} of {len(docs)}")
    if errors:
        print("failures, by kind:")
        for kind, n in errors.most_common():
            print(f"  {n:4d}  {kind}")
    print(f"spent: ${spend:.2f}   (${notional:.2f} if the cache were cold)")
    print(f"results: {RESULTS}")


if __name__ == "__main__":
    main()
