#!/usr/bin/env python3
"""What an extraction batch actually weighs, and what the corpus run costs.

Makes no API calls and spends nothing. Two questions, both answered from
measurement rather than from the ceilings in the documentation:

  1. How many bytes does one extraction request serialise to? A batch is
     capped at 256 MB, and an extraction request carries every page of a
     document as a 1568 px PNG. The chunk size in pipeline/extractor.py has to
     come from this number, not from the classifier's, whose requests are one
     page at 1000 px.

  2. What does the run cost, batched and unbatched? Priced from the token
     counts the 20-document smoke run actually recorded, not from a guess.

Run it before spending anything:  .venv/bin/python scripts/estimate_batch.py
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import extractor                    # noqa: E402
from pipeline import pageclass as pc              # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"

SEED = 20260905


def faces() -> list[str]:
    """Every page the census calls the face of a completion report."""
    out = []
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        if (not row.get("error") and row.get("form_class") in ("g1", "w2")
                and row.get("part") == "face"):
            out.append(row["page_id"])
    return sorted(out)


def pdf_of(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            name = json.loads(line)["files"][file_index]["name"]
            return RAW / record_id / name
    raise KeyError(record_id)


def measure(page_ids) -> list[int]:
    """Serialised bytes of a one-page extraction request, per page."""
    sizes = []
    for page_id in page_ids:
        record, index, page = pc.parse_page_id(page_id)
        request = extractor.build_request(
            pdf_of(record, index), (page,), custom_id=page_id)
        sizes.append(len(json.dumps(request)))
    return sizes


def tokens_from_smoke() -> dict:
    """Input and output tokens per document, from the smoke run, by page count.

    Split by page count rather than pooled, because the two differ by a lot: a
    two-page document sends a second image and comes back with the casing and
    completion tables the face does not carry. Pooling them prices whatever
    mix the smoke draw happened to have, which is not the corpus mix.

    Only the documents that came back whole. A truncation is not what a
    completed document costs.
    """
    rows = [json.loads(l) for l in SMOKE.open() if l.strip()]
    kept = [r for r in rows if not r.get("error") and r.get("input_tokens")]
    by: dict[int, list] = {}
    for row in kept:
        by.setdefault(len(row["pages"]), []).append(row)
    return {n: {"n": len(group),
                "in": statistics.mean(r["input_tokens"] for r in group),
                "out": statistics.mean(r["output_tokens"] for r in group),
                "out_max": max(r["output_tokens"] for r in group)}
            for n, group in sorted(by.items())}


def corpus_mix() -> dict | None:
    """Documents by page count, from the reassembly run, when it has one."""
    path = ROOT / "data" / "extract" / "reassemble.jsonl"
    if not path.exists():
        return None
    counts: dict[int, int] = {}
    for line in path.open():
        if not line.strip():
            continue
        row = json.loads(line)
        pages = row.get("pages")
        if not pages:
            continue
        counts[len(pages)] = counts.get(len(pages), 0) + 1
    return counts or None


def price(tokens: dict, pages: int) -> float:
    """USD for one document of this page count, at the standard rate.

    Falls back to the nearest measured page count. Nothing in the smoke run
    ran to three pages, so a three-page document is priced as a two-page one
    and that is an under-estimate, said out loud rather than hidden.
    """
    if not tokens:
        raise RuntimeError("no completed smoke documents to price from")
    nearest = min(tokens, key=lambda n: abs(n - pages))
    row = tokens[nearest]
    return (row["in"] * extractor.PRICE_IN
            + row["out"] * extractor.PRICE_OUT) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=12,
                    help="how many real pages to weigh")
    ap.add_argument("--documents", type=int, default=None,
                    help="documents in the run being priced "
                         "(default: every predicted completion face)")
    args = ap.parse_args()

    frame = faces()
    rng = random.Random(SEED)
    drawn = sorted(rng.sample(frame, min(args.sample, len(frame))))

    print(f"frame: {len(frame)} predicted completion faces")
    print(f"weighing {len(drawn)} one-page requests, seed {SEED}\n")

    sizes = measure(drawn)
    mean, largest = statistics.mean(sizes), max(sizes)
    print(f"  request bytes   mean {mean/1e6:.2f} MB   "
          f"max {largest/1e6:.2f} MB   min {min(sizes)/1e6:.2f} MB")
    print("  (one page. A two-page document is roughly twice this.)\n")

    cap = extractor.BATCH_MAX_BYTES
    print(f"  batch byte ceiling in use: {cap/1e6:.0f} MB")
    print(f"  one-page documents per chunk at the mean:   "
          f"{int(cap // mean)}")
    print(f"  two-page documents per chunk at the mean:   "
          f"{int(cap // (2 * mean))}")
    print(f"  request ceiling in use: {extractor.BATCH_MAX_REQUESTS}\n")

    tokens = tokens_from_smoke()
    print("measured on the smoke run, by page count:")
    for pages, row in tokens.items():
        print(f"  {pages}-page  n={row['n']:2d}   in {row['in']:>7,.0f}   "
              f"out {row['out']:>7,.0f}   worst out {row['out_max']:>7,}   "
              f"${price(tokens, pages):.4f}/doc")
    worst = max(r["out_max"] for r in tokens.values())
    print(f"\n  max_tokens is {extractor.MAX_TOKENS:,} and the worst document "
          f"measured used {worst:,} output tokens.")
    print(f"  That is {extractor.MAX_TOKENS / worst:.2f}x headroom over a "
          f"sample of {sum(r['n'] for r in tokens.values())}. A document that "
          f"hits the cap")
    print("  is refused, not cached, and costs full price for nothing.\n")

    mix = corpus_mix()
    if args.documents is not None:
        mix = {1: args.documents}
        source = f"{args.documents} one-page documents, as asked"
    elif mix:
        source = (f"the reassembly run: "
                  + ", ".join(f"{c} x {p}-page" for p, c in sorted(mix.items())))
    else:
        mix = {1: len(frame)}
        source = (f"no reassembly output on disk, so {len(frame)} faces "
                  "priced as one page each, which is a floor")

    print(f"pricing {sum(mix.values())} documents from {source}:")
    standard = sum(count * price(tokens, pages)
                   for pages, count in mix.items())
    batched = standard * extractor.BATCH_DISCOUNT
    print(f"  standard  ${standard:.2f}")
    print(f"  batched   ${batched:.2f}")
    print(f"  saving    ${standard - batched:.2f}")


if __name__ == "__main__":
    main()
