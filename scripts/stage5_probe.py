#!/usr/bin/env python3
"""Stage five's free gate: the stack ceiling on the 35 graded boxes.

Pre-registered in docs/labeling-protocol-extract.md, "Box grading, stage
five". The stack under test is snap, then the multi-sample template where
the page registers and a region is asserted, then the band. A box is
located when snap located it, or the template asserted a region graded hit
or near, or the template abstained and the band's stage-two grade on that
exact box was hit or near. The bar is 26 of 35 with McNemar one-sided at
or below 0.05 against the shipped 19; the ceiling is computable free, and
a ceiling of 21 or fewer is the DEAD zone with no sitting, 22 to 25 fires
the elected escape before grading.

Registration here is the shipping configuration: the graded document's own
embedded-layer words, exact-token, onto the Textract-built anchor table.
No aliases (the single-variable rule in the protocol), no API calls, no
cost.

Reuses scripts/probe_boxes.py's loaders for the graded document, grades
and snap outcomes, so the two probes cannot disagree about what the 35
boxes are.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                       # noqa: E402
from pipeline import template as tpl              # noqa: E402
from pipeline.guard import refuse_if_filled       # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402
from scripts import probe_boxes as pb             # noqa: E402

TEMPLATES = ROOT / "pipeline" / "templates"
SHEET = ROOT / "tests" / "fixtures" / "box_grades_stage5.csv"
#: Committed, not under data/: the answer key cannot be regenerated once
#: its sheet is graded, and it carries field names and coordinates rather
#: than corpus imagery (DEFECTS #36).
KEY = ROOT / "tests" / "fixtures" / "box_grades_stage5_key.csv"
OVERLAYS = ROOT / "data" / "labelset" / "overlay_stage5"

#: The stage-five rule's numbers, fixed in the protocol before the read.
BAR_COUNT, BAR_TOTAL = 26, 35
DEAD_AT = 21
COMPARATOR = 19

#: Blinded consistency fillers: already-graded model boxes, re-drawn so the
#: sitting checks itself against stage two. Their grades govern nothing.
FILLERS = 5
SEED = 20260908


def load_template(role: str):
    path = TEMPLATES / f"{pb.FORM_CLASS}_{pb.REVISION}_{role}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    if raw.get("word_source") != "textract":
        raise SystemExit(f"{path} is not a stage-five template")
    anchors = {t: tpl.Anchor(t, tuple(v["box"]), v["pages"],
                             tuple(v["spread"]))
               for t, v in raw["anchors"].items()}
    template = tpl.Template(
        revision=raw["revision"], form_class=raw["form_class"],
        page_role=raw["page_role"], anchors=anchors,
        line_height=raw["line_height"], built_from=raw["built_from"])
    template.fields = {n: tuple(b) for n, b in raw["fields"].items()}
    return template, {n: tuple(b) for n, b in raw["blocks"].items()}


def compute():
    """Everything the ceiling, the sheet and the scorer share."""
    pdf, pages, report = pb.report_rows()
    rows = pb.graded_rows()
    snaps = pb.snap_outcomes()

    registered = {}
    for page, role in pb.TARGET[2].items():
        loaded = load_template(role)
        if loaded is None:
            print(f"  page {page} ({role}): no stage-five template built")
            continue
        template, blocks, = loaded
        words = page_words(pdf, page)
        reg = tpl.register(template, words)
        registered[page] = (template, blocks, reg)
        if reg is None:
            shared = len(set(tpl.unique_tokens(words))
                         & set(template.anchors))
            print(f"  page {page} ({role}): REFUSED to register "
                  f"({shared} shared anchors, floor {tpl.MIN_ANCHORS})")
        else:
            print(f"  page {page} ({role}): registered on {reg.matched} "
                  f"anchors, residual median {reg.residual_median:.4f}, "
                  f"p90 {reg.residual_p90:.4f}")

    from collections import Counter
    table_rows: Counter = Counter()
    for name, _ in report.named_values():
        if "[" in name:
            table_rows[name.split("[")[0]] += 1

    asserted = {}
    for row in rows:
        page, field = int(row["page"]), row["field"]
        entry = registered.get(page)
        if entry is None or entry[2] is None:
            continue
        template, blocks, reg = entry
        box, source = None, None
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
            asserted[row["box_num"]] = (box, source, field)

    snap_boxes = {r["box_num"] for r in rows
                  if snaps.get(r["field"], {}).get("outcome")
                  in ("unique", "disambiguated")}
    residue = [r for r in rows if r["box_num"] not in snap_boxes]
    t_on_residue = [r for r in residue if r["box_num"] in asserted]
    band_backstop = [r for r in residue if r["box_num"] not in asserted
                     and r["grade"] in ("hit", "near")]
    ceiling = len(snap_boxes) + len(t_on_residue) + len(band_backstop)
    return (pdf, rows, snaps, asserted, snap_boxes, residue,
            t_on_residue, band_backstop, ceiling)


def ceiling_report(state) -> None:
    (pdf, rows, snaps, asserted, snap_boxes, residue,
     t_on_residue, band_backstop, ceiling) = state
    print("\nTHE STACK, snap then template then band:")
    print(f"  snap-located boxes                {len(snap_boxes):2d}")
    print(f"  template asserts on the residue   {len(t_on_residue):2d}"
          f"/{len(residue)}")
    print(f"  band-located among abstentions     {len(band_backstop):2d}")
    print(f"  CEILING                           {ceiling:2d}/{len(rows)}"
          f" = {ceiling / len(rows):.1%}")
    print(f"  comparator: the shipped stack locates {COMPARATOR}"
          f"/{len(rows)} = {COMPARATOR / len(rows):.1%}")

    print(f"\nPRE-REGISTERED ZONES (bar {BAR_COUNT}/{BAR_TOTAL} plus "
          "McNemar one-sided <= 0.05)")
    if ceiling <= DEAD_AT:
        print(f"  ceiling {ceiling} <= {DEAD_AT}: DEAD, no sitting. The "
              "thread re-closes and the record states what the money "
              "bought.")
    elif ceiling < BAR_COUNT:
        print(f"  ceiling {ceiling} in 22-25: the elected escape fires "
              "BEFORE grading; the sheet extends to 1495195's 14 boxes "
              "and the 49-box bar of 38 governs.")
    else:
        print(f"  ceiling {ceiling} clears {BAR_COUNT}: the sitting is "
              "live and grading decides.")

    print("\nWHERE THE STACK'S CEILING LOSES BOXES (the residue any "
          "verdict carries)")
    for row in residue:
        if row["box_num"] in asserted or row["grade"] in ("hit", "near"):
            continue
        outcome = snaps.get(row["field"], {}).get("outcome", "-")
        print(f"  p{row['page']} {row['field']:44s} "
              f"snap={outcome:14s} model_grade={row['grade']}")

    print("\nSECONDARY, governing nothing: template regions coinciding "
          "with a miss-graded model box")
    both = [r for r in rows if r["box_num"] in asserted
            and r["grade"] == "miss"]
    print(f"  {len(both)} of {len(asserted)} asserted regions cover a box "
          "the model box missed; those are the boxes the sitting tests")


def write_sheet(state) -> None:
    """The blinded stage-five sheet: the template's residue regions plus
    consistency fillers, shuffled, mechanism hidden.

    The sitting grades ONLY the template regions on the non-snapped boxes;
    snap stands on its stage-four grades and is counted per the standing
    convention, so it never appears here. The fillers are already-graded
    model boxes re-drawn blind; their grades govern nothing and check the
    sitting against stage two.
    """
    import random

    (pdf, rows, snaps, asserted, snap_boxes, residue, t_on_residue,
     band_backstop, ceiling) = state

    refuse_if_filled(SHEET, "grade")

    from scripts import score_boxes as sb
    model_boxes = {num: region.box for (record, num), region
                   in sb.regions().items() if record == pb.TARGET[0]}
    by_num = {r["box_num"]: r for r in rows}

    entries = []
    for row in t_on_residue:
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
        stem = f"STAGE5_{pb.TARGET[0]}_f{pb.TARGET[1]}_p{page:03d}"
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
        writer.writerows(sorted(key_rows,
                                key=lambda r: int(r["box_num"])))
    print(f"\n  sheet: {SHEET}  ({len(sheet_rows)} boxes: "
          f"{len(t_on_residue)} template regions, {FILLERS} fillers)")
    print(f"  key:   {KEY}  (the blind; scoring reads it, you do not)")


def score_sheet(state) -> None:
    """Apply the stage-five rule, fixed in the protocol before the read."""
    (pdf, rows, snaps, asserted, snap_boxes, residue, t_on_residue,
     band_backstop, ceiling) = state

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
              "ungraded, and a rule applied to part of a sheet is not the "
              "rule that was pre-registered")
        return

    template_grade = {k["orig_box_num"]: graded[k["box_num"]]["grade"].strip()
                      for k in key if k["source"].startswith("template")}
    by_num = {r["box_num"]: r for r in rows}

    new_located, shipped_located = {}, {}
    for row in residue:
        num = row["box_num"]
        shipped_located[num] = row["grade"] in ("hit", "near")
        if num in template_grade:
            new_located[num] = template_grade[num] in ("hit", "near")
        else:
            new_located[num] = shipped_located[num]
    b = sum(1 for n in new_located
            if new_located[n] and not shipped_located[n])
    c = sum(1 for n in new_located
            if shipped_located[n] and not new_located[n])
    located = len(snap_boxes) + sum(new_located.values())
    p = pb.mcnemar_one_sided(b, c)

    from collections import Counter
    split = {"template": Counter(), "template_row": Counter()}
    for k in key:
        if k["source"] in split:
            split[k["source"]][graded[k["box_num"]]["grade"].strip()] += 1

    print("\nSTAGE FIVE RESULT, the one marked rule (protocol, R15)\n")
    for name, counts in split.items():
        total = sum(counts.values())
        if total:
            print(f"  {name:13s} hit {counts['hit']:2d}  near "
                  f"{counts['near']:2d}  miss {counts['miss']:2d}   "
                  f"(reported, governs nothing)")
    print(f"\n  located {located}/{len(rows)}  (snap {len(snap_boxes)}, "
          f"stack on the residue {sum(new_located.values())}/"
          f"{len(residue)})")
    print(f"  shipped comparator {COMPARATOR}/{len(rows)}")
    print(f"  McNemar b={b} c={c}, one-sided p = {p:.4f}")

    if located >= BAR_COUNT and p <= 0.05:
        print("\n  PASS. The template becomes the tier between snap and "
              "band, wired in under its own rule-5 proposal.")
    elif located <= DEAD_AT:
        print("\n  DEAD. The thread re-closes and the record states what "
              "the money bought.")
    else:
        print("\n  INCONCLUSIVE. The elected escape fires: the sheet "
              "extends to 1495195's 14 boxes and the 49-box bar of 38 "
              "governs, once, final either way.")

    fillers = [(k, graded[k["box_num"]]["grade"].strip()) for k in key
               if k["source"] == "model_filler"]
    agree = sum(1 for k, g in fillers
                if g == by_num[k["orig_box_num"]]["grade"])
    print(f"\n  consistency fillers: {agree}/{len(fillers)} agree with "
          "their stage-two grades (governs nothing)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true",
                    help="write the blinded stage-five grading sheet")
    ap.add_argument("--score", action="store_true",
                    help="score the graded sheet against the "
                         "pre-registered rule")
    args = ap.parse_args()

    print(f"STAGE FIVE, record {pb.TARGET[0]}\n")
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
