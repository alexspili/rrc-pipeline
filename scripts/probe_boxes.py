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

**Sheet.** With --sheet, writes the blinded shuffled stage-four sheet and its
overlays: the 18 regions the template asserts and the 15 boxes the layered
join counts as snapped, mixed together. That sitting does NOT reopen the
coverage verdict, which is closed. It asks the one question coverage cannot
answer, whether a region lands when a mechanism asserts one, and its two rules
are pre-registered in the protocol under "Box grading, stage four".

No API calls. Reads the finished run's cache under the prompt hash the run
recorded.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageDraw, ImageFont              # noqa: E402

from pipeline import classify                     # noqa: E402
from pipeline import extractor                    # noqa: E402
from pipeline import formlabels as fl             # noqa: E402
from pipeline import template as tpl              # noqa: E402
from pipeline import render                       # noqa: E402
from pipeline.guard import refuse_if_filled       # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
SNAP = ROOT / "data" / "extract" / "snap_coverage.jsonl"
GRADES = ROOT / "tests" / "fixtures" / "box_grades.csv"
TEMPLATES = ROOT / "data" / "extract" / "templates"
PROBE_SHEET = ROOT / "tests" / "fixtures" / "box_grades_probe.csv"
PROBE_OUT = ROOT / "data" / "labelset" / "overlay_probe"

CAP = 2000
MIN_SHORT_EDGE = 700

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
                    help="write the blinded stage-four grading sheet")
    ap.add_argument("--score", action="store_true",
                    help="score the graded stage-four sheet against both "
                         "pre-registered rules")
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
              "bar CANNOT be met and that verdict needs no grading.")
        print(f"  zone: {'DEAD (21 or fewer)' if ceiling <= 21 else 'see the protocol'}"
              f"; the elected middle-zone escape does not fire.")
    else:
        low, high = wilson(BAR_COUNT, BAR_TOTAL)
        print(f"  ceiling {ceiling}/{len(rows)} clears it; grading decides. "
              f"Wilson at the bar: [{low:.1%}, {high:.1%}]")

    print("\nWHERE THE TEMPLATE ABSTAINS (the residue any fix must carry)")
    for row in rows:
        if (int(row["page"]), row["box_num"]) not in asserted:
            outcome = snaps.get(row["field"], {}).get("outcome", "-")
            print(f"  p{row['page']} {row['field']:44s} "
                  f"snap={outcome:14s} model_grade={row['grade']}")

    if args.sheet:
        print("\nSTAGE FOUR SHEET (does a region land when it is asserted?)")
        write_sheet(pdf, rows, asserted, snaps, args.seed)
    if args.score:
        score_sheet()


def write_sheet(pdf, rows, asserted, snaps, seed: int) -> None:
    """The blinded stage-four sheet: template regions and snap boxes mixed.

    Blinding hides the mechanism, not the field: "does this box land on its
    field" cannot be answered without knowing the field. Two things still
    leak the source and the protocol says so rather than pretending
    otherwise. A snap box is one word and a template region is a form cell,
    so they differ in size. And 7 of the 33 fields appear once from each
    mechanism, so a repeated field is visibly a pair. What the shuffle still
    buys is that the grader cannot tell which box of a pair is which.
    """
    entries = []
    for row in rows:
        key = (int(row["page"]), row["box_num"])
        if key in asserted:
            box, source, field = asserted[key]
            entries.append((int(row["page"]), box, field, row["raw"], source))
    for field, snap in snaps.items():
        if snap["outcome"] not in ("unique", "disambiguated"):
            continue
        if not snap.get("snapped_box"):
            continue
        page = next((int(r["page"]) for r in rows if r["field"] == field),
                    None)
        if page is None:
            continue
        entries.append((page, tuple(snap["snapped_box"]), field,
                        snap.get("raw") or "", "text_layer"))

    # First statement of the destructive half, not the last one (DEFECTS
    # #34). The unlink loop below removes the answer key, which lives under
    # data/ and is git-ignored, so unlike the sheet it has no commit to come
    # back from. A guard belongs at the top of the operation it protects.
    refuse_if_filled(PROBE_SHEET, "grade")

    random.Random(seed).shuffle(entries)
    PROBE_OUT.mkdir(parents=True, exist_ok=True)
    for stale in PROBE_OUT.glob("*"):
        stale.unlink()
    render.preflight()

    numbered = [(i, *entry) for i, entry in enumerate(entries, 1)]
    sheet_rows = [{
        "record_id": TARGET[0], "file_index": TARGET[1],
        "pages": "5 6", "page": page, "box_num": number,
        "field": field, "raw": (raw or "")[:60],
        "grade": "", "handwritten": "", "note": ""}
        for number, page, box, field, raw, source in numbered]
    key_rows = [{"box_num": number, "page": page, "field": field,
                 "source": source,
                 "box": " ".join(f"{v:.4f}" for v in box)}
                for number, page, box, field, raw, source in numbered]

    by_page = {}
    for number, page, box, field, raw, source in numbered:
        by_page.setdefault(page, []).append((number, box, field, raw))
    for page, items in sorted(by_page.items()):
        image = render.extract_page_image(pdf, page).convert("RGB")
        width, height = image.size
        cap = CAP
        short = min(width, height)
        if short and round(max(width, height) * MIN_SHORT_EDGE / short) > cap:
            cap = round(max(width, height) * MIN_SHORT_EDGE / short)
        image = render.downscale_image(image, cap=cap)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=max(22, width // 60))
        except TypeError:
            font = ImageFont.load_default()
        legend = []
        for number, box, field, raw in sorted(items):
            pixels = (int(box[0] * width), int(box[1] * height),
                      int(box[2] * width), int(box[3] * height))
            draw.rectangle(pixels, outline=(220, 0, 0),
                           width=max(2, width // 700))
            draw.text((pixels[0] + 3, max(0, pixels[1] - font.size - 2)),
                      str(number), fill=(220, 0, 0), font=font)
            legend.append(f"{number:3d}  {field:44s} {raw!r}")
        stem = f"PROBE_{TARGET[0]}_f{TARGET[1]}_p{page:03d}"
        image.save(PROBE_OUT / f"{stem}.png")
        (PROBE_OUT / f"{stem}.txt").write_text(
            f"{TARGET[0]} page {page}: {len(items)} boxes\n"
            + "\n".join(legend) + "\n")
        print(f"  {stem}.png  {len(items):3d} boxes")

    with PROBE_SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sheet_rows[0]))
        writer.writeheader()
        writer.writerows(sheet_rows)
    key_path = PROBE_OUT / "KEY_do_not_open_until_graded.csv"
    with key_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(sorted(key_rows, key=lambda r: r["box_num"]))
    print(f"\n  sheet: {PROBE_SHEET}  ({len(sheet_rows)} boxes)")
    print(f"  key:   {key_path}  (the blind; scoring reads it, you do not)")


def score_sheet() -> None:
    """Apply both stage-four rules, which were fixed before the sheet existed.

    The template is judged hit+near because its region is a locator for a
    viewer that zooms to it. The snap tier is judged on hit alone, because a
    snapped box claims a measured word position and a box near the value is a
    box on the wrong word.
    """
    key_path = PROBE_OUT / "KEY_do_not_open_until_graded.csv"
    if not PROBE_SHEET.exists() or not key_path.exists():
        print("\nnothing to score: run --sheet first")
        return
    graded = {r["box_num"]: r for r in
              csv.DictReader(PROBE_SHEET.open(encoding="utf-8-sig"))}
    key = list(csv.DictReader(key_path.open(encoding="utf-8-sig")))
    ungraded = [k["box_num"] for k in key
                if not graded.get(k["box_num"], {}).get("grade", "").strip()]
    if ungraded:
        print(f"\nSTAGE FOUR: not scored, {len(ungraded)} of {len(key)} "
              f"boxes are ungraded")
        return

    buckets = defaultdict(Counter)
    notes = defaultdict(Counter)
    for row in key:
        entry = graded[row["box_num"]]
        grade = entry["grade"].strip()
        source = row["source"]
        buckets[source][grade] += 1
        note = entry.get("note", "").lower()
        if grade == "hit" and "on label" in note:
            notes[source]["on_label"] += 1
        if "x outside" in note:
            notes[source]["x_outside"] += 1
        if "unsure" in note:
            notes[source]["unsure"] += 1
        if source.startswith("template"):
            buckets["template_all"][grade] += 1

    print("\nSTAGE FOUR RESULT, both rules pre-registered before the draw\n")
    template = buckets["template_all"]
    landed = template["hit"] + template["near"]
    total = sum(template.values())
    scalars = buckets["template"]
    cells = buckets["template_row"]
    print("RULE ONE, the template: hit + near over 18")
    print(f"  scalars      {scalars['hit'] + scalars['near']:2d}/"
          f"{sum(scalars.values()):2d}   "
          f"(hit {scalars['hit']}, near {scalars['near']}, "
          f"miss {scalars['miss']})   <- the number that decides")
    print(f"  cell bands   {cells['hit'] + cells['near']:2d}/"
          f"{sum(cells.values()):2d}   "
          f"(hit {cells['hit']}, near {cells['near']}, miss {cells['miss']})"
          f"   <- weak in the hit direction, median area 0.075 of the page")
    low, high = wilson(landed, total) if total else (0, 0)
    print(f"  pooled       {landed:2d}/{total:2d} = {landed / total:.1%}   "
          f"Wilson [{low:.1%}, {high:.1%}]")
    if landed >= 14:
        verdict = ("the cell rule lands. The template's failure is anchor "
                   "inventory only, which is the Textract trigger signature; "
                   "the escalation opens for decision, gated on its own "
                   "ceiling step.")
    elif landed <= 10:
        verdict = ("the layout assumption fails too. Textract stays shut "
                   "permanently on this argument and the template direction "
                   "is closed rather than parked.")
    else:
        verdict = "inconclusive at this n. Stays shut. No escape."
    print(f"  -> {verdict}")
    flags = notes["template"] + notes["template_row"]
    if flags:
        print(f"  notes: " + ", ".join(f"{k} {v}" for k, v in flags.items()))

    snap = buckets["text_layer"]
    hits = snap["hit"]
    total_snap = sum(snap.values())
    print("\nRULE TWO, the snap tier: hit alone over 15")
    print(f"  {hits:2d}/{total_snap:2d} hits  "
          f"(near {snap['near']}, miss {snap['miss']})")
    on_label = notes["text_layer"]["on_label"]
    if on_label:
        print(f"  of those hits, {on_label} landed on the printed label "
              f"rather than the value.")
        print(f"  A snap claims a measured word position, so that is a "
              f"different kind of hit: {hits - on_label}/{total_snap} are on "
              f"the value itself.")
        print("  Reported, not applied: the threshold was pre-registered "
              "against stage two's definition and is not moved after the "
              "fact.")
    if hits >= 12:
        print("  -> the snap tier stands as measured geometry")
    else:
        rate = hits / total_snap if total_snap else 0
        restated = 4 + hits          # the 4 model-box bands, plus real snaps
        print("  -> snap demotes to a disambiguation prior only, pending "
              "diagnosis, and")
        print(f"     the 54.3% comparator on this document is restated: "
              f"{restated}/35 = {restated / 35:.1%} "
              f"(snap hit rate {rate:.1%}, not 100%)")


if __name__ == "__main__":
    main()
