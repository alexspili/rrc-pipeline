#!/usr/bin/env python3
"""Score the held-out sitting against the rule fixed before it was drawn.

Spends nothing. No API calls.

docs/labeling-protocol-paper.md. The mechanism was frozen in commit
4868fdd3f714a38f9117b81b2b1c5f57a7c2b642 and its verdicts for these 30 rows
were sealed and hashed before Alex saw the sheet. This script re-checks the
hash, applies the rule as written, and reports both halves.

Nothing here may change the arithmetic. What the failures teach is recorded
separately, in DEFECTS and in the module doc, and does not feed back.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import paper                          # noqa: E402
from pipeline import pageclass as pc                # noqa: E402
from pipeline import papermatch                     # noqa: E402
from pipeline import render                         # noqa: E402

SHEET = ROOT / "tests" / "fixtures" / "paper_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "paper_sitting_verdicts.json"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
CACHE = ROOT / "data" / "cache" / "paper"

#: Pre-registered, before the sheet was drawn.
MIN_DENOMINATOR = 8
CANNOT_TELL_TRIP = 0.30
SEED = 20260907


def judgements() -> dict:
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    return {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}


def sealed() -> dict:
    blob = json.loads(VERDICTS.read_text())
    recomputed = hashlib.sha256(
        json.dumps(blob["verdicts"], sort_keys=True).encode()).hexdigest()
    if recomputed != blob["sha256"]:
        raise SystemExit("the sealed verdicts have been altered since the "
                         "sheet went out; this scoring is void")
    return blob["verdicts"]


def part_b(rows, verdicts) -> dict:
    def call(item):
        return (rows[item]["verdict"] or "").strip().lower()

    same = [k for k in verdicts if call(k) == "same-sheet"]
    diff = [k for k in verdicts if call(k) == "not-same-sheet"]
    unsure = [k for k in verdicts if call(k) == "cannot-tell"]
    confirmed = [k for k in same if verdicts[k]["confirmed"]]
    false_positives = [k for k in diff if verdicts[k]["confirmed"]]
    return {"same": same, "diff": diff, "unsure": unsure,
            "confirmed": confirmed, "false_positives": false_positives,
            "cannot_tell_rate": len(unsure) / len(verdicts)}


def part_a(verdicts, per_stratum: int = 300) -> dict:
    """False confirmations on guaranteed-false pairs from HELD-OUT records."""
    recs = {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}
    by_file = defaultdict(dict)
    for line in CENSUS.open():
        if line.strip():
            row = json.loads(line)
            rid, fi, page = pc.parse_page_id(row["page_id"])
            by_file[(rid, fi)][page] = row

    held_out = sorted({v["record_id"] for v in verdicts.values()})
    cache = papermatch.MarkCache(CACHE)
    hashes: dict = {}

    def marks(rid, fi, page):
        pdf = RAW / rid / recs[rid]["files"][fi]["name"]
        hashes.setdefault(pdf, render.doc_hash(pdf))
        return papermatch.page_marks(pdf, page, cache, hashes[pdf])

    rng = random.Random(SEED)
    lease = {r: (recs[r].get("meta") or {}).get("lease_name", "")
             for r in held_out}
    files = {k: v for k, v in by_file.items() if k[0] in held_out}

    pairs = {"stack": [], "record": []}
    keys = [k for k in files if len(files[k]) >= 4]
    rng.shuffle(keys)
    for key in keys:
        pages = sorted(files[key])
        for _ in range(6):
            a, b = rng.sample(pages, 2)
            if abs(a - b) >= 2:
                pairs["stack"].append((key[0], key[1], a, key[1], b))
            if len(pairs["stack"]) >= per_stratum:
                break
        if len(pairs["stack"]) >= per_stratum:
            break
    guard = 0
    while len(pairs["record"]) < per_stratum and guard < per_stratum * 40:
        guard += 1
        ra, rb = rng.sample(held_out, 2)
        if lease.get(ra) and lease.get(ra) == lease.get(rb):
            continue
        fa = rng.choice([k[1] for k in files if k[0] == ra])
        fb = rng.choice([k[1] for k in files if k[0] == rb])
        pairs["record"].append((ra, fa, rng.choice(sorted(files[(ra, fa)])),
                                rb, fb, rng.choice(sorted(files[(rb, fb)]))))

    out = {}
    for name, group in pairs.items():
        scored = confirmed = 0
        for entry in group:
            if name == "stack":
                ra, fa, pa, fb, pb = entry
                rb = ra
            else:
                ra, fa, pa, rb, fb, pb = entry
            try:
                first, second = marks(ra, fa, pa), marks(rb, fb, pb)
            except Exception:                           # noqa: BLE001
                continue
            if min(len(first), len(second)) < paper.MIN_MARKS_AGREEING:
                continue
            scored += 1
            if paper.compare(first, second).confirmed:
                confirmed += 1
        out[name] = (scored, confirmed)
    return out


def main() -> None:
    rows, verdicts = judgements(), sealed()
    print(f"sealed verdicts verified, sha256 "
          f"{hashlib.sha256(json.dumps(verdicts, sort_keys=True).encode()).hexdigest()[:16]}")

    b = part_b(rows, verdicts)
    print(f"\nPART B  Alex judged: same-sheet {len(b['same'])}, "
          f"not-same-sheet {len(b['diff'])}, cannot-tell {len(b['unsure'])}")
    print(f"        cannot-tell rate {b['cannot_tell_rate']:.0%} "
          f"(inconclusive above {CANNOT_TELL_TRIP:.0%})")
    if b["cannot_tell_rate"] > CANNOT_TELL_TRIP:
        print("        INCONCLUSIVE: the labels are not trustworthy.")
    print(f"        confirmed {len(b['confirmed'])} of {len(b['same'])} "
          f"same-sheet pairs = "
          f"{len(b['confirmed']) / max(len(b['same']), 1):.0%}")
    print(f"        rule: at least half of at least {MIN_DENOMINATOR}")
    b_pass = (len(b["same"]) >= MIN_DENOMINATOR
              and 2 * len(b["confirmed"]) >= len(b["same"]))
    print(f"        -> {'PASS' if b_pass else 'FAIL'}")
    print(f"        confirmations among pairs Alex judged NOT same-sheet: "
          f"{len(b['false_positives'])} {b['false_positives']}")

    print("\nPART A  guaranteed-false pairs from the sitting's own records")
    a = part_a(verdicts)
    total_scored = total_confirmed = 0
    for name, (scored, confirmed) in sorted(a.items()):
        total_scored += scored
        total_confirmed += confirmed
        print(f"        {name:8s} scoreable {scored:4d}   "
              f"false confirmations {confirmed}")
    a_pass = total_confirmed == 0
    print(f"        -> {'PASS' if a_pass else 'FAIL'}  "
          f"({total_confirmed} of {total_scored})")

    print("\nDECISION RULE: ships only if BOTH hold.")
    print(f"  Part A {'PASS' if a_pass else 'FAIL'}   "
          f"Part B {'PASS' if b_pass else 'FAIL'}")
    print(f"  -> {'SHIPS' if (a_pass and b_pass) else 'DOES NOT SHIP'}")

    print("\nwhat the evidence column says Alex actually used:")
    for kind, n in Counter(
            (rows[k]["evidence"] or "none given").strip().lower()
            for k in b["same"]).most_common():
        print(f"    {n:3d}  {kind}")


if __name__ == "__main__":
    main()
