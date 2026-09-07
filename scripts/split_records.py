#!/usr/bin/env python3
"""Split the corpus into a development half and a held-out half, once.

Spends nothing. No API calls, no model calls.

**Why this exists.** The staple work of 2026-09-06 tunes a detector on pages,
and every constant it sets is a chance to fit the evidence rather than read it.
The paper module has been here before: DEFECTS #46 records a rule that scored
7 of 8 on the pairs it was built from and 2 of 7 on fresh ones. So the split is
written down before any constant is chosen, and it is derived rather than
remembered so it cannot drift.

**Development is forced, not sampled.** Every record whose pages Alex has
already looked at goes into development regardless of the draw. Those records
can never supply a positive again (DEFECTS #56: the contamination vector is his
memory, not the code), so they are worth nothing as held-out and everything as
development. `seen_by_alex` in scripts/make_paper_sheet.py already derives that
set from the verification sheets themselves, and it is imported rather than
copied.

**What the split does and does not protect.** Negatives never reach Alex, so
this guards one thing only: that the false-confirmation number is measured on
records I did not tune on. It says nothing about positives, which are exhausted
corpus-wide and are the reason the fetch exists.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util                                      # noqa: E402


def _seen_by_alex():
    """Imported by path, which is how this repo loads a script from a
    test (tests/tier2/test_paper_sheet.py). Copying the derivation would
    let the two drift, and the whole point of it is that it cannot."""
    path = ROOT / "scripts" / "make_paper_sheet.py"
    spec = importlib.util.spec_from_file_location("make_paper_sheet", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.seen_by_alex()

MANIFEST = ROOT / "data" / "manifest.jsonl"
SPLIT = ROOT / "tests" / "fixtures" / "paper_record_split.csv"

#: Fixed before any staple constant was chosen.
SEED = 20260906

#: Of the records Alex has NOT seen, this share joins development. The rest are
#: held out. Two thirds held out because negatives are the abundant resource
#: and the held-out false-confirmation count is the number that has to carry
#: weight.
DEV_SHARE = 1 / 3


def records() -> list[str]:
    return [json.loads(line)["record_id"]
            for line in MANIFEST.open() if line.strip()]


def split() -> list[dict]:
    everything = sorted(records())
    seen = _seen_by_alex() & set(everything)
    rest = [r for r in everything if r not in seen]
    rng = random.Random(SEED)
    rng.shuffle(rest)
    extra = set(rest[:round(len(rest) * DEV_SHARE)])
    return [{"record_id": r,
             "half": "development" if r in seen or r in extra else "held_out",
             "reason": ("alex has seen its pages" if r in seen
                        else "drawn" if r in extra else "drawn")}
            for r in everything]


#: Records fetched after the split was written. They are not development and
#: they are not held-out negatives: they are the frame for the blind sitting
#: the fetch exists to make possible. Kept in the same file so there is one
#: place that says what every record is for.
SITTING = "sitting_frame"


def extend() -> list[dict]:
    """Add records the split does not know about, changing no existing row.

    Extending is a different operation from rewriting and only this one is
    allowed. An existing row may never move: the whole value of the file is
    that a record's half was decided before anybody looked at it.
    """
    known = {}
    for line in SPLIT.read_text().splitlines()[1:]:
        if line.strip():
            record_id, half, reason = line.split(",", 2)
            known[record_id] = (half, reason)
    added = []
    for record_id in sorted(records()):
        if record_id in known:
            continue
        added.append({"record_id": record_id, "half": SITTING,
                      "reason": "fetched after the split; sitting frame"})
    return added


def main() -> None:
    if SPLIT.exists():
        added = extend()
        if not added:
            raise SystemExit(
                f"{SPLIT} already covers every record in the manifest. The "
                f"split is written once and extended only; rewriting it after "
                f"a measurement is the thing it exists to prevent.")
        with SPLIT.open("a", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["record_id", "half", "reason"])
            writer.writerows(added)
        print(f"appended {len(added)} records as {SITTING!r}; "
              f"no existing row touched")
        return
    rows = split()
    with SPLIT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["record_id", "half", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    dev = sum(1 for r in rows if r["half"] == "development")
    seen = sum(1 for r in rows if r["reason"].startswith("alex"))
    print(f"records: {len(rows)}")
    print(f"  development {dev:3d}  ({seen} of them because Alex has seen them)")
    print(f"  held out    {len(rows) - dev:3d}")
    print(f"\nseed {SEED}, written to {SPLIT}")


if __name__ == "__main__":
    main()
