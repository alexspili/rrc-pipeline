#!/usr/bin/env python3
"""The stage-six AnalyzeDocument read: Forms and Tables on the fuel pages.

Pre-registered in docs/labeling-protocol-extract.md, "Box grading, stage
six". Same transport discipline as scripts/textract_read.py: the default
sends nothing, --probe sends ONE page (standing rule 2), --send is gated
on an explicit go, and a paid response is cached before it is judged
(DEFECTS #76).

  textract_analyze.py              dry run: page list, count, price
  textract_analyze.py --probe     ONE page, shape-verified
  textract_analyze.py --send      the batch; requires the go first

The page population is the union of the committed stage-five templates'
fuel pages, so the seal of DEFECTS #78 is inherited from the build that
chose them; an assertion re-checks it anyway. Responses land under
data/textract/analyze/ keyed by the hash of the exact PNG bytes sent.
Forms responses carry filled value text, which is why the cache lives
under git-ignored data/ and nothing here prints value text.
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

from pipeline import textractforms as tf           # noqa: E402
from scripts.textract_read import (                # noqa: E402
    EXCLUDED_RECORDS, PROBE_PAGE, REGION, manifest, page_png)

TEMPLATES = ROOT / "pipeline" / "templates"
OUT = ROOT / "data" / "textract" / "analyze"
INDEX = OUT / "index.jsonl"

#: Documented AnalyzeDocument price for FORMS plus TABLES, per page. The
#: dry run quotes with this; the run report prints pages sent so the
#: actual lands beside it.
PRICE_PER_PAGE = 65.00 / 1000
FEATURES = ["FORMS", "TABLES"]
PACE_SECONDS = 0.5


def population() -> list[tuple[str, int, int]]:
    """The committed templates' fuel pages, deduped, stable order."""
    seen = set()
    for path in sorted(TEMPLATES.glob("*.json")):
        for page_id in json.loads(path.read_text())["built_from"]:
            record_id, file_index, page = page_id.rsplit("-", 2)
            seen.add((record_id, int(file_index), int(page)))
    assert not {r for r, _, _ in seen} & EXCLUDED_RECORDS, \
        "a sealed record reached the analyze population (DEFECTS #78)"
    return sorted(seen)


def cached_hashes() -> set[str]:
    if not INDEX.exists():
        return set()
    return {json.loads(l)["sha256"] for l in INDEX.open() if l.strip()}


def send_page(client, records, key, known) -> str:
    record_id, file_index, page = key
    data = page_png(records, record_id, file_index, page)
    digest = hashlib.sha256(data).hexdigest()
    if digest in known:
        return "cached"
    response = client.analyze_document(Document={"Bytes": data},
                                       FeatureTypes=FEATURES)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{digest[:16]}.json").write_text(json.dumps(response))
    with INDEX.open("a") as fh:
        fh.write(json.dumps({
            "record_id": record_id, "file_index": file_index, "page": page,
            "sha256": digest, "bytes": len(data),
            "features": FEATURES}) + "\n")
    known.add(digest)
    time.sleep(PACE_SECONDS)
    try:
        tf.key_values(response)
        tf.tables(response)
    except tf.TextractShape as err:
        raise tf.TextractShape(
            f"{record_id}-{file_index} p{page}: {err}") from err
    return "sent"


def client():
    import boto3
    return boto3.client("textract", region_name=REGION)


def probe(records) -> None:
    record_id, file_index, page = PROBE_PAGE
    outcome = send_page(client(), records, PROBE_PAGE, cached_hashes())
    digest = next(json.loads(l)["sha256"] for l in INDEX.open()
                  if json.loads(l)["record_id"] == record_id
                  and json.loads(l)["page"] == page)
    response = json.loads((OUT / f"{digest[:16]}.json").read_text())

    kinds = Counter(b.get("BlockType") for b in response["Blocks"])
    pairs = tf.key_values(response)
    grids = tf.tables(response)

    print(f"PROBE AnalyzeDocument {record_id}-{file_index} p{page} "
          f"({outcome}, features {FEATURES})")
    print(f"  block types: {dict(kinds)}")
    print(f"  key-value pairs parse clean: {len(pairs)}, "
          f"{sum(1 for p in pairs if p.value_box is not None)} with a "
          "linked value box")
    if pairs:
        widths = sorted(p.key_box[2] - p.key_box[0] for p in pairs)
        print(f"  key box widths: median {widths[len(widths) // 2]:.3f}")
        print("  key texts (printed labels only, value text stays in the "
              "cache):")
        for pair in pairs[:20]:
            print(f"    {pair.key_text[:60]!r}")
    print(f"  tables: {len(grids)}, grids "
          f"{[(t.rows, max((c.column for c in t.cells), default=0)) for t in grids]}")
    if grids:
        heights = [c.box[3] - c.box[1] for t in grids for c in t.cells]
        print(f"  cell heights: median {statistics.median(heights):.4f} "
              "(the equal-band rule this would replace ran to 0.075)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="send the ONE bounded-probe page and verify shape")
    ap.add_argument("--send", action="store_true",
                    help="send the batch (gated on an explicit go)")
    args = ap.parse_args()

    records = manifest()
    if args.probe:
        probe(records)
        return

    pages = population()
    known = cached_hashes()
    if not args.send:
        by_record = len({r for r, _, _ in pages})
        print(f"DRY RUN: {len(pages)} fuel pages across {by_record} "
              "records (union of committed templates' built_from)")
        print(f"  price at ${PRICE_PER_PAGE * 1000:.2f}/1k: "
              f"${len(pages) * PRICE_PER_PAGE:.2f}")
        print(f"  responses already cached: {len(known)}")
        print("  nothing sent. --probe for the bounded probe, --send "
              "after the go.")
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
