#!/usr/bin/env python3
"""Before and after, on the 143 stage-2 labelled pages.

Method fixed in docs/modules/classify.md before the run was submitted:
stratified estimator for "before", a within-stratum bootstrap of a domain ratio
for "after", 2,000 resamples, 5th and 95th percentiles.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import stage2                              # noqa: E402
from pipeline.estimate import Stratum, stratified_proportion  # noqa: E402

LABELS = ROOT / "tests" / "fixtures" / "labels_stage2.csv"
KEY = ROOT / "tests" / "fixtures" / "stage2_strata.csv"
AFTER = ROOT / "data" / "census" / "stage2_after.jsonl"

FRAMES = {
    stage2.G1_FACE_SILENT: 43, stage2.G1_FACE_CORROBORATED: 29,
    stage2.W2_FACE_SILENT: 113, stage2.W2_FACE_W15_HEADER: 7,
    stage2.W2_FACE_CORROBORATED: 46, stage2.COMPLETION_NON_FACE: 137,
    stage2.CONFUSABLE: 361, stage2.OVERSIZE: 23, stage2.PARSE_FAILURE: 15,
}
G1_STRATA = (stage2.G1_FACE_SILENT, stage2.G1_FACE_CORROBORATED)
W2_STRATA = (stage2.W2_FACE_SILENT, stage2.W2_FACE_W15_HEADER,
             stage2.W2_FACE_CORROBORATED)
SCORED = stage2.SCORED
BOOTSTRAP = 2000
SEED = 20260901


def load():
    labels = {r["page_id"]: r for r in
              csv.DictReader(LABELS.open(encoding="utf-8-sig"))}
    after = {json.loads(l)["page_id"]: json.loads(l)
             for l in AFTER.open() if l.strip()}
    rows = []
    for k in csv.DictReader(KEY.open(encoding="utf-8-sig")):
        pid = k["page_id"]
        a = after[pid]
        rows.append({
            "page_id": pid, "record_id": pid.rsplit("-", 2)[0],
            "stratum": k["stratum"],
            "before_class": k["predicted_class"], "before_part": k["predicted_part"],
            "after_class": a["form_class"], "after_part": a["part"],
            "after_legible": a["form_number_legible"], "after_error": a["error"],
            "true_class": labels[pid]["form_class"].strip(),
            "true_part": labels[pid]["part"].strip(),
            "true_legible": labels[pid]["form_number_legible"].strip().lower(),
        })
    return rows


def groups(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["stratum"]].append(r)
    return out


def precision_before(rows, strata, want):
    g = groups(rows)
    return stratified_proportion([
        Stratum(s, FRAMES[s], len(g[s]),
                sum(1 for r in g[s] if r["true_class"] == want))
        for s in strata])


def domain_ratio(rows, want, rng=None):
    """Weighted precision over the pages the new run calls `want` face."""
    g = groups(rows)
    num = den = 0.0
    for s in SCORED:
        drawn = g[s]
        if not drawn:
            continue
        if rng is not None:
            drawn = [rng.choice(drawn) for _ in drawn]
        weight = FRAMES[s] / len(drawn)
        for r in drawn:
            if r["after_class"] == want and r["after_part"] == "face":
                den += weight
                if r["true_class"] == want:
                    num += weight
    return (num / den if den else None), den


def bootstrap(rows, want):
    rng = random.Random(SEED)
    draws = []
    for _ in range(BOOTSTRAP):
        value, _ = domain_ratio(rows, want, rng)
        if value is not None:
            draws.append(value)
    if not draws:
        return None
    draws.sort()
    return draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws))]


def weighted_count(rows, predicate):
    g = groups(rows)
    return sum(FRAMES[s] / len(g[s]) * sum(1 for r in g[s] if predicate(r))
               for s in SCORED if g[s])


def main():
    rows = load()
    scored = [r for r in rows if r["stratum"] in SCORED]
    print(f"{len(rows)} pages re-classified, {len(scored)} in the scored frame "
          f"of {sum(FRAMES[s] for s in SCORED)} pages\n")

    print("=" * 70)
    print("1. PRECISION OF THE NAMED COMPLETION FACES")
    print("=" * 70)
    for name, strata, want in (("g1 face", G1_STRATA, "g1"),
                               ("w2 face", W2_STRATA, "w2")):
        before = precision_before(rows, strata, want)
        after, den = domain_ratio(rows, want)
        interval = bootstrap(rows, want)
        print(f"\n  {name}")
        print(f"    before  {before.as_percent()}   "
              f"({before.hits}/{before.sampled} drawn, {before.frame_size}-page frame)")
        if after is None:
            print("    after   the run calls no page this class at all")
        else:
            lo, hi = interval
            print(f"    after   {after:.1%}   90% bootstrap [{lo:.1%}, {hi:.1%}]"
                  f"   over ~{den:.0f} pages of the frame")

    print("\n" + "=" * 70)
    print("2. COVERAGE: what the run now calls each class, over the 736-page frame")
    print("=" * 70)
    for label, pred in (
            ("g1 face", lambda r: r["after_class"] == "g1" and r["after_part"] == "face"),
            ("w2 face", lambda r: r["after_class"] == "w2" and r["after_part"] == "face"),
            ("completion_face_unknown_form", lambda r: r["after_class"] == "completion_face_unknown_form"),
            ("completion_face_legacy", lambda r: r["after_class"] == "completion_face_legacy"),
            ("any completion face", lambda r: r["after_class"] in
             ("g1", "w2", "completion_face_unknown_form", "completion_face_legacy")),
            ("parse failure", lambda r: r["after_error"]),
    ):
        print(f"    {label:32s} ~{weighted_count(rows, pred):5.0f} pages")
    print(f"\n    before, by construction:  g1 face 72, w2 face 166, "
          "abstentions 0")

    print("\n" + "=" * 70)
    print("3. WHERE THE PREVIOUSLY WRONG PAGES WENT")
    print("=" * 70)
    faces = [r for r in rows if r["stratum"] in G1_STRATA + W2_STRATA]
    wrong = [r for r in faces if r["true_class"] != r["before_class"]]
    moved = Counter()
    for r in wrong:
        if r["after_error"]:
            moved["parse failure"] += 1
        elif r["after_class"] == r["true_class"]:
            moved["now correct"] += 1
        elif r["after_class"] in ("completion_face_unknown_form",
                                 "completion_face_legacy"):
            moved[f"abstained ({r['after_class'].replace('completion_face_','')})"] += 1
        elif r["after_class"] in ("g1", "w2"):
            moved["still names a form, still wrong"] += 1
        else:
            moved[f"other class ({r['after_class']})"] += 1
    print(f"    {len(wrong)} of {len(faces)} drawn faces were wrong before")
    for k, v in moved.most_common():
        print(f"      {v:3d}  {k}")

    right = [r for r in faces if r["true_class"] == r["before_class"]]
    kept = sum(1 for r in right if r["after_class"] == r["true_class"])
    print(f"\n    {len(right)} were right before; {kept} still right, "
          f"{len(right) - kept} lost")
    for r in right:
        if r["after_class"] != r["true_class"]:
            print(f"      {r['page_id']:16s} {r['true_class']} -> "
                  f"{r['after_class'] or 'PARSE FAIL'}")

    print("\n" + "=" * 70)
    print("4. PARSE FAILURES, counted apart from abstentions")
    print("=" * 70)
    fails = [r for r in rows if r["after_error"]]
    print(f"    {len(fails)} of {len(rows)} pages")
    for r in fails:
        print(f"      {r['page_id']:16s} {r['after_error'][:88]}")

    print("\n" + "=" * 70)
    print("5. RECORD-LEVEL UNION across the drawn pages")
    print("=" * 70)
    comp = ("g1", "w2", "completion_face_unknown_form", "completion_face_legacy")
    before_recs = {r["record_id"] for r in rows if r["before_class"] in ("g1", "w2")}
    after_recs = {r["record_id"] for r in rows if r["after_class"] in comp}
    true_recs = {r["record_id"] for r in rows if r["true_class"] in ("g1", "w2")}
    print(f"    records with a completion page, before: {len(before_recs)}")
    print(f"    records with a completion page, after:  {len(after_recs)}")
    print(f"    records the LABELS say have one:        {len(true_recs)}")
    print(f"    lost: {sorted(before_recs - after_recs)}")

    print("\n" + "=" * 70)
    print("6. THE LEGIBILITY ANSWER AGAINST ALEX'S")
    print("=" * 70)
    agree = sum(1 for r in rows if r["after_legible"] is not None
                and r["true_legible"] in ("y", "n")
                and r["after_legible"] == (r["true_legible"] == "y"))
    have = sum(1 for r in rows if r["after_legible"] is not None
               and r["true_legible"] in ("y", "n"))
    print(f"    model and human agree on {agree}/{have} pages "
          f"({agree / have:.0%})")
    disagree = Counter((r["after_legible"], r["true_legible"]) for r in rows
                       if r["after_legible"] is not None
                       and r["true_legible"] in ("y", "n")
                       and r["after_legible"] != (r["true_legible"] == "y"))
    for (m, h), n in disagree.most_common():
        print(f"      model says legible={m}, Alex says {h}: {n}")


if __name__ == "__main__":
    main()
