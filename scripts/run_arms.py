#!/usr/bin/env python3
"""Run the three classifier arms and score them on the hand-labelled pages.

Pages are the union of the stage-1 labelled sample and the smoke slice. The
smoke slice alone has no ground truth, so the competition would have nothing
to score against; the labelled sample alone would not exercise the documents
whose contents are already known from recon.

Selection rule, recorded in docs/modules/classify.md before any arm ran: the
cheapest arm wins unless a costlier arm beats it by more than 5 percentage
points on the labelled set. Anything inside 5pp is a tie and cost decides.

Nothing here runs the census. That is gated on reading these results.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify          # noqa: E402
from pipeline import pageclass as pc   # noqa: E402
from pipeline import render            # noqa: E402

LABELS = ROOT / "tests" / "fixtures" / "labels_stage1.csv"
MANIFEST = ROOT / "data" / "manifest.jsonl"
OUT = ROOT / "data" / "arms"

# Five documents characterised during recon, plus five drawn from the 2014
# imaging wave (118 records, 59% of the corpus, paper vintage unknown).
# Seed 20260830, recorded so the slice is reproducible.
SMOKE_RECORDS = [
    "1501720",   # demo doc: G-1 face p2, its Section III p5, P-4 between
    "1760703",   # three G-1s; completions are a time series per well
    "1493418",   # Form WS-1 rev-1959; no G-1
    "1494070",   # handwritten X-reference card; no G-1
    "1865621",   # 1983 P-4; no G-1
    "1493495", "1494036", "1494686", "1493521", "1497398",
]

# Known from reading the paper during recon. A run that misses these is wrong
# regardless of what it scores on the labelled set.
SPOT_CHECKS = {
    ("1501720", 0, 2): "G-1 face of the demo document",
    ("1501720", 0, 5): "a form page several pages from its face",
}


def manifest_index() -> dict[str, list[dict]]:
    index = {}
    for line in MANIFEST.open():
        if line.strip():
            record = json.loads(line)
            index[record["record_id"]] = record["files"]
    return index


def ground_truth() -> dict[str, dict]:
    if not LABELS.exists():
        return {}
    rows = [r for r in csv.DictReader(LABELS.open()) if r["form_class"].strip()]
    return {r["page_id"]: r for r in rows}


def pages_to_run(index, truth) -> list[tuple[str, int, int, Path]]:
    wanted: set[tuple[str, int, int]] = set()
    for record_id in SMOKE_RECORDS:
        for file_index, entry in enumerate(index[record_id]):
            for page in range(1, (entry.get("pages") or 0) + 1):
                wanted.add((record_id, file_index, page))
    for page_id in truth:
        wanted.add(pc.parse_page_id(page_id))

    out = []
    for record_id, file_index, page in sorted(wanted):
        name = index[record_id][file_index]["name"]
        out.append((record_id, file_index, page,
                    ROOT / "data" / "raw" / record_id / name))
    return out


def run_arm(api, arm, pages, cache) -> list[dict]:
    results = []
    hashes: dict[Path, str] = {}
    for n, (record_id, file_index, page, pdf) in enumerate(pages, 1):
        if pdf not in hashes:
            hashes[pdf] = render.doc_hash(pdf)
        try:
            attempt = classify.classify_page(
                api, arm, pdf, page, record_id=record_id, file_index=file_index,
                cache=cache, doc_hash=hashes[pdf])
        except render.PageNotSingleImage as exc:
            results.append({"page_id": pc.page_id(record_id, file_index, page),
                            "arm": arm, "error": str(exc)})
            continue

        label = attempt.label
        results.append({
            "page_id": pc.page_id(record_id, file_index, page),
            "record_id": record_id, "file_index": file_index, "page": page,
            "arm": arm, "model": classify.MODEL,
            "form_class": label.form_class.value if label else None,
            "part": label.part.value if label and label.part else None,
            "orientation": label.orientation.value if label else None,
            "confidence": label.confidence.value if label else None,
            "alt_class": label.alt_class.value if label and label.alt_class else None,
            "oversize": label.oversize if label else None,
            "extraction_eligible": label.extraction_eligible if label else None,
            "sent_px": list(attempt.sent_px) if attempt.sent_px else None,
            "input_tokens": attempt.input_tokens,
            "output_tokens": attempt.output_tokens,
            "cached": attempt.cached,
            "prompt_hash": classify.PROMPT_HASH,
            "doc_hash": hashes[pdf],
            "error": attempt.error,
        })
        if n % 25 == 0:
            print(f"    {n}/{len(pages)}", flush=True)
    return results


def score(rows, truth):
    scored = [r for r in rows if r["page_id"] in truth and r.get("form_class")]
    if not scored:
        return None
    correct = sum(1 for r in scored
                  if r["form_class"] == truth[r["page_id"]]["form_class"].strip())
    part_rows = [r for r in scored
                 if truth[r["page_id"]]["part"].strip()]
    part_ok = sum(1 for r in part_rows
                  if (r["part"] or "") == truth[r["page_id"]]["part"].strip())
    orient_ok = sum(1 for r in scored
                    if r["orientation"] == truth[r["page_id"]]["orientation"].strip())

    by_bucket = defaultdict(lambda: [0, 0])
    for r in scored:
        bucket = by_bucket[r["confidence"]]
        bucket[1] += 1
        bucket[0] += r["form_class"] == truth[r["page_id"]]["form_class"].strip()

    confusion = Counter()
    for r in scored:
        actual = truth[r["page_id"]]["form_class"].strip()
        if r["form_class"] != actual:
            confusion[(actual, r["form_class"], r["alt_class"])] += 1

    return {
        "n": len(scored),
        "class_accuracy": correct / len(scored),
        "part_accuracy": part_ok / len(part_rows) if part_rows else None,
        "orientation_accuracy": orient_ok / len(scored),
        "by_bucket": dict(by_bucket),
        "confusion": confusion,
        "alt_class_rescues": sum(
            1 for r in scored
            if r["form_class"] != truth[r["page_id"]]["form_class"].strip()
            and r["alt_class"] == truth[r["page_id"]]["form_class"].strip()),
    }


def report(all_rows, scores, truth):
    print("\n" + "=" * 72)
    print("COST, over the pages actually run")
    print("=" * 72)
    print(f"{'arm':<14}{'pages':>7}{'in tok':>12}{'out':>8}"
          f"{'$ this run':>13}{'$ census est':>15}")
    for arm, rows in all_rows.items():
        live = [r for r in rows if not r.get("cached") and r.get("input_tokens")]
        tok_in = sum(r["input_tokens"] for r in rows if r.get("input_tokens"))
        tok_out = sum(r["output_tokens"] for r in rows if r.get("output_tokens"))
        n = len([r for r in rows if r.get("input_tokens")]) or 1
        spend = (tok_in * classify.PRICE_IN + tok_out * classify.PRICE_OUT) / 1e6
        per_page = spend / n
        print(f"{arm:<14}{len(rows):>7}{tok_in:>12,}{tok_out:>8,}"
              f"{spend:>13.3f}{per_page * 3689 / 2:>15.2f}")
    print("  census estimate is batched, at 50% of list price")

    if not scores:
        print("\nNo labelled pages yet, so no accuracy. Fill "
              "tests/fixtures/labels_stage1.csv and re-run; cached pages will "
              "not be charged again.")
        return

    print("\n" + "=" * 72)
    print(f"ACCURACY on {scores[next(iter(scores))]['n']} labelled pages")
    print("=" * 72)
    print(f"{'arm':<14}{'class':>9}{'part':>9}{'orient':>9}{'alt saves':>11}")
    for arm, s in scores.items():
        part = f"{s['part_accuracy']:.1%}" if s["part_accuracy"] is not None else "n/a"
        print(f"{arm:<14}{s['class_accuracy']:>9.1%}{part:>9}"
              f"{s['orientation_accuracy']:>9.1%}{s['alt_class_rescues']:>11}")

    print("\n" + "=" * 72)
    print("ACCURACY PER CONFIDENCE BUCKET")
    print("  A self-reported bucket means nothing until this table gives it")
    print("  a meaning (docs/modules/classify.md R6).")
    print("=" * 72)
    for arm, s in scores.items():
        print(f"  {arm}")
        for bucket in ("high", "medium", "low"):
            if bucket in s["by_bucket"]:
                ok, total = s["by_bucket"][bucket]
                print(f"    {bucket:<8}{ok:>4}/{total:<4} {ok / total:>6.1%}")

    print("\n" + "=" * 72)
    print("CONFUSION, where an arm was wrong (actual -> predicted, 2nd choice)")
    print("=" * 72)
    for arm, s in scores.items():
        print(f"  {arm}")
        if not s["confusion"]:
            print("    none")
        for (actual, predicted, alt), count in s["confusion"].most_common(12):
            flag = "  <- alt was right" if alt == actual else ""
            print(f"    {count:>3}x  {actual} -> {predicted}"
                  f"  (alt: {alt}){flag}")

    print("\n" + "=" * 72)
    print("DECISION, by the rule recorded before the run")
    print("=" * 72)
    order = ["text", "vision_1000", "vision_1568"]      # cheapest first
    ranked = [a for a in order if a in scores]
    cheapest = ranked[0]
    base = scores[cheapest]["class_accuracy"]
    winner, margin = cheapest, 0.0
    for arm in ranked[1:]:
        gain = scores[arm]["class_accuracy"] - base
        verdict = "beats it" if gain > 0.05 else "inside 5pp, a tie"
        print(f"  {arm} vs {cheapest}: {gain:+.1%}  {verdict}")
        if gain > 0.05 and gain > margin:
            winner, margin = arm, gain
    print(f"\n  WINNER: {winner}")
    if winner == cheapest:
        print("  No costlier arm cleared 5pp, so cost decides.")


def spot_checks(all_rows):
    print("\n" + "=" * 72)
    print("SPOT CHECKS, ground truth read off the paper during recon")
    print("=" * 72)
    for (record_id, file_index, page), note in SPOT_CHECKS.items():
        page_id = pc.page_id(record_id, file_index, page)
        print(f"  {page_id}  {note}")
        for arm, rows in all_rows.items():
            row = next((r for r in rows if r["page_id"] == page_id), None)
            if row:
                print(f"    {arm:<14}{row.get('form_class')} / "
                      f"{row.get('part')} / {row.get('orientation')} "
                      f"({row.get('confidence')})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default=",".join(classify.ARMS))
    ap.add_argument("--limit", type=int, help="first N pages, for a dry run")
    args = ap.parse_args()

    render.preflight()
    api = classify.client()
    index = manifest_index()
    truth = ground_truth()
    pages = pages_to_run(index, truth)
    if args.limit:
        pages = pages[:args.limit]

    print(f"{len(pages)} pages: {len(SMOKE_RECORDS)} smoke records "
          f"+ {len(truth)} labelled pages (union)")
    if not truth:
        print("WARNING: no labels filled in, so arms cannot be scored.")

    OUT.mkdir(parents=True, exist_ok=True)
    all_rows, scores = {}, {}
    for arm in args.arms.split(","):
        print(f"\n  arm {arm}")
        cache = classify.ResultCache(OUT / f"cache_{arm}.jsonl")
        rows = run_arm(api, arm, pages, cache)
        all_rows[arm] = rows
        (OUT / f"{arm}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
        result = score(rows, truth)
        if result:
            scores[arm] = result

    report(all_rows, scores, truth)
    spot_checks(all_rows)
    print(f"\nper-page results: {OUT}")


if __name__ == "__main__":
    main()
