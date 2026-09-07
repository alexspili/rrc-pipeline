#!/usr/bin/env python3
"""Run the deterministic checks over every extracted document.

Reads the smoke run's result cache and the manifest. No API calls and no
labels, so it is free and repeatable, and it runs on every document rather
than on the fifteen that have ground truth.

That is the point of these checks. Accuracy needs somebody to key a sheet;
these do not, so they scale to the whole corpus and they are what turns
"I noticed an error in this document" into "the pipeline flags errors".
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                       # noqa: E402
from pipeline import extractor                      # noqa: E402
from pipeline import pageclass as pc                # noqa: E402
from pipeline import validate as v                  # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
OUT = ROOT / "data" / "extract" / "findings.jsonl"


def run_prompt_hash(results: Path) -> str:
    """The prompt the run being validated used."""
    return extractor.recorded_prompt_hash(results)


def manifest():
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true",
                    help="counts only, no per-finding lines")
    # Which run to validate. Defaults are the smoke run, unchanged; the
    # corpus run passes its own pair, same shape as snap_coverage's.
    ap.add_argument("--results", type=Path, default=SMOKE,
                    help="run results jsonl (default: the smoke run)")
    ap.add_argument("--cache", type=Path, default=CACHE,
                    help="that run's result cache (default: the smoke cache)")
    ap.add_argument("--out", type=Path, default=OUT,
                    help="where the findings land")
    args = ap.parse_args()

    records = manifest()
    counties = v.county_codes([(r["meta"].get("county"), r["meta"].get("api_ft"))
                               for r in records.values()])
    print(f"county map: {len(counties)} counties learned from the archive index")

    cache = classify.ResultCache(
        args.cache, prompt_hash=run_prompt_hash(args.results))
    documents = [json.loads(l) for l in args.results.open() if l.strip()]

    rules: Counter = Counter()
    checked = unparsed = 0
    with args.out.open("w") as out:
        for row in documents:
            # The page id carries the file index and a record can hold five
            # files. Assuming file 0 hashes the wrong PDF, which misses the
            # cache and would otherwise validate a document nobody extracted.
            record_id, file_index, _ = pc.parse_page_id(row["page_id"])
            entry = records[record_id]
            pdf = RAW / record_id / entry["files"][file_index]["name"]
            result = extractor.extract_document(
                None, pdf, tuple(row["pages"]), record_id=record_id,
                file_index=file_index, cache=cache)
            if result.report is None:
                unparsed += 1
                continue
            checked += 1
            findings = v.validate(result.report, counties,
                                  entry["meta"].get("api_ft"))
            for finding in findings:
                rules[(finding.severity.value, finding.rule)] += 1
            out.write(json.dumps({
                "record_id": record_id, "pages": row["pages"],
                "findings": [{"rule": f.rule, "severity": f.severity.value,
                              "message": f.message, "fields": list(f.fields)}
                             for f in findings]}) + "\n")
            if findings and not args.quiet:
                print(f"\n  {record_id} pages {row['pages']}")
                for finding in findings:
                    print(f"     {finding}")

    print(f"\n{checked} documents checked, {unparsed} unparsed")
    clean = checked - len({json.loads(l)["record_id"]
                           for l in args.out.open()
                           if json.loads(l)["findings"]})
    print(f"{clean} clean, {checked - clean} carrying at least one finding")
    if rules:
        print("\nby rule:")
        for (severity, rule), n in sorted(rules.items(),
                                          key=lambda kv: (kv[0][0] != "error",
                                                          -kv[1])):
            print(f"   {n:3d}  {severity:8s} {rule}")
    print(f"\n{args.out}")


if __name__ == "__main__":
    main()
