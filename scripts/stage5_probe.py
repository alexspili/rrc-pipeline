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
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import template as tpl              # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402
from scripts import probe_boxes as pb             # noqa: E402

TEMPLATES = ROOT / "pipeline" / "templates"

#: The stage-five rule's numbers, fixed in the protocol before the read.
BAR_COUNT, BAR_TOTAL = 26, 35
DEAD_AT = 21
COMPARATOR = 19


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


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    pdf, pages, report = pb.report_rows()
    rows = pb.graded_rows()
    snaps = pb.snap_outcomes()
    print(f"STAGE FIVE CEILING, record {pb.TARGET[0]}, "
          f"{len(rows)} graded boxes\n")

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


if __name__ == "__main__":
    main()
