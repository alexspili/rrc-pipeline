#!/usr/bin/env python3
"""Stage six's free gate, sheet and scorer, on the same 35 boxes.

Pre-registered in docs/labeling-protocol-extract.md, "Box grading, stage
six": identical rule, population, comparator and escape as stage five,
because the instrument must not move between mechanisms being compared.
The only change is where a region comes from: the pooled Forms cell
where one exists, else the stage-five region; measured table rows past
the detected header rows, else the equal-band fallback. Registration is
still the page's embedded layer onto the stage-five anchors, exact-token.

The stage-five sheet is never reopened; this stage draws its own.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                       # noqa: E402
from pipeline import template as tpl              # noqa: E402
from pipeline.guard import refuse_if_filled       # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402
from scripts import probe_boxes as pb             # noqa: E402
from scripts.stage5_probe import load_template    # noqa: E402

TEMPLATES = ROOT / "pipeline" / "templates"
SHEET = ROOT / "tests" / "fixtures" / "box_grades_stage6.csv"
KEY = ROOT / "tests" / "fixtures" / "box_grades_stage6_key.csv"
OVERLAYS = ROOT / "data" / "labelset" / "overlay_stage6"

BAR_COUNT, BAR_TOTAL = 26, 35
DEAD_AT = 21
COMPARATOR = 19
FILLERS = 5
SEED = 20260909


def load_forms(role: str):
    path = (TEMPLATES
            / f"{pb.FORM_CLASS}_{pb.REVISION}_{role}_forms.json")
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return {
        "fields": {n: tuple(b) for n, b in raw["fields"].items()},
        "rows": {n: [tuple(b) for b in rows]
                 for n, rows in raw["blocks_rows"].items()},
        "headers": raw["header_rows"],
    }


def compute():
    pdf, pages, report = pb.report_rows()
    rows = pb.graded_rows()
    snaps = pb.snap_outcomes()

    registered = {}
    for page, role in pb.TARGET[2].items():
        loaded = load_template(role)
        forms = load_forms(role)
        if loaded is None:
            print(f"  page {page} ({role}): no stage-five template")
            continue
        template, blocks = loaded
        reg = tpl.register(template, page_words(pdf, page))
        registered[page] = (template, blocks, forms, reg)
        if reg is None:
            print(f"  page {page} ({role}): REFUSED to register")
        else:
            forms_n = len(forms["fields"]) if forms else 0
            print(f"  page {page} ({role}): registered on {reg.matched} "
                  f"anchors, residual {reg.residual_median:.4f}; forms "
                  f"geometry: {forms_n} fields, "
                  f"{len(forms['rows']) if forms else 0} row sets")

    table_rows: Counter = Counter()
    for name, _ in report.named_values():
        if "[" in name:
            table_rows[name.split("[")[0]] += 1

    asserted = {}
    for row in rows:
        page, field = int(row["page"]), row["field"]
        entry = registered.get(page)
        if entry is None or entry[3] is None:
            continue
        template, blocks, forms, reg = entry
        box = source = None
        base = field.split("[")[0]
        if forms and field in forms["fields"]:
            box, source = forms["fields"][field], "forms_kv"
        elif field in template.fields:
            box, source = template.fields[field], "template"
        elif "[" in field:
            index = int(field.split("[")[1].split("]")[0])
            if forms and base in forms["rows"]:
                measured = forms["rows"][base]
                position = forms["headers"].get(base, 0) + index
                if position < len(measured):
                    box, source = measured[position], "forms_row"
            if box is None and base in blocks:
                band = tpl.row_region(blocks[base], index,
                                      max(1, table_rows[base]))
                if band is not None:
                    box, source = band, "template_row"
        if box is not None:
            # frame to page runs through the inverse (DEFECTS #79)
            asserted[row["box_num"]] = (reg.page_box(box), source, field)

    snap_boxes = {r["box_num"] for r in rows
                  if snaps.get(r["field"], {}).get("outcome")
                  in ("unique", "disambiguated")}
    residue = [r for r in rows if r["box_num"] not in snap_boxes]
    on_residue = [r for r in residue if r["box_num"] in asserted]
    backstop = [r for r in residue if r["box_num"] not in asserted
                and r["grade"] in ("hit", "near")]
    ceiling = len(snap_boxes) + len(on_residue) + len(backstop)
    return (pdf, rows, snaps, asserted, snap_boxes, residue,
            on_residue, backstop, ceiling)


def ceiling_report(state) -> None:
    (pdf, rows, snaps, asserted, snap_boxes, residue,
     on_residue, backstop, ceiling) = state
    sources = Counter(s for _, s, _ in asserted.values())
    print("\nTHE STACK, snap then stage-six geometry then band:")
    print(f"  snap-located boxes                {len(snap_boxes):2d}")
    print(f"  asserted on the residue           {len(on_residue):2d}"
          f"/{len(residue)}   (sources over all 35: {dict(sources)})")
    print(f"  band-located among abstentions     {len(backstop):2d}")
    print(f"  CEILING                           {ceiling:2d}/{len(rows)}"
          f" = {ceiling / len(rows):.1%}")
    print(f"  comparator: the shipped stack locates {COMPARATOR}"
          f"/{len(rows)}; the stage-five ceiling was 32")

    print(f"\nPRE-REGISTERED ZONES (bar {BAR_COUNT}/{BAR_TOTAL} plus "
          "McNemar one-sided <= 0.05)")
    if ceiling <= DEAD_AT:
        print(f"  ceiling {ceiling} <= {DEAD_AT}: DEAD, no sitting.")
    elif ceiling < BAR_COUNT:
        print(f"  ceiling {ceiling} in 22-25: the elected escape fires "
              "before grading.")
    else:
        print(f"  ceiling {ceiling} clears {BAR_COUNT}: the sitting is "
              "live and grading decides.")

    print("\nWHERE THE CEILING LOSES BOXES")
    for row in residue:
        if row["box_num"] in asserted or row["grade"] in ("hit", "near"):
            continue
        outcome = snaps.get(row["field"], {}).get("outcome", "-")
        print(f"  p{row['page']} {row['field']:44s} snap={outcome}")


def write_sheet(state) -> None:
    import random

    (pdf, rows, snaps, asserted, snap_boxes, residue, on_residue,
     backstop, ceiling) = state
    refuse_if_filled(SHEET, "grade")

    from scripts import score_boxes as sb
    model_boxes = {num: region.box for (record, num), region
                   in sb.regions().items() if record == pb.TARGET[0]}
    by_num = {r["box_num"]: r for r in rows}

    entries = []
    for row in on_residue:
        box, source, field = asserted[row["box_num"]]
        entries.append((int(row["page"]), box, field, row["raw"], source,
                        row["box_num"]))
    filler_pool = sorted(n for n in model_boxes if n in by_num)
    for num in random.Random(SEED).sample(filler_pool, FILLERS):
        row = by_num[num]
        entries.append((int(row["page"]), model_boxes[num], row["field"],
                        row["raw"], "model_filler", num))

    random.Random(SEED).shuffle(entries)
    OVERLAYS.mkdir(parents=True, exist_ok=True)
    for stale in OVERLAYS.glob("*"):
        stale.unlink()
    render.preflight()

    numbered = [(i, *entry) for i, entry in enumerate(entries, 1)]
    sheet_rows = [{
        "record_id": pb.TARGET[0], "file_index": pb.TARGET[1],
        "pages": "5 6", "page": page, "box_num": number,
        "field": field, "raw": (raw or "")[:60],
        "grade": "", "handwritten": "", "note": ""}
        for number, page, box, field, raw, source, orig in numbered]
    key_rows = [{"box_num": number, "page": page, "field": field,
                 "source": source, "orig_box_num": orig,
                 "box": " ".join(f"{v:.4f}" for v in box)}
                for number, page, box, field, raw, source, orig in numbered]

    by_page = {}
    for number, page, box, field, raw, source, orig in numbered:
        by_page.setdefault(page, []).append((number, box, field, raw))
    for page, items in sorted(by_page.items()):
        image = render.extract_page_image(pdf, page).convert("RGB")
        width, height = image.size
        cap = pb.CAP
        short = min(width, height)
        if short and round(max(width, height)
                           * pb.MIN_SHORT_EDGE / short) > cap:
            cap = round(max(width, height) * pb.MIN_SHORT_EDGE / short)
        image = render.downscale_image(image, cap=cap)
        render.draw_numbered_boxes(
            image, [(number, box) for number, box, _, _ in sorted(items)])
        legend = [f"{number:3d}  {field:44s} {raw!r}"
                  for number, box, field, raw in sorted(items)]
        stem = f"STAGE6_{pb.TARGET[0]}_f{pb.TARGET[1]}_p{page:03d}"
        image.save(OVERLAYS / f"{stem}.png")
        (OVERLAYS / f"{stem}.txt").write_text(
            f"{pb.TARGET[0]} page {page}: {len(items)} boxes\n"
            + "\n".join(legend) + "\n")
        print(f"  {stem}.png  {len(items):3d} boxes")

    with SHEET.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sheet_rows[0]))
        writer.writeheader()
        writer.writerows(sheet_rows)
    with KEY.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(sorted(key_rows, key=lambda r: int(r["box_num"])))
    print(f"\n  sheet: {SHEET}  ({len(sheet_rows)} boxes: "
          f"{len(on_residue)} stage-six regions, {FILLERS} fillers)")
    print(f"  key:   {KEY}  (the blind; scoring reads it, you do not)")


def score_sheet(state) -> None:
    (pdf, rows, snaps, asserted, snap_boxes, residue, on_residue,
     backstop, ceiling) = state
    if not SHEET.exists() or not KEY.exists():
        print("\nnothing to score: run --sheet first")
        return
    graded = {r["box_num"]: r for r in
              csv.DictReader(SHEET.open(encoding="utf-8-sig"))}
    key = list(csv.DictReader(KEY.open(encoding="utf-8-sig")))
    ungraded = [k["box_num"] for k in key
                if not graded.get(k["box_num"], {}).get("grade",
                                                        "").strip()]
    if ungraded:
        print(f"\nnot scored: {len(ungraded)} of {len(key)} boxes are "
              "ungraded; finish the sheet or clear it")
        return

    mechanism_grade = {
        k["orig_box_num"]: graded[k["box_num"]]["grade"].strip()
        for k in key if k["source"] != "model_filler"}
    by_num = {r["box_num"]: r for r in rows}

    new_located, shipped_located = {}, {}
    for row in residue:
        num = row["box_num"]
        shipped_located[num] = row["grade"] in ("hit", "near")
        if num in mechanism_grade:
            new_located[num] = mechanism_grade[num] in ("hit", "near")
        else:
            new_located[num] = shipped_located[num]
    b = sum(1 for n in new_located
            if new_located[n] and not shipped_located[n])
    c = sum(1 for n in new_located
            if shipped_located[n] and not new_located[n])
    located = len(snap_boxes) + sum(new_located.values())
    p = pb.mcnemar_one_sided(b, c)

    split = {}
    for k in key:
        split.setdefault(k["source"], Counter())[
            graded[k["box_num"]]["grade"].strip()] += 1

    print("\nSTAGE SIX RESULT, the one marked rule (protocol, R15)\n")
    for name, counts in sorted(split.items()):
        print(f"  {name:13s} hit {counts['hit']:2d}  near "
              f"{counts['near']:2d}  miss {counts['miss']:2d}   "
              "(reported, governs nothing)")
    print(f"\n  located {located}/{len(rows)}  (snap {len(snap_boxes)}, "
          f"stack on the residue {sum(new_located.values())}/"
          f"{len(residue)})")
    print(f"  shipped comparator {COMPARATOR}/{len(rows)}")
    print(f"  McNemar b={b} c={c}, one-sided p = {p:.4f}")

    if located >= BAR_COUNT and p <= 0.05:
        print("\n  PASS. Stage-six geometry becomes the template tier's "
              "geometry, wired under its own rule-5 proposal.")
    elif located <= DEAD_AT:
        print("\n  DEAD. The stage-six thread closes with its number.")
    else:
        print("\n  INCONCLUSIVE. The elected escape fires: 1495195's 14 "
              "boxes, the 49-box bar of 38, once, final either way.")

    fillers = [(k, graded[k["box_num"]]["grade"].strip()) for k in key
               if k["source"] == "model_filler"]
    agree = sum(1 for k, g in fillers
                if g == by_num[k["orig_box_num"]]["grade"])
    print(f"\n  consistency fillers: {agree}/{len(fillers)} agree with "
          "their stage-two grades (governs nothing)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args()

    print(f"STAGE SIX, record {pb.TARGET[0]}\n")
    state = compute()
    if args.score:
        score_sheet(state)
        return
    ceiling_report(state)
    if args.sheet:
        print("\nTHE SITTING'S SHEET")
        write_sheet(state)


if __name__ == "__main__":
    main()
