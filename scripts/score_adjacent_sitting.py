#!/usr/bin/env python3
"""Score the district 02 adjacent sitting against the rule fixed before it ran.

Spends nothing. Recomputes no decision: the rule is in
docs/labeling-protocol-adjacent.md, the mechanism was frozen in commit
1a0182976062931bdcf416f3a104975f91d3cac6, and the verdicts were sealed and
hashed before Alex saw an image.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHEET = ROOT / "tests" / "fixtures" / "adjacent_sitting.csv"
VERDICTS = ROOT / "data" / "probe" / "adjacent_sitting_verdicts.json"

SEALED_SHA = "ceb7e34c8c448196"
MIN_DENOMINATOR = 8
MAX_FALSE = 1
MIN_CONFIRMED = 2
CANNOT_TELL_TRIP = 0.30

#: Channels the mechanism is blind to, so a call resting on one of them is
#: independent confirmation rather than agreement. Ranked in the protocol
#: before the sheet went out.
INDEPENDENT = ("show-through", "showthrough", "ink", "fold", "tear", "crease",
               "silhouette", "shape", "corner")
SHARED = ("punch", "staple", "speck", "blot", "rust", "dirt", "hole")


def upper_bound(k: int, n: int, alpha: float = 0.05) -> float:
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        tail = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i)
                   for i in range(k + 1))
        low, high = (mid, high) if tail > alpha else (low, mid)
    return high


def main() -> None:
    raw = SHEET.read_bytes().decode("utf-8", errors="replace")
    sheet = {r["item"]: r for r in csv.DictReader(io.StringIO(raw))}
    blob = json.loads(VERDICTS.read_text())
    sealed = blob["verdicts"]

    recomputed = hashlib.sha256(
        json.dumps(sealed, sort_keys=True).encode()).hexdigest()
    ok = recomputed == blob["sha256"] and recomputed.startswith(SEALED_SHA)
    print(f"sealed verdicts intact: {ok}  ({recomputed[:16]})")
    if not ok:
        raise SystemExit("the seal is broken; this scoring is void")

    def call(item):
        return (sheet[item]["verdict"] or "").strip().lower()

    labels = Counter(call(i) for i in sealed)
    print(f"\nlabels: {dict(labels)}")
    unsure = labels["cannot-tell"]
    print(f"cannot-tell {unsure} of {len(sealed)} "
          f"({unsure/len(sealed):.0%}), trip is {CANNOT_TELL_TRIP:.0%}")

    same = [i for i in sealed if call(i) == "same-sheet"]
    notsame = [i for i in sealed
               if call(i) in ("different", "same-bundle")]
    confirmed_same = [i for i in same if sealed[i]["confirmed"]]
    confirmed_not = [i for i in notsame if sealed[i]["confirmed"]]

    print("\n--- the two halves of the rule ---")
    print(f"(a) false confirmations among not-one-sheet: "
          f"{len(confirmed_not)} of {len(notsame)}   "
          f"[bar: at most {MAX_FALSE}]")
    print(f"(b) confirmations among same-sheet:          "
          f"{len(confirmed_same)} of {len(same)}   "
          f"[bar: at least {MIN_CONFIRMED}, denominator {MIN_DENOMINATOR}]")

    a_ok = len(confirmed_not) <= MAX_FALSE
    b_ok = len(confirmed_same) >= MIN_CONFIRMED and len(same) >= MIN_DENOMINATOR
    print(f"\n(a) {'PASS' if a_ok else 'FAIL'}    (b) "
          f"{'PASS' if b_ok else 'FAIL'}")
    print(f"RULE: {'PASSES' if a_ok and b_ok else 'FAILS'}")

    if notsame:
        print(f"\nadjacent false-confirmation rate: "
              f"{len(confirmed_not)}/{len(notsame)} = "
              f"{len(confirmed_not)/len(notsame):.1%}, "
              f"95% upper bound {upper_bound(len(confirmed_not), len(notsame)):.1%}")
        print("  for contrast, held out cross-record: 1 of 400, bound 1.18%")

    for item in confirmed_not:
        row, v = sheet[item], sealed[item]
        print(f"  FALSE: {item} {v['record_id']}-{v['file_index']} "
              f"p{v['pages'][0]}+p{v['pages'][1]} {v['transform']} "
              f"agree {v['agreeing']} control {v['control']} "
              f"| judged {call(item)} on {row['evidence'] or 'no evidence given'}")

    print("\n--- what the mechanism missed, and on what evidence ---")
    for item in same:
        row = sheet[item]
        mark = "confirms" if sealed[item]["confirmed"] else "silent  "
        print(f"  {mark} {item}  {row['evidence'] or '-'}")

    print("\n--- secondary: parity (pre-registered, decides nothing) ---")
    par = Counter()
    for item in sealed:
        if call(item) in ("same-sheet", "different", "same-bundle"):
            par[sealed[item]["starts_on"], call(item)] += 1
    for start in ("even", "odd"):
        yes = par[start, "same-sheet"]
        total = sum(v for (s, _), v in par.items() if s == start)
        if total:
            print(f"  starts on {start:4} : {yes} same-sheet of {total} "
                  f"({yes/total:.0%})")

    print("\n--- secondary: which channel carried the same-sheet calls ---")
    chan = Counter()
    for item in same:
        text = (sheet[item]["evidence"] or "").lower()
        chan["independent" if any(k in text for k in INDEPENDENT) else
             ("shared" if any(k in text for k in SHARED) else "none given")] += 1
    print(f"  {dict(chan)}")
    both = sum(1 for i in same
               if any(k in (sheet[i]["evidence"] or "").lower() for k in INDEPENDENT)
               and any(k in (sheet[i]["evidence"] or "").lower() for k in SHARED))
    print(f"  calls citing both an independent and a shared channel: {both}")

    print(f"\nsame-bundle labels used: {labels['same-bundle']}")


if __name__ == "__main__":
    main()
