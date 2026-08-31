#!/usr/bin/env python3
"""Classify every page in the corpus and report what is actually in it.

This is the milestone the project hangs on. `profile_type` is POTENTIAL on all
202 records and tells you nothing about contents; four of four old-operator
files sampled during recon had no completion report at all. The fraction of
records carrying a G-1 or W-2 decides whether this corpus supports extraction,
with roughly 80 records as the floor below which fetch.py reopens.

Two guards on the headline number, because it is load-bearing and wrong in
either direction is expensive:

  Lower  an OCR floor. 72 of 202 records carry a legible G-1 or W-2 header in
         bad OCR alone (pipeline/formscan.py). The census must not come in
         under its own floor.
  Upper  a hand-verifiable sample. Under-counting only wastes a corpus;
         over-counting green-lights extraction against records that do not
         contain what the census says they do. So a seeded random sample of
         records reported as having a completion report is rendered to
         thumbnails for a human to check, and the count is not settled until
         somebody has looked.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify              # noqa: E402
from pipeline import pageclass as pc       # noqa: E402
from pipeline import render                # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "census"
VERIFY = OUT / "verify"

#: The floor from pipeline/formscan.py, measured on the OCR layer alone.
OCR_FLOOR_RECORDS = 72

#: HANDOFF's threshold: below this, reopen fetch.py.
SUFFICIENCY_THRESHOLD = 80

VERIFY_SAMPLE = 15
VERIFY_SEED = 20260830


# ----------------------------------------------------------------- enumeration

def all_pages():
    """Every page in the corpus, in manifest order."""
    pages = []
    for line in MANIFEST.open():
        if not line.strip():
            continue
        record = json.loads(line)
        for index, entry in enumerate(record["files"]):
            pdf = RAW / record["record_id"] / entry["name"]
            for page in range(1, (entry.get("pages") or 0) + 1):
                pages.append((record["record_id"], index, page, pdf))
    return pages


def reconcile(pages, labels, errors) -> list[str]:
    """Every page in the manifest is accounted for, exactly once.

    A census that quietly covers 3,600 of 3,689 pages is not a census, and
    nothing else here would notice.
    """
    problems = []
    expected = {pc.page_id(r, f, p) for r, f, p, _ in pages}
    got = {lab.id for lab in labels} | set(errors)
    if expected - got:
        problems.append(f"{len(expected - got)} pages produced neither a label "
                        f"nor an error, e.g. {sorted(expected - got)[:3]}")
    if got - expected:
        problems.append(f"{len(got - expected)} results are for pages not in "
                        f"the manifest, e.g. {sorted(got - expected)[:3]}")
    if len(pages) != 3689:
        problems.append(f"manifest yielded {len(pages)} pages, expected 3,689; "
                        "if the corpus changed, the docs test should have "
                        "failed first")
    return problems


# ------------------------------------------------------------ verification set

def verification_sample(labels, size=VERIFY_SAMPLE, seed=VERIFY_SEED):
    """Records reported as holding a completion report, sampled for a human.

    Returns [(record_id, [PageLabel, ...])], the labels being the pages that
    caused the record to be counted. Seeded, so the sample is reproducible and
    was not chosen after seeing which ones looked convincing.
    """
    by_record: dict[str, list] = {}
    for label in labels:
        if label.form_class in pc.EXTRACTION_TARGETS:
            by_record.setdefault(label.record_id, []).append(label)
    chosen = sorted(by_record)
    rng = random.Random(seed)
    if len(chosen) > size:
        chosen = sorted(rng.sample(chosen, size))
    return [(record_id, by_record[record_id]) for record_id in chosen]


def write_verification(sample, pages_by_id) -> Path:
    """Render the pages a human has to look at, plus a CSV to record verdicts."""
    import csv

    VERIFY.mkdir(parents=True, exist_ok=True)
    for stale in VERIFY.glob("*.png"):
        stale.unlink()

    rows = []
    for record_id, labels in sample:
        for label in sorted(labels, key=lambda l: (l.file_index, l.page)):
            pdf = pages_by_id.get(label.id)
            if pdf is None:
                continue
            png, _ = render.render_page_png(pdf, label.page, cap=1400)
            (VERIFY / f"{label.id}.png").write_bytes(png)
            rows.append({
                "record_id": record_id, "page_id": label.id,
                "page": label.page, "predicted": label.form_class.value,
                "part": label.part.value if label.part else "",
                "confidence": label.confidence.value,
                "is_it_really": "",
            })

    path = OUT / "verify.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


# ------------------------------------------------------------------- reporting

def report(census, labels, errors, sample, partial=False) -> None:
    print("\n" + "=" * 72)
    print("CENSUS")
    print("=" * 72)
    print(f"  pages classified      {census.total_pages:>6,}")
    print(f"  parse failures        {len(errors):>6,}  "
          f"({len(errors) / max(1, census.total_pages + len(errors)):.1%})")
    print(f"  records               {census.total_records:>6,}")
    print(f"  oversize pages        {census.oversize_pages:>6,}")
    print(f"  extraction-eligible   {census.extraction_eligible_pages:>6,}")

    print("\n  pages by class")
    for cls, n in census.pages_by_class.most_common():
        recs = census.records_by_class[cls]
        print(f"    {cls.value:<20}{n:>6,} pages{recs:>6} records")

    print("\n  confidence")
    for bucket in (pc.Confidence.HIGH, pc.Confidence.MEDIUM, pc.Confidence.LOW):
        n = census.pages_by_confidence.get(bucket, 0)
        print(f"    {bucket.value:<20}{n:>6,}")

    print("\n" + "=" * 72)
    print("THE NUMBER THIS MILESTONE EXISTS TO PRODUCE")
    print("=" * 72)
    have = census.records_with_completion_report
    print(f"  records with a G-1 or W-2: {have} of {census.total_records} "
          f"({have / max(1, census.total_records):.0%})")
    print(f"  OCR floor (formscan, no model): {OCR_FLOOR_RECORDS}")
    print(f"  sufficiency threshold (HANDOFF): {SUFFICIENCY_THRESHOLD}")

    if partial:
        print("\n  Partial run (--limit). The floor and threshold apply to the")
        print("  whole corpus and mean nothing on a slice, so neither is")
        print("  checked here.")
    elif have < OCR_FLOOR_RECORDS:
        print("\n  UNDER THE FLOOR. Bad OCR alone found more records with a")
        print("  completion-report header than the classifier did. Something")
        print("  is wrong with the run, not with the corpus.")
    elif have < SUFFICIENCY_THRESHOLD:
        print("\n  Below the sufficiency threshold. Per HANDOFF, this is the")
        print("  condition for reopening fetch.py.")
    else:
        print("\n  Above the threshold, subject to the check below.")

    print("\n" + "=" * 72)
    print("UPPER CHECK, NOT YET PERFORMED")
    print("=" * 72)
    print(f"  {len(sample)} records sampled at random from the {have} counted,")
    print("  seed 20260830. Thumbnails of the pages that caused each record to")
    print("  be counted are in data/census/verify/, with data/census/verify.csv")
    print("  to record a verdict per page.")
    print()
    print("  The floor above only catches under-counting. Over-counting is the")
    print("  failure that would green-light extraction against records that do")
    print("  not contain a completion report, and no automatic check can catch")
    print("  it. Until these are eyeballed the number above is provisional.")
    for record_id, labels_ in sample:
        ids = ", ".join(f"p{l.page}" for l in sorted(labels_, key=lambda l: l.page))
        print(f"    {record_id}   {ids}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", default="vision_1000",
                    help="winner of the arm competition; see "
                         "docs/modules/classify.md")
    ap.add_argument("--limit", type=int, help="first N pages, for a dry run")
    ap.add_argument("--no-verify-render", action="store_true",
                    help="skip rendering the verification thumbnails")
    args = ap.parse_args()

    render.preflight()
    api = classify.client()
    pages = all_pages()
    if args.limit:
        pages = pages[:args.limit]
    print(f"{len(pages):,} pages, arm {args.arm}")

    doc_hashes, pages_by_id = {}, {}
    for record_id, file_index, page, pdf in pages:
        if pdf not in doc_hashes:
            doc_hashes[pdf] = render.doc_hash(pdf)
        pages_by_id[pc.page_id(record_id, file_index, page)] = pdf

    OUT.mkdir(parents=True, exist_ok=True)
    cache = classify.ResultCache(OUT / f"cache_{args.arm}.jsonl")
    attempts = classify.run_batched(
        api, args.arm, pages, cache=cache, doc_hashes=doc_hashes,
        on_progress=lambda msg: print(f"  {msg}", flush=True))

    labels = [a.label for a in attempts.values() if a.label is not None]
    errors = {page_id: a.error for page_id, a in attempts.items()
              if a.label is None}

    (OUT / f"{args.arm}.jsonl").write_text("".join(
        json.dumps({"page_id": pid,
                    "form_class": a.label.form_class.value if a.label else None,
                    "part": a.label.part.value if a.label and a.label.part else None,
                    "orientation": a.label.orientation.value if a.label else None,
                    "confidence": a.label.confidence.value if a.label else None,
                    "alt_class": a.label.alt_class.value if a.label and a.label.alt_class else None,
                    "oversize": a.label.oversize if a.label else None,
                    "extraction_eligible": a.label.extraction_eligible if a.label else None,
                    "input_tokens": a.input_tokens, "output_tokens": a.output_tokens,
                    "cached": a.cached, "error": a.error}) + "\n"
        for pid, a in sorted(attempts.items())))

    problems = reconcile(pages, labels, errors)
    if problems:
        print("\nRECONCILIATION FAILED")
        for problem in problems:
            print(f"  {problem}")
    else:
        print(f"\nreconciled: {len(pages):,} manifest pages, "
              f"{len(labels):,} labelled, {len(errors):,} errored, none missing")

    census = pc.aggregate(labels)
    sample = verification_sample(labels)
    report(census, labels, errors, sample, partial=bool(args.limit))

    if not args.no_verify_render and sample:
        path = write_verification(sample, pages_by_id)
        print(f"\n  verification sheet: {path}")
        print(f"  thumbnails:         {VERIFY}")

    spend = sum(a.input_tokens * classify.PRICE_IN
                + a.output_tokens * classify.PRICE_OUT
                for a in attempts.values() if not a.cached) / 1e6
    print(f"\n  spent this run: ${spend * classify.BATCH_DISCOUNT:.2f} batched")


if __name__ == "__main__":
    main()
