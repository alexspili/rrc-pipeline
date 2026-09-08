#!/usr/bin/env python3
"""The stage-five Textract read: G-1/W-2 corpus pages, once, cached forever.

Pre-registered in docs/labeling-protocol-extract.md under "Box grading,
stage five". Build time is not runtime: this script is the only file in the
repo that imports boto3, the responses it caches feed template building on
the developer's machine, and nothing that ships calls AWS.

Three modes, and the default sends nothing:

  textract_read.py                 dry run: page list, count, price, misses
  textract_read.py --probe        ONE page, shape-verified (standing rule 2)
  textract_read.py --send         the read; requires an explicit go first

The page population is every page of the g1/w2 documents in the corpus run,
EXCEPT record 1493608's. That is the graded document; excluding it from the
read entirely means no template can leak its geometry, rather than trusting
a downstream filter to hold.

Caching: responses land at data/textract/<sha256[:16]>.json, keyed by the
hash of the exact PNG bytes sent, with an index row per page in
data/textract/index.jsonl. A page whose hash is already cached is never
re-sent, whatever mode asked for it (CLAUDE.md rule 7's shape, applied to a
second vendor).

Images are the page's embedded scan at native resolution, grayscale PNG. No
downscale: Textract is priced per page, not per pixel, and the model-image
cap exists for token cost, which does not apply here. A page over the
documented sync limits (10 MB, 10,000 px on a side) is refused and reported,
never silently shrunk, because a shrunk page would put its words in a
different coordinate space than its siblings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                        # noqa: E402
from pipeline import textractwords as tw           # noqa: E402
from pipeline.textlayer import norm, page_words    # noqa: E402

CORPUS = ROOT / "data" / "extract" / "corpus.jsonl"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "textract"
INDEX = OUT / "index.jsonl"

#: Sealed, same reason as scripts/build_template.py: the graded document
#: never touches Textract at all.
EXCLUDED_RECORDS = frozenset({"1493608"})

#: The bounded probe's page: the existing rev7566 seed face.
PROBE_PAGE = ("1494690", 0, 9)

REGION = "us-east-2"
PRICE_PER_PAGE = 1.50 / 1000
MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 10_000
PACE_SECONDS = 0.25


def manifest() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def population() -> list[tuple[str, int, int]]:
    """(record_id, file_index, page) for every g1/w2 corpus page, deduped,
    in a stable order, with the sealed record excluded."""
    seen, out = set(), []
    for line in CORPUS.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        if doc.get("form_class") not in ("g1", "w2"):
            continue
        record_id, file_index = doc["page_id"].rsplit("-", 2)[:2]
        if record_id in EXCLUDED_RECORDS:
            continue
        for page in doc["pages"]:
            key = (record_id, int(file_index), int(page))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return sorted(out)


def page_png(records: dict, record_id: str, file_index: int,
             page: int) -> bytes:
    pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
    img = render.extract_page_image(pdf, page)
    if img.width > MAX_SIDE or img.height > MAX_SIDE:
        raise ValueError(f"{record_id}-{file_index} p{page}: "
                         f"{img.width}x{img.height} exceeds {MAX_SIDE}px")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError(f"{record_id}-{file_index} p{page}: "
                         f"{len(data)} bytes exceeds the sync limit")
    return data


def cached_hashes() -> set[str]:
    if not INDEX.exists():
        return set()
    return {json.loads(l)["sha256"] for l in INDEX.open() if l.strip()}


def send_page(client, records: dict, key: tuple[str, int, int],
              known: set[str]) -> str:
    """Send one page unless its bytes are already cached. Returns the
    outcome for the run report."""
    record_id, file_index, page = key
    data = page_png(records, record_id, file_index, page)
    digest = hashlib.sha256(data).hexdigest()
    if digest in known:
        return "cached"
    response = client.detect_document_text(Document={"Bytes": data})
    tw.words_from_response(response)      # shape-verify before caching
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{digest[:16]}.json").write_text(json.dumps(response))
    with INDEX.open("a") as fh:
        fh.write(json.dumps({
            "record_id": record_id, "file_index": file_index, "page": page,
            "sha256": digest, "bytes": len(data)}) + "\n")
    known.add(digest)
    time.sleep(PACE_SECONDS)
    return "sent"


def client():
    import boto3
    return boto3.client("textract", region_name=REGION)


def probe(records: dict) -> None:
    """One page, and every shape check the protocol names, printed."""
    record_id, file_index, page = PROBE_PAGE
    outcome = send_page(client(), records, PROBE_PAGE, cached_hashes())
    digest = next(json.loads(l)["sha256"] for l in INDEX.open()
                  if json.loads(l)["record_id"] == record_id
                  and json.loads(l)["page"] == page)
    response = json.loads((OUT / f"{digest[:16]}.json").read_text())

    kinds = Counter(b.get("BlockType") for b in response["Blocks"])
    words = tw.words_only(response)
    pdf = (RAW / record_id
           / records[record_id]["files"][file_index]["name"])
    embedded = page_words(pdf, page)

    print(f"PROBE {record_id}-{file_index} p{page} ({outcome})")
    print(f"  DocumentMetadata.Pages = "
          f"{response['DocumentMetadata']['Pages']}")
    print(f"  block types: {dict(kinds)}")
    print(f"  WORD blocks parse clean: {len(words)} words, every ratio in "
          f"[0, 1] (the parser raises otherwise)")
    print(f"  embedded layer on the same page: {len(embedded)} words")

    t_unique = {norm(w[4]): w for w in words
                if len(norm(w[4])) >= 4}
    counts = Counter(norm(w[4]) for w in words if len(norm(w[4])) >= 4)
    t_unique = {t: w for t, w in t_unique.items() if counts[t] == 1}
    e_counts = Counter(norm(w[4]) for w in embedded if len(norm(w[4])) >= 4)
    e_unique = {norm(w[4]): w for w in embedded
                if e_counts[norm(w[4])] == 1 and len(norm(w[4])) >= 4}
    shared = sorted(set(t_unique) & set(e_unique))
    distances = []
    for token in shared:
        a, b = t_unique[token], e_unique[token]
        distances.append((((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) ** 2
                          + ((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) ** 2)
                         ** 0.5)
    if distances:
        print(f"  positional agreement on {len(shared)} shared unique "
              f"tokens: median {statistics.median(distances):.4f}, "
              f"max {max(distances):.4f} page-fractions")
        print("  (the protocol expects well under 0.01; anything else "
              "means the coordinate spaces do not align)")
    else:
        print("  NO shared unique tokens: alignment unverified, stop here")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="send the ONE bounded-probe page and verify shape")
    ap.add_argument("--send", action="store_true",
                    help="send the full read (gated on an explicit go)")
    args = ap.parse_args()

    records = manifest()
    if args.probe:
        probe(records)
        return

    pages = population()
    known = cached_hashes()
    if not args.send:
        # the dry run prices by page count; rendering and hashing all 230
        # PNGs here would just predict what --send discovers anyway
        by_record = len({r for r, _, _ in pages})
        print(f"DRY RUN: {len(pages)} pages across {by_record} records "
              f"(g1/w2 corpus documents, {sorted(EXCLUDED_RECORDS)} "
              f"excluded)")
        print(f"  price at ${PRICE_PER_PAGE * 1000:.2f}/1k: "
              f"${len(pages) * PRICE_PER_PAGE:.2f}")
        print(f"  responses already cached: {len(known)}")
        print("  nothing sent. --probe for the bounded probe, --send after "
              "the go.")
        return

    sent = skipped = failed = 0
    textract = client()
    for key in pages:
        try:
            outcome = send_page(textract, records, key, known)
        except ValueError as err:
            print(f"  refused: {err}")
            failed += 1
            continue
        if outcome == "sent":
            sent += 1
        else:
            skipped += 1
    print(f"READ COMPLETE: {sent} sent (${sent * PRICE_PER_PAGE:.2f}), "
          f"{skipped} already cached, {failed} refused")


if __name__ == "__main__":
    main()
