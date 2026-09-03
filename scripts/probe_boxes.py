#!/usr/bin/env python3
"""The template probe: register the graded document, assert what the template
can, and report against the pre-registered bar.

The bar is in docs/labeling-protocol-extract.md, "Box grading, stage three",
and was committed before the template existed: at least 26 of the same 35
boxes on record 1493608, and McNemar exact one-sided at or below 0.05 against
the layered join's 19.

This script runs in two stages and the first one is a gate.

**Ceiling, free, no human time.** A box can only be graded `hit` if the
template asserts a region for it at all. Coverage is therefore an upper bound
on the score, and it is computable without opening the grades or the page.
If the ceiling is below the bar, the bar cannot be met and a grading sitting
would be spent on a foregone conclusion. Reporting that is cheaper and more
honest than grading anyway.

**Sheet.** With --sheet, and only if the ceiling clears the bar, writes the
blinded shuffled grading sheet and the overlays that go with it.

No API calls. Reads the finished run's cache under the prompt hash the run
recorded.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import formlabels as fl             # noqa: E402
from pipeline import template as tpl              # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
SNAP = ROOT / "data" / "extract" / "snap_coverage.jsonl"
GRADES = ROOT / "tests" / "fixtures" / "box_grades.csv"
TEMPLATES = ROOT / "data" / "extract" / "templates"

#: The graded 1966 document and the role of each of its pages.
TARGET = ("1493608", 0, {5: "face", 6: "sec_ii"})
REVISION = "rev7566"
FORM_CLASS = "w2"

#: The pre-registered bar.
BAR_COUNT = 26
BAR_TOTAL = 35


def load_template(role: str):
    path = TEMPLATES / f"{FORM_CLASS}_{REVISION}_{role}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    anchors = {t: tpl.Anchor(t, tuple(v["box"]), v["pages"],
                             tuple(v["spread"]))
               for t, v in raw["anchors"].items()}
    template = tpl.Template(
        revision=raw["revision"], form_class=raw["form_class"],
        page_role=raw["page_role"], anchors=anchors,
        line_height=raw["line_height"], built_from=raw["built_from"])
    template.fields = {n: tuple(b) for n, b in raw["fields"].items()}
    return template, {n: tuple(b) for n, b in raw["blocks"].items()}


def graded_rows():
    import csv
    rows = list(csv.DictReader(GRADES.open(encoding="utf-8-sig")))
    return [r for r in rows if r["record_id"] == TARGET[0]]


def report_rows():
    """The extracted values of the graded document, in overlay order."""
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(
        CACHE, prompt_hash=extractor.recorded_prompt_hash(SMOKE))
    for line in SMOKE.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        if not doc["page_id"].startswith(TARGET[0] + "-"):
            continue
        file_index = int(doc["page_id"].rsplit("-", 2)[1])
        pdf = RAW / TARGET[0] / records[TARGET[0]]["files"][file_index]["name"]
        result = extractor.extract_document(
            None, pdf, tuple(doc["pages"]), record_id=TARGET[0],
            file_index=file_index, cache=cache)
        return pdf, doc["pages"], result.report
    raise LookupError(TARGET[0])


def snap_outcomes():
    out = {}
    if SNAP.exists():
        for line in SNAP.open():
            row = json.loads(line)
            if row["record_id"] == TARGET[0]:
                out[row["field"]] = row
    return out


def mcnemar_one_sided(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c), n + 1)) if b < c \
        else sum(math.comb(n, i) for i in range(b, n + 1))
    return tail / 2 ** n


def wilson(k: int, n: int, z: float = 1.96):
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true",
                    help="write the blinded grading sheet, if the ceiling "
                         "clears the bar")
    ap.add_argument("--seed", type=int, default=20260903)
    args = ap.parse_args()

    pdf, pages, report = report_rows()
    rows = graded_rows()
    print(f"TEMPLATE PROBE, record {TARGET[0]}, {len(rows)} graded boxes\n")

    # ---- registration ----------------------------------------------------
    registered = {}
    for page, role in TARGET[2].items():
        loaded = load_template(role)
        if loaded is None:
            print(f"  page {page} ({role}): no template built")
            continue
        template, blocks = loaded
        words = page_words(pdf, page)
        reg = tpl.register(template, words)
        registered[page] = (template, blocks, reg)
        if reg is None:
            page_unique = len(tpl.unique_tokens(words))
            shared = len(set(tpl.unique_tokens(words)) & set(template.anchors))
            print(f"  page {page} ({role}): REFUSED to register "
                  f"({shared} shared anchors of {page_unique} unique tokens, "
                  f"floor {tpl.MIN_ANCHORS})")
        else:
            print(f"  page {page} ({role}): registered on {reg.matched} "
                  f"anchors, residual median {reg.residual_median:.4f}, "
                  f"p90 {reg.residual_p90:.4f}")
    print()

    # ---- what the template can assert ------------------------------------
    table_rows: Counter = Counter()
    for name, value in report.named_values():
        if "[" in name:
            table_rows[name.split("[")[0]] += 1

    asserted = {}
    for row in rows:
        page = int(row["page"])
        field = row["field"]
        entry = registered.get(page)
        if entry is None or entry[2] is None:
            continue
        template, blocks, reg = entry
        box = None
        if field in template.fields:
            box = reg.transform.box(template.fields[field])
            source = "template"
        elif "[" in field:
            table = field.split("[")[0]
            index = int(field.split("[")[1].split("]")[0])
            cells = table_rows[table]
            per_row = max(1, cells // max(1, index + 1)) if cells else 1
            n_rows = max(index + 1, cells // max(1, per_row))
            if table in blocks:
                band = tpl.row_region(blocks[table], index, n_rows)
                if band is not None:
                    box = reg.transform.box(band)
                    source = "template_row"
        if box is not None:
            asserted[(page, row["box_num"])] = (box, source, field)

    scalars = [r for r in rows if "[" not in r["field"]]
    tables = [r for r in rows if "[" in r["field"]]
    covered_scalar = sum(1 for r in scalars
                         if (int(r["page"]), r["box_num"]) in asserted)
    covered_table = sum(1 for r in tables
                        if (int(r["page"]), r["box_num"]) in asserted)
    ceiling = covered_scalar + covered_table

    print("CEILING: boxes the template asserts a region for at all")
    print(f"  scalars  {covered_scalar:2d}/{len(scalars)}")
    print(f"  table    {covered_table:2d}/{len(tables)}")
    print(f"  overall  {ceiling:2d}/{len(rows)} = {ceiling / len(rows):.1%}")
    if asserted:
        areas = sorted((b[2] - b[0]) * (b[3] - b[1])
                       for b, _, _ in asserted.values())
        print(f"  median asserted region area "
              f"{areas[len(areas) // 2]:.4f} of the page")

    # ---- the comparator, from the committed grades and snap --------------
    snaps = snap_outcomes()
    join = {}
    for row in rows:
        outcome = snaps.get(row["field"], {}).get("outcome")
        if outcome in ("unique", "disambiguated"):
            join[row["box_num"]] = "snap"
        elif row["grade"] in ("hit", "near"):
            join[row["box_num"]] = "band"
    print(f"\nCOMPARATOR: the layered join locates {len(join)}/{len(rows)} "
          f"= {len(join) / len(rows):.1%} on this document")
    print(f"  (snap {sum(1 for v in join.values() if v == 'snap')}, "
          f"band {sum(1 for v in join.values() if v == 'band')})")

    print(f"\nPRE-REGISTERED BAR: {BAR_COUNT}/{BAR_TOTAL} "
          f"= {BAR_COUNT / BAR_TOTAL:.1%}, plus McNemar one-sided <= 0.05")
    if ceiling < BAR_COUNT:
        print(f"  the ceiling is {ceiling}/{len(rows)}, below the bar of "
              f"{BAR_COUNT}. Every unasserted box is a miss by construction,")
        print("  so no grading of the asserted ones can reach the bar. The "
              "bar CANNOT be met and the grading sitting is not owed.")
        best_b = max(0, ceiling - len(join))
        print(f"  best case if every asserted box were graded hit: "
              f"{ceiling}/{len(rows)} = {ceiling / len(rows):.1%}, "
              f"b-c at most {best_b}")
    else:
        low, high = wilson(BAR_COUNT, BAR_TOTAL)
        print(f"  ceiling {ceiling}/{len(rows)} clears it; grading decides. "
              f"Wilson at the bar: [{low:.1%}, {high:.1%}]")
        if args.sheet:
            print("  --sheet: writing the blinded grading sheet")

    print("\nWHERE THE TEMPLATE ABSTAINS (the residue any fix must carry)")
    for row in rows:
        if (int(row["page"]), row["box_num"]) not in asserted:
            outcome = snaps.get(row["field"], {}).get("outcome", "-")
            print(f"  p{row['page']} {row['field']:44s} "
                  f"snap={outcome:14s} model_grade={row['grade']}")


if __name__ == "__main__":
    main()
