#!/usr/bin/env python3
"""Is there a same-sheet signal BELOW the mark-area floor, and is it safe?

Spends nothing. No API calls, no model calls, no fetch.

**Why.** `pipeline/paper.py` confirms 4 of the 16 pairs Alex judged same-sheet
on 2026-09-06, and 15 of those 16 calls cite staple marks, which sit under
`MIN_MARK_AREA`. DEFECTS #53 fixed that floor where it is because bold printed
glyphs are the same size, so the floor cannot be lowered. Anything under it
needs a different discriminator, and this probe measures whether one exists
before a single record is fetched.

**The staple model in the plan is not what the paper supports, and this probe
is how that was found.** "Two marks about 10 mm apart near a corner" fires on 1
of the 8 pairs where a flip beat the control; the others sit 1.6 to 9.2 inches
apart. What carries the signal is small marks generally.

**The discriminators, in the order they cut.** Below the area floor, on the
sheet rather than in the scanner surround, roughly equant, near the paper's own
edge, and with at most one comparable neighbour within a character pitch, which
is what removes printing: glyphs come in runs, in rows and in dotted rules, and
damage does not.

**The statistic is the margin, as everywhere else in this module (R4):** marks
agreeing under a legitimate flip, minus marks agreeing under the best
orientation-preserving control. Marks are matched one at a time and **no rigid
offset is searched**. That is not an oversight. Searching a shared offset was
measured and it lifted the controls exactly as searching rotations did in the
original work (R1): false confirmations went from 0 to 2 of 120 cross-record
and from 3 to 11 of 160 same-file.

**Everything here is development data**, drawn from the 91 development records
of tests/fixtures/paper_record_split.csv, and every constant below was chosen
while looking at it. The rule was chosen after seeing both the positive and the
negative results. It has no held-out support of any kind, exactly like the
ambiguity rule of DEFECTS #55 when it was written.

    --positives   the 16 pairs Alex judged same-sheet, and the 8 he judged not
    --cross       guaranteed-false pairs from two different records
    --samefile    non-adjacent pages of one file: one punch, one staple
    (default)     all three
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper, papermatch, render             # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SPLIT = ROOT / "tests" / "fixtures" / "paper_record_split.csv"
SHEET = ROOT / "tests" / "fixtures" / "paper_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"

#: The detector and every constant live in pipeline/paper.py, frozen there.
#: This probe carried its own copy while the shape of the thing was still
#: being found; a probe that reimplements the mechanism measures the probe.

_CACHE: dict = {}


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def development_records() -> set:
    rows = csv.DictReader(io.StringIO(SPLIT.read_text()))
    return {r["record_id"] for r in rows if r["half"] == "development"}


def small_marks(pdf: Path, page: int) -> list:
    """Cached per page for the run. Detection is ~1.5 s and the negative
    strata score hundreds of pairs over the same pages."""
    key = (str(pdf), page)
    if key not in _CACHE:
        dpi = papermatch.page_dpi(pdf, page)
        image = render.extract_page_image(pdf, page).convert("L")
        _CACHE[key] = paper.small_marks(np.asarray(image) < 128, dpi=dpi)
    return _CACHE[key]


def verdict(pdf_a: Path, page_a: int, pdf_b: Path, page_b: int):
    a, b = small_marks(pdf_a, page_a), small_marks(pdf_b, page_b)
    result = paper.compare_small(a, b)
    return (len(a), len(b), result.agreeing, result.control, result.confirmed)


def pdf_of(recs, record_id, file_index) -> Path:
    return RAW / record_id / recs[record_id]["files"][file_index]["name"]


def judged(recs):
    """The 2026-09-06 sitting, which is the only human truth that exists."""
    sealed = json.loads(VERDICTS.read_text())["verdicts"]
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    sheet = {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}
    for item in sorted(sealed):
        call = (sheet[item]["verdict"] or "").strip().lower()
        if call in ("same-sheet", "not-same-sheet"):
            yield item, call, sealed[item]


def run_positives(recs) -> None:
    for want in ("same-sheet", "not-same-sheet"):
        print(f"\npairs Alex judged {want}")
        fired = total = 0
        for item, call, row in judged(recs):
            if call != want:
                continue
            pdf = pdf_of(recs, row["record_id"], row["file_index"])
            a, b = row["pages"]
            na, nb, flip, control, fires = verdict(pdf, a, pdf, b)
            total += 1
            fired += fires
            print(f"  {item} {row['record_id']}-{row['file_index']} p{a}+p{b}"
                  f"  marks {na:3d}/{nb:3d}  flip {flip:2d} control {control:2d}"
                  f"{'  FIRES' if fires else ''}"
                  f"{'   [paper.compare confirms]' if row['confirmed'] else ''}")
        print(f"  fired on {fired} of {total}")


def run_cross(recs, development, count=120, seed=20260906) -> None:
    print(f"\nguaranteed-false: two different records, different leases")
    rng = random.Random(seed)
    pool = [(r, pdf_of(recs, r, 0), recs[r]["files"][0].get("pages") or 2)
            for r in sorted(development) if r in recs]
    fired = total = 0
    for _ in range(count):
        (ra, pa, na), (rb, pb, nb) = rng.sample(pool, 2)
        page_a = rng.randint(1, min(na, 20))
        page_b = rng.randint(1, min(nb, 20))
        try:
            ca, cb, flip, control, fires = verdict(pa, page_a, pb, page_b)
        except Exception:                                   # noqa: BLE001
            continue
        total += 1
        fired += fires
        if fires:
            print(f"  FIRES {ra}-0 p{page_a} + {rb}-0 p{page_b}"
                  f"  marks {ca}/{cb} flip {flip} control {control}")
    print(f"  false confirmations: {fired} of {total}")


def run_samefile(recs, development, per_record=8, seed=20260906) -> None:
    print(f"\nhard negative: non-adjacent pages of ONE file, one punch stroke")
    print("  NOT guaranteed false. The protocol's own rule is that Alex")
    print("  adjudicates a confirmed pair here; I do not.")
    rng = random.Random(seed)
    fired = total = 0
    for record_id in sorted(development):
        if record_id not in recs:
            continue
        pages = recs[record_id]["files"][0].get("pages") or 0
        if pages < 6:
            continue
        pdf = pdf_of(recs, record_id, 0)
        tried = 0
        while tried < per_record:
            a, b = rng.randint(1, pages), rng.randint(1, pages)
            if abs(a - b) < 3:
                continue
            tried += 1
            try:
                ca, cb, flip, control, fires = verdict(pdf, a, pdf, b)
            except Exception:                               # noqa: BLE001
                continue
            total += 1
            fired += fires
            if fires:
                print(f"  FIRES {record_id}-0 p{a}+p{b}  marks {ca}/{cb} "
                      f"flip {flip} control {control}   -> for adjudication")
    print(f"  fired on {fired} of {total}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--positives", action="store_true")
    ap.add_argument("--cross", action="store_true")
    ap.add_argument("--samefile", action="store_true")
    ap.add_argument("--records", type=int, default=0,
                    help="cap records used for the negative strata, for a "
                         "quick run")
    ap.add_argument("--held-out", action="store_true",
                    help="draw the negative strata from the 111 held-out "
                         "records instead of the 91 development ones. This is "
                         "the run docs/labeling-protocol-staple.md "
                         "pre-registers, and it is run ONCE.")
    ap.add_argument("--pairs", type=int, default=120,
                    help="cross-record pairs to score")
    ap.add_argument("--whole-page", action="store_true",
                    help="ignore SMALL_EDGE_IN and read the whole sheet. "
                         "Measured 2026-09-07 and it is worse: one more true "
                         "confirmation for six more false ones, because the "
                         "periphery holds about 6 candidates a page and the "
                         "whole page about 45 (DEFECTS #64).")
    args = ap.parse_args()
    everything = not (args.positives or args.cross or args.samefile)

    render.preflight()
    if args.whole_page:
        # Not a constant change: the frozen value stands and this switch exists
        # to re-measure the comparison in DEFECTS #64, not to ship a different
        # one. A run under it may not be quoted beside a frozen-config result.
        paper.SMALL_EDGE_IN = 99.0
        print("WHOLE PAGE: SMALL_EDGE_IN overridden for this run only. "
              "Measured worse (DEFECTS #64); not a shippable configuration.")
    recs = records()
    rows = list(csv.DictReader(io.StringIO(SPLIT.read_text())))
    half = "held_out" if args.held_out else "development"
    pool = {r["record_id"] for r in rows if r["half"] == half}
    everything_in_half = len(pool)
    if args.records:
        pool = set(sorted(pool)[:args.records])
    print(f"{half} records in use: {len(pool)} of {everything_in_half}"
          f"  (tests/fixtures/paper_record_split.csv)")
    if args.held_out:
        print("PRE-REGISTERED RUN: docs/labeling-protocol-staple.md, frozen at "
              "1a01829.\n  The rule is a 95% upper bound below 2% on the "
              "cross-record rate.")
    development = pool
    print(f"constants, frozen in pipeline/paper.py: area "
          f"{[round(v, 6) for v in paper.SMALL_AREA_IN2]} in2, aspect "
          f"{paper.SMALL_MAX_ASPECT}, edge {paper.SMALL_EDGE_IN} in, run "
          f"pitch {paper.SMALL_RUN_PITCH_IN} in, tolerance "
          f"{paper.SMALL_TOLERANCE}, minimum agreeing "
          f"{paper.MIN_SMALL_AGREEING}")

    if everything or args.positives:
        run_positives(recs)
    if everything or args.cross:
        run_cross(recs, development, count=args.pairs)
    if everything or args.samefile:
        run_samefile(recs, development)


if __name__ == "__main__":
    main()
