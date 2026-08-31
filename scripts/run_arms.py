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
from math import comb
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
    rows = [r for r in csv.DictReader(LABELS.open(encoding='utf-8-sig')) if r["form_class"].strip()]
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


def comparable_pages(all_rows, truth) -> set:
    """Pages every arm labelled, and that carry ground truth.

    Arms fail to parse on different pages, so scoring each on whatever it
    managed leaves the headline percentages sitting on different denominators
    and not comparable. The first run had 58, 59 and 57. Parse failures are
    reported separately, as their own number.
    """
    common = set(truth)
    for rows in all_rows.values():
        common &= {r["page_id"] for r in rows if r.get("form_class")}
    return common


def score(rows, truth, pages=None):
    scored = [r for r in rows
              if r["page_id"] in truth and r.get("form_class")
              and (pages is None or r["page_id"] in pages)]
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


def arm_cost(rows) -> tuple[float, int]:
    """Dollars per page at list price, from the tokens this run actually used.

    Measured, not assumed. DEFECTS #9 and classify.md R10: the text arm is the
    cheapest across the corpus and was the most expensive of the three on the
    first page probed.
    """
    priced = [r for r in rows if r.get("input_tokens")]
    if not priced:
        return 0.0, 0
    spend = sum(r["input_tokens"] * classify.PRICE_IN
                + r["output_tokens"] * classify.PRICE_OUT
                for r in priced) / 1e6
    return spend / len(priced), len(priced)


def mcnemar(rows_a, rows_b, truth, pages=None) -> dict:
    """Paired comparison of two arms scored on the same pages.

    An unpaired +/-6pp error bar is the wrong instrument here: both arms see
    identical pages, so what matters is the pages where they disagree. b and c
    are the discordant counts, and under the null they split evenly, which is
    an exact binomial test on b + c trials.
    """
    by_id_a = {r["page_id"]: r for r in rows_a}
    by_id_b = {r["page_id"]: r for r in rows_b}
    b = c = n = 0
    for page_id, row in truth.items():
        if pages is not None and page_id not in pages:
            continue
        ra, rb = by_id_a.get(page_id), by_id_b.get(page_id)
        if not ra or not rb or not ra.get("form_class") or not rb.get("form_class"):
            continue
        n += 1
        actual = row["form_class"].strip()
        a_ok, b_ok = ra["form_class"] == actual, rb["form_class"] == actual
        b += a_ok and not b_ok
        c += b_ok and not a_ok

    discordant = b + c
    if discordant == 0:
        p_value = 1.0
    else:
        tail = max(b, c)
        p_value = min(1.0, 2 * sum(comb(discordant, k)
                                   for k in range(tail, discordant + 1))
                      / 2 ** discordant)
    return {"n": n, "b": b, "c": c, "discordant": discordant,
            "difference": (c - b) / n if n else 0.0, "p_value": p_value}


#: A costlier arm must beat the cheapest by more than this to be preferred.
#: Recorded in docs/modules/classify.md before any arm ran.
MARGIN = 0.05

#: Below this the paired test separates two arms; above it, it does not.
ALPHA = 0.05


def decide(ranked, scores, paired) -> dict:
    """Who wins, and which comparisons could not be settled at this sample size.

    Origin: DEFECTS #13. The first version reset the winner to the cheapest arm
    for any contested comparison, which discarded a different arm's proven win.
    Contested is a statement about one arm and never a veto over another.
    """
    cheapest = ranked[0]
    base = scores[cheapest]["class_accuracy"]

    contested, eligible = [], []
    for arm in ranked[1:]:
        gain = scores[arm]["class_accuracy"] - base
        if gain <= MARGIN:
            continue                       # rule already answers this: cheapest
        if paired[arm]["p_value"] < ALPHA:
            eligible.append((gain, arm))
        else:
            contested.append(arm)

    winner = max(eligible)[1] if eligible else cheapest
    return {"winner": winner, "cheapest": cheapest,
            "contested": contested, "eligible": [a for _, a in eligible]}


def rank_by_cost(all_rows) -> list[str]:
    return sorted(all_rows, key=lambda arm: arm_cost(all_rows[arm])[0])


def report(all_rows, scores, truth):
    print("\n" + "=" * 72)
    print("COST, over the pages actually run")
    print("=" * 72)
    print(f"{'arm':<14}{'pages':>7}{'in tok':>12}{'out':>8}"
          f"{'$/page':>11}{'$ census est':>15}")
    for arm in rank_by_cost(all_rows):
        rows = all_rows[arm]
        tok_in = sum(r["input_tokens"] for r in rows if r.get("input_tokens"))
        tok_out = sum(r["output_tokens"] for r in rows if r.get("output_tokens"))
        per_page, priced = arm_cost(rows)
        print(f"{arm:<14}{len(rows):>7}{tok_in:>12,}{tok_out:>8,}"
              f"{per_page:>11.5f}{per_page * 3689 / 2:>15.2f}")
    print("  ordered cheapest first, by measured cost per page (R10)")
    print("  census estimate is batched, at 50% of list price")

    if not scores:
        if not truth:
            print("\nNo labels in tests/fixtures/labels_stage1.csv, so no "
                  "accuracy. Fill it and re-run; cached pages are not charged "
                  "again.")
        else:
            print(f"\n{len(truth)} pages are labelled, but none of the pages "
                  "run are among them, so there is nothing to score. This is "
                  "what --limit does on a slice that misses the sample.")
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
    print("DECISION, by the rule recorded in docs/modules/classify.md")
    print("  before any arm was run: the cheapest arm wins unless a costlier")
    print("  one beats it by more than 5 percentage points on the labelled set.")
    print("=" * 72)

    ranked = [a for a in rank_by_cost(all_rows) if a in scores]
    pages = comparable_pages(all_rows, truth)
    paired = {arm: mcnemar(all_rows[ranked[0]], all_rows[arm], truth, pages)
              for arm in ranked[1:]}
    verdict = decide(ranked, scores, paired)
    cheapest = verdict["cheapest"]

    print(f"  cheapest arm, measured: {cheapest} "
          f"({arm_cost(all_rows[cheapest])[0]:.5f}/page, "
          f"{scores[cheapest]['class_accuracy']:.1%} on "
          f"{scores[cheapest]['n']} labelled pages)\n")

    for arm in ranked[1:]:
        gain = scores[arm]["class_accuracy"] - scores[cheapest]["class_accuracy"]
        pair = paired[arm]
        print(f"  {arm} vs {cheapest}: {gain:+.1%}")
        print(f"    5pp rule:  {'clears' if gain > MARGIN else 'inside 5pp, a tie'}")
        print(f"    paired:    {pair['discordant']} pages disagree "
              f"({pair['b']} only {cheapest} right, "
              f"{pair['c']} only {arm} right), p={pair['p_value']:.3f}")
        print("    " + ("distinguishable at this sample size"
                        if pair["p_value"] < ALPHA
                        else "NOT distinguishable at this sample size"))
        print()

    for arm in verdict["contested"]:
        pair = paired[arm]
        gain = scores[arm]["class_accuracy"] - scores[cheapest]["class_accuracy"]
        print("  " + "!" * 60)
        print(f"  FLAG: {arm} clears the 5pp threshold at {gain:+.1%}, but the")
        print(f"  paired test cannot separate it from {cheapest} at this sample")
        print(f"  size (p={pair['p_value']:.3f}, only {pair['discordant']} "
              "pages disagree). That gap is")
        print("  inside what this sample can resolve, so it does not win on it.")
        print("  To settle it, enlarge the labelled set; do not eyeball it.")
        print("  " + "!" * 60)
        print()

    print(f"  WINNER: {verdict['winner']}")
    if verdict["winner"] == cheapest:
        print("  Cheapest arm. No costlier arm both cleared 5pp and survived")
        print("  the paired test.")
    else:
        pair = paired[verdict["winner"]]
        print(f"  Beat {cheapest} by "
              f"{scores[verdict['winner']]['class_accuracy'] - scores[cheapest]['class_accuracy']:+.1%} "
              f"at p={pair['p_value']:.3f}, which clears both the 5pp rule and")
        print("  the paired test. The margin is real at this sample size.")
    if verdict["contested"]:
        print(f"  Unsettled at this n: {', '.join(verdict['contested'])}.")


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
    ap.add_argument("--labelled-only", action="store_true",
                    help="run only the hand-labelled pages. Validating a "
                         "prompt change needs the scored pages, not the "
                         "smoke slice, and costs 60 pages instead of 280.")
    args = ap.parse_args()

    render.preflight()
    api = classify.client()
    index = manifest_index()
    truth = ground_truth()
    pages = pages_to_run(index, truth)
    if args.labelled_only:
        pages = [p for p in pages if pc.page_id(p[0], p[1], p[2]) in truth]
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
    shared = comparable_pages(all_rows, truth)
    for arm, rows in all_rows.items():
        result = score(rows, truth, shared)
        if result:
            scores[arm] = result

    print(f"\nscored on {len(shared)} pages every arm labelled, of "
          f"{len(truth)} labelled")
    for arm, rows in all_rows.items():
        errs = sum(1 for r in rows if r.get("error"))
        print(f"  {arm:<14}{errs:>3} parse failures of {len(rows)} pages "
              f"({errs / len(rows):.1%})")

    report(all_rows, scores, truth)
    spot_checks(all_rows)
    print(f"\nper-page results: {OUT}")


if __name__ == "__main__":
    main()
