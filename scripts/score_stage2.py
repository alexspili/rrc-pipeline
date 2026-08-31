#!/usr/bin/env python3
"""Score the stage-2 labels against the census predictions.

Every number here was defined in docs/labeling-protocol-stage2.md before the
labels existed. Nothing is added after the fact: if a question is interesting
and not in that list, it goes in the write-up as an observation, not here as a
metric.

Reads the labels, the stratum key and nothing else. No model calls, no cost.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import stage2                      # noqa: E402
from pipeline.estimate import (Stratum,          # noqa: E402
                               stratified_proportion)

LABELS = ROOT / "tests" / "fixtures" / "labels_stage2.csv"
KEY = ROOT / "tests" / "fixtures" / "stage2_strata.csv"

#: Frame sizes measured before the draw. The weights in every estimate below.
#: Pinned against a recount of the census by tests/tier2/test_labelset_stage2.py.
FRAMES = {
    stage2.G1_FACE_SILENT: 43, stage2.G1_FACE_CORROBORATED: 29,
    stage2.W2_FACE_SILENT: 113, stage2.W2_FACE_W15_HEADER: 7,
    stage2.W2_FACE_CORROBORATED: 46, stage2.COMPLETION_NON_FACE: 137,
    stage2.CONFUSABLE: 361, stage2.OVERSIZE: 23, stage2.PARSE_FAILURE: 15,
}

G1_FACE = (stage2.G1_FACE_SILENT, stage2.G1_FACE_CORROBORATED)
W2_FACE = (stage2.W2_FACE_SILENT, stage2.W2_FACE_W15_HEADER,
           stage2.W2_FACE_CORROBORATED)


def load() -> list[dict]:
    labels = {r["page_id"]: r for r in
              csv.DictReader(LABELS.open(encoding="utf-8-sig"))}
    if not all(r["form_class"].strip() for r in labels.values()):
        sys.exit("labels are not complete")
    rows = []
    for key in csv.DictReader(KEY.open(encoding="utf-8-sig")):
        label = labels[key["page_id"]]
        rows.append({
            "page_id": key["page_id"],
            "record_id": key["page_id"].rsplit("-", 2)[0],
            "stratum": key["stratum"],
            "predicted_class": key["predicted_class"],
            "predicted_part": key["predicted_part"],
            "confidence": key["confidence"],
            "seen_in_verify": key["seen_in_verify"] == "yes",
            "true_class": label["form_class"].strip(),
            "true_part": label["part"].strip(),
            "legible": label["form_number_legible"].strip().lower(),
            "note": label["note"].strip(),
            "unsure": "unsure" in label["note"].lower(),
        })
    return rows


def by_stratum(rows: list[dict]) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for row in rows:
        out[row["stratum"]].append(row)
    return out


def precision(rows: list[dict], strata: tuple[str, ...], predicted: str,
              with_part: bool = False):
    """Share of pages predicted `predicted` face that really are one."""
    groups = by_stratum(rows)
    cells = []
    for name in strata:
        drawn = groups[name]
        hits = sum(1 for r in drawn
                   if r["true_class"] == predicted
                   and (not with_part or r["true_part"] == "face"))
        cells.append(Stratum(name, FRAMES[name], len(drawn), hits))
    return stratified_proportion(cells)


def report(rows: list[dict], title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")

    print("\n1. PRECISION OF THE COMPLETION FACES, stratified, FPC applied")
    for label, strata, predicted in (("g1 face", G1_FACE, "g1"),
                                     ("w2 face", W2_FACE, "w2")):
        klass = precision(rows, strata, predicted)
        both = precision(rows, strata, predicted, with_part=True)
        print(f"   {label:8s} class only      {klass.as_percent():>18s}   "
              f"({klass.hits}/{klass.sampled} of {klass.frame_size} pages)")
        print(f"   {'':8s} class and part  {both.as_percent():>18s}")
    groups = by_stratum(rows)
    print("\n   per stratum:")
    for name in G1_FACE + W2_FACE:
        drawn = groups[name]
        want = "g1" if name in G1_FACE else "w2"
        hits = sum(1 for r in drawn if r["true_class"] == want)
        records = len({r["record_id"] for r in drawn})
        print(f"     {name:28s} {hits:2d}/{len(drawn):2d}   "
              f"over {records} records")

    print("\n2. ATTRIBUTION INVENTED ON A PAGE THAT NAMES NO FORM (stratum F)")
    f_rows = groups[stage2.COMPLETION_NON_FACE]
    unnamed = sum(1 for r in f_rows if r["true_class"] == "other_form")
    cell = Stratum(stage2.COMPLETION_NON_FACE,
                   FRAMES[stage2.COMPLETION_NON_FACE], len(f_rows), unnamed)
    est = stratified_proportion([cell])
    print(f"   labelled other_form: {est.as_percent()}  "
          f"({unnamed}/{len(f_rows)} of {FRAMES[stage2.COMPLETION_NON_FACE]})")
    print("   the census gave every one of them a form number and a part.")

    print("\n3. CONFUSION IN THE COMPLETION NEIGHBOURHOOD")
    matrix = Counter()
    for row in rows:
        if row["stratum"] in G1_FACE + W2_FACE + (stage2.COMPLETION_NON_FACE,
                                                  stage2.CONFUSABLE):
            matrix[(f"{row['predicted_class']}/{row['predicted_part']}",
                    f"{row['true_class']}/{row['true_part']}")] += 1
    for (predicted, true), n in sorted(matrix.items(), key=lambda kv: -kv[1]):
        flag = "" if predicted == true else "   <-- wrong"
        print(f"   {n:3d}  predicted {predicted:22s} true {true:24s}{flag}")

    print("\n4. RECALL BOUND (stratum G)")
    g_rows = groups[stage2.CONFUSABLE]
    found = [r for r in g_rows if r["true_class"] in ("g1", "w2")]
    print(f"   completion pages found among {len(g_rows)} drawn from a "
          f"{FRAMES[stage2.CONFUSABLE]}-page frame: {len(found)}")
    print("   a bound, not an estimate, as the protocol says.")

    print("\n5. ACCURACY PER SELF-REPORTED CONFIDENCE (R6)")
    buckets = defaultdict(lambda: [0, 0])
    for row in rows:
        if not row["confidence"]:
            continue
        bucket = buckets[row["confidence"]]
        bucket[1] += 1
        if (row["true_class"] == row["predicted_class"]
                and row["true_part"] == row["predicted_part"]):
            bucket[0] += 1
    for name in ("high", "medium", "low"):
        hits, n = buckets[name]
        if n:
            print(f"   {name:7s} {hits:3d}/{n:3d}  {hits / n:.0%}")
    print("   unweighted: a stratified sample is not the corpus. Directional.")

    print("\n6. THE PRINTED FORM NUMBER")
    legible = Counter((r["legible"], r["true_class"] == "other_form")
                      for r in rows)
    yes = sum(n for (leg, _), n in legible.items() if leg == "y")
    print(f"   legible on {yes} of {len(rows)} drawn pages")
    for stratum in G1_FACE + W2_FACE:
        drawn = groups[stratum]
        n_legible = sum(1 for r in drawn if r["legible"] == "y")
        want = "g1" if stratum in G1_FACE else "w2"
        right_legible = sum(1 for r in drawn
                            if r["legible"] == "y" and r["true_class"] == want)
        right_not = sum(1 for r in drawn
                        if r["legible"] != "y" and r["true_class"] == want)
        print(f"     {stratum:28s} legible {right_legible}/{n_legible}   "
              f"illegible {right_not}/{len(drawn) - n_legible}")


def main() -> None:
    rows = load()
    print(f"{len(rows)} labelled pages, "
          f"{sum(1 for r in rows if r['unsure'])} noted unsure")

    report(rows, "ALL DRAWN PAGES")

    seen = [r for r in rows if r["seen_in_verify"]]
    if seen:
        report([r for r in rows if not r["seen_in_verify"]],
               f"EXCLUDING THE {len(seen)} PAGES IN RECORDS RENDERED FOR "
               "verify.csv")

    print(f"\n{'=' * 72}\nADD-ONS\n{'=' * 72}")
    groups = by_stratum(rows)
    for name in (stage2.OVERSIZE, stage2.PARSE_FAILURE):
        drawn = groups[name]
        print(f"\n{name}  n={len(drawn)}")
        if name == stage2.OVERSIZE:
            right = sum(1 for r in drawn
                        if r["true_class"] == r["predicted_class"])
            print(f"   class correct on {right}/{len(drawn)} "
                  f"({right / len(drawn):.0%}); R1 measured for the first time")
        for row in drawn:
            mark = "" if row["true_class"] == row["predicted_class"] else " <--"
            print(f"   {row['page_id']:16s} predicted "
                  f"{row['predicted_class'] or '(none)':16s} true "
                  f"{row['true_class']:16s}{mark}  {row['note'][:40]}")


if __name__ == "__main__":
    main()
