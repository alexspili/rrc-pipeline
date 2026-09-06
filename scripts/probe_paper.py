#!/usr/bin/env python3
"""Development measurement for pipeline/paper.py, and where the threshold comes from.

Spends nothing. No API calls.

**What it must not do is spend the held-out frame.** 53 fresh same-family
adjacent pairs exist across 38 records, and those are the only pairs that can
grade this mechanism. So the threshold is chosen from:

  negatives  drawn only from records that hold NO fresh pair, in unlimited
             numbers, because a pair of pages that cannot be one sheet costs
             nothing to generate

  positives  only the two records whose marks have already been inspected by
             eye, 1493608 and 1495414, which are burned already

That is enough. A threshold is a number that separates two distributions, the
negative distribution is where the risk lives, and it is free. The positives
are here to show the bar is attainable, not to set it.

**Three negative strata**, reported separately because they are not equally
hard:

  stack      two pages of one file, punched in the same stroke. The hardest
             negatives that exist: on the raw correlation these reach 0.53 to
             0.57, as high as a true pair.
  file       two files of one record: same well, same district office.
  record     two different records, different leases.

Run:  .venv/bin/python scripts/probe_paper.py
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper                          # noqa: E402
from pipeline import pageclass as pc                # noqa: E402
from pipeline import papermatch                     # noqa: E402
from pipeline import render                         # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
CACHE = ROOT / "data" / "cache" / "paper"
OUT = ROOT / "data" / "probe"

#: Records whose marks have been looked at by eye. Burned for this mechanism,
#: and the only records burned for it: knowing that a record's operator name
#: repeats across filings says nothing about its punch holes.
INSPECTED = ("1493608", "1495414", "1774674")

#: Same-sheet pairs confirmed from the paper by eye, both already burned.
KNOWN_TRUE = [("1493608", 0, 5, 6), ("1495414", 0, 6, 7)]

SEED = 20260906
SECTIONS = {"sec_ii", "sec_iii", "continuation"}


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def pdf_of(recs, record_id: str, file_index: int) -> Path:
    return RAW / record_id / recs[record_id]["files"][file_index]["name"]


def census():
    out = {}
    for line in CENSUS.open():
        if line.strip():
            row = json.loads(line)
            out[row["page_id"]] = row
    return out


def pages_by_file(rows):
    out = defaultdict(dict)
    for page_id, row in rows.items():
        record_id, file_index, page = pc.parse_page_id(page_id)
        out[(record_id, file_index)][page] = row
    return out


def held_out_records(by_file) -> set:
    """Records holding a fresh same-family adjacent pair. Off limits here."""
    out = set()
    for (record_id, file_index), pages in by_file.items():
        if record_id in INSPECTED:
            continue
        for page, row in pages.items():
            if row.get("error") or row.get("form_class") not in ("g1", "w2"):
                continue
            if row.get("part") != "face":
                continue
            nxt = pages.get(page + 1)
            if (nxt and not nxt.get("error")
                    and nxt.get("part") in SECTIONS
                    and nxt.get("form_class") == row.get("form_class")):
                out.add(record_id)
    return out


def pair_label(ra, fa, pa, rb, fb, pb) -> str:
    """Both sides of a pair, always.

    DEFECTS #54: this used to print only the first record, so a cross-record
    pair read as two adjacent pages of one file and the second record was
    written down nowhere. The one result that mattered was the one that could
    not be looked at.
    """
    if (ra, fa) == (rb, fb):
        return f"{ra}-{fa} p{pa}+p{pb}"
    return f"{ra}-{fa} p{pa} + {rb}-{fb} p{pb}"


def false_positive_bound(count: int, scored: int) -> str:
    """What this many events in this many trials actually licenses.

    Derived from the measured count. DEFECTS #54: the sentence used to say
    "Zero of N" unconditionally, and printed it two lines below a line
    reporting one.
    """
    if not scored:
        return "no scoreable negatives, so there is no bound to state."
    if count == 0:
        return (f"Zero of {scored} licenses a false-positive rate below "
                f"{3.0 / scored:.2%} at 95% (rule of three).")
    # Upper end of a one-sided 95% interval, near enough for a report.
    upper = (count + 1.96 * (count ** 0.5) + 1.5) / scored
    return (f"{count} of {scored} is a false-positive rate of "
            f"{count / scored:.2%}, upper 95% bound about {upper:.2%}. "
            f"Not zero, and not to be reported as zero.")


def scoreable(pages, needed: int = paper.MIN_MARKS_AGREEING) -> bool:
    """Does this page carry enough marks to say anything at all?

    Negatives are screened exactly as the held-out positives will be. A pair
    the mechanism cannot score is not evidence that it does not produce false
    positives, and counting it as one would inflate apparent safety by
    diluting the rate with pairs that could never confirm.
    """
    return len(pages) >= needed


def negatives(by_file, allowed, rng, per_stratum: int, cap_per_record: int):
    """Pairs that cannot be two sides of one sheet, by three constructions."""
    files = {k: v for k, v in by_file.items() if k[0] in allowed}
    out = defaultdict(list)

    # stack: two non-adjacent pages of one file, punched in one stroke
    seen = defaultdict(int)
    keys = sorted(files)
    rng.shuffle(keys)
    for key in keys:
        pages = sorted(files[key])
        if len(pages) < 4 or seen[key[0]] >= cap_per_record:
            continue
        for _ in range(3):
            a, b = rng.sample(pages, 2)
            if abs(a - b) < 2:
                continue
            out["stack"].append((key[0], key[1], a, key[0], key[1], b))
            seen[key[0]] += 1
            if len(out["stack"]) >= per_stratum:
                break
        if len(out["stack"]) >= per_stratum:
            break

    # file: two files of one record
    by_record = defaultdict(list)
    for (record_id, file_index) in files:
        by_record[record_id].append(file_index)
    multi = [r for r, f in by_record.items() if len(f) > 1]
    rng.shuffle(multi)
    for record_id in multi:
        fa, fb = rng.sample(by_record[record_id], 2)
        pa, pb = sorted(files[(record_id, fa)]), sorted(files[(record_id, fb)])
        for _ in range(min(cap_per_record, 4)):
            out["file"].append((record_id, fa, rng.choice(pa),
                                record_id, fb, rng.choice(pb)))
            if len(out["file"]) >= per_stratum:
                break
        if len(out["file"]) >= per_stratum:
            break

    # record: two different records with different leases
    recs = records()
    lease = {r: (recs[r].get("meta") or {}).get("lease_name", "") for r in allowed}
    pool = sorted(allowed)
    while len(out["record"]) < per_stratum and len(pool) > 1:
        ra, rb = rng.sample(pool, 2)
        if lease.get(ra) and lease.get(ra) == lease.get(rb):
            continue
        fa = rng.choice([k[1] for k in files if k[0] == ra])
        fb = rng.choice([k[1] for k in files if k[0] == rb])
        out["record"].append((ra, fa, rng.choice(sorted(files[(ra, fa)])),
                              rb, fb, rng.choice(sorted(files[(rb, fb)]))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-stratum", type=int, default=250)
    ap.add_argument("--cap-per-record", type=int, default=10)
    args = ap.parse_args()

    render.preflight()
    recs = records()
    by_file = pages_by_file(census())
    reserved = held_out_records(by_file)
    allowed = {k[0] for k in by_file} - reserved - set(INSPECTED)

    print(f"records in the corpus            : {len({k[0] for k in by_file})}")
    print(f"  reserved, hold a fresh pair    : {len(reserved)}")
    print(f"  marks already inspected by eye : {len(INSPECTED)}")
    print(f"  usable for development         : {len(allowed)}\n")

    cache = papermatch.MarkCache(CACHE)
    hashes: dict = {}

    def verdict(ra, fa, pa, rb, fb, pb):
        one, two = pdf_of(recs, ra, fa), pdf_of(recs, rb, fb)
        for path in (one, two):
            hashes.setdefault(path, render.doc_hash(path))
        a = papermatch.page_marks(one, pa, cache, hashes[one])
        b = papermatch.page_marks(two, pb, cache, hashes[two])
        return paper.compare(a, b), a, b

    def margins_of(pairs, label):
        """Every pair's margins, and how many could not be scored at all.

        A pair with fewer than MIN_MARKS_AGREEING marks on either page is
        counted as unscoreable rather than as a pass. It is not evidence about
        false positives, and folding it in would inflate safety by dilution.
        """
        rows, unscoreable, failed = [], 0, 0
        for n, (ra, fa, pa, rb, fb, pb) in enumerate(pairs, 1):
            try:
                v, a, b = verdict(ra, fa, pa, rb, fb, pb)
            except Exception:                           # noqa: BLE001
                failed += 1
                continue
            if not (scoreable(a) and scoreable(b)):
                unscoreable += 1
                continue
            ranked = sorted((m for m in v.margins), reverse=True)
            rows.append((ranked[0] if ranked else float("nan"), ranked,
                         v.marks_agreeing,
                         pair_label(ra, fa, pa, rb, fb, pb), v.confirmed))
            if n % 100 == 0:
                print(f"    {label}: {n}/{len(pairs)}", flush=True)
        return rows, unscoreable, failed

    rng = random.Random(SEED)
    print("building the negative strata (no labelling, unlimited supply)")
    strata = negatives(by_file, allowed, rng, args.per_stratum,
                       args.cap_per_record)
    for name, pairs in strata.items():
        print(f"  {name:8s} {len(pairs)} pairs")

    print("\nscoring. Detection is cached per page, so a rerun is free.\n")
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    worst_overall = -9.0
    with (OUT / "paper_development.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stratum", "pair", "best_margin", "second_margin",
                         "marks_agreeing"])
        confirmed_total = scored_total = 0
        for name in ("stack", "file", "record"):
            rows, unscoreable, failed = margins_of(strata[name], name)
            best = [r[0] for r in rows if not np.isnan(r[0])]
            # The SECOND margin is what MIN_MARKS_AGREEING gates on, so it is
            # the number the threshold actually has to clear.
            second = [r[1][1] for r in rows if len(r[1]) > 1]
            summary[name] = (rows, unscoreable)
            for r in rows:
                writer.writerow([name, r[3],
                                 "" if np.isnan(r[0]) else round(r[0], 4),
                                 round(r[1][1], 4) if len(r[1]) > 1 else "",
                                 r[2]])
            if second:
                worst_overall = max(worst_overall, max(second))
            confirmed = sum(1 for r in rows if r[4])
            confirmed_total += confirmed
            scored_total += len(rows)
            print(f"  {name:8s} scoreable {len(rows):4d}, "
                  f"unscoreable {unscoreable:4d}, unreadable {failed:3d}")
            if best:
                print(f"           best single margin {max(best):+.3f}, "
                      f"99th pct {np.percentile(best, 99):+.3f}")
            print(f"           reached two agreeing marks: {len(second)}"
                  + (f", worst second margin {max(second):+.3f}"
                     if second else "")
                  + f"   CONFIRMED (false positives): {confirmed}")

        print("\nknown same-sheet pairs, both from records already inspected:")
        for ra, fa, pa, pb in KNOWN_TRUE:
            v, _, _ = verdict(ra, fa, pa, ra, fa, pb)
            writer.writerow(["true", pair_label(ra, fa, pa, ra, fa, pb),
                             round(max(v.margins), 4) if v.margins else "",
                             round(sorted(v.margins)[-2], 4)
                             if len(v.margins) > 1 else "", v.marks_agreeing])
            print(f"  {ra}-{fa} p{pa}+p{pb}: confirmed={v.confirmed} "
                  f"margins={tuple(round(m, 3) for m in v.margins)}")

    print(f"\nscoreable negatives: {scored_total}   "
          f"false positives: {confirmed_total}")
    if worst_overall > -8:
        print(f"worst SECOND margin on any negative: {worst_overall:+.3f}")
        print(f"MARGIN_THRESHOLD {paper.MARGIN_THRESHOLD} clears it by "
              f"{paper.MARGIN_THRESHOLD - worst_overall:+.3f}")
    else:
        print("no negative ever reached two agreeing marks, so the threshold "
              "is not\nwhat is holding them out -- the two-mark rule is.")
    print("\n" + false_positive_bound(confirmed_total, scored_total))
    print(f"\ndevelopment rows: {OUT / 'paper_development.csv'}")


if __name__ == "__main__":
    main()
