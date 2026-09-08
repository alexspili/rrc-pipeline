#!/usr/bin/env python3
"""Assignment by registration residual: which template serves a page.

Pre-registered in docs/labeling-protocol-extract.md, "Box grading, stage
five": a page is assigned to the lowest-residual template only if that
residual clears MAX_RESIDUAL (0.010) and the next-best candidate is at
least MARGIN times worse. Anything else abstains and keeps snap-plus-band.
Every number here is REPORTED AND GOVERNS NOTHING; the graded sitting is
the gate.

Two populations, reported separately and never blended:

- Known-revision pages, as a label check: mask the extracted revision,
  assign, compare. The caveat travels with the number: most of these
  pages are IN the fuel of the template they should be assigned to, so
  their agreement is inflated by construction. It can falsify the
  mechanism; it cannot confirm it.
- Unknown-revision pages, the 58 documents the mechanism exists for.
  These are in no template's fuel, so their residuals and margins are the
  honest evidence.

Registration is the shipping configuration: embedded-layer words,
exact-token, no aliases. No API calls, no cost.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import template as tpl              # noqa: E402
from pipeline.textlayer import page_words         # noqa: E402
from scripts.stage5_templates import (            # noqa: E402
    corpus_docs, manifest)

TEMPLATES = ROOT / "pipeline" / "templates"

MARGIN = 2.0


def load_templates():
    out = {}
    for path in sorted(TEMPLATES.glob("*.json")):
        raw = json.loads(path.read_text())
        anchors = {t: tpl.Anchor(t, tuple(v["box"]), v["pages"],
                                 tuple(v["spread"]))
                   for t, v in raw["anchors"].items()}
        out[path.stem] = (raw["form_class"], raw["revision"],
                          tpl.Template(
                              revision=raw["revision"],
                              form_class=raw["form_class"],
                              page_role=raw["page_role"], anchors=anchors,
                              line_height=raw["line_height"]))
    return out


def assign(templates, words):
    """(name, residual, margin_ok) for the best-fitting template, or None."""
    fits = []
    for name, (_, _, template) in templates.items():
        reg = tpl.register(template, words)
        if reg is not None:
            fits.append((reg.residual_median, name))
    if not fits:
        return None
    fits.sort()
    best_residual, best_name = fits[0]
    if best_residual > tpl.MAX_RESIDUAL:
        return None
    margin_ok = (len(fits) == 1
                 or fits[1][0] >= MARGIN * best_residual)
    return best_name, best_residual, margin_ok


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    records = manifest()
    templates = load_templates()
    fuel_pages = set()
    for path in TEMPLATES.glob("*.json"):
        for page_id in json.loads(path.read_text())["built_from"]:
            r, f, p = page_id.rsplit("-", 2)
            fuel_pages.add((r, int(f), int(p)))

    print(f"ASSIGNMENT BY RESIDUAL, {len(templates)} templates, "
          f"margin {MARGIN}x, gate {tpl.MAX_RESIDUAL}\n")

    known = Counter()
    unknown = Counter()
    unknown_residuals = []
    disagreements = []
    for form_class, revision, pages in corpus_docs():
        for key in pages:
            record_id, file_index, page = key
            pdf = (ROOT / "data" / "raw" / record_id
                   / records[record_id]["files"][file_index]["name"])
            if not pdf.exists():
                continue
            verdict = assign(templates, page_words(pdf, page))
            if revision == "unknown":
                if verdict is None:
                    unknown["no_fit"] += 1
                elif not verdict[2]:
                    unknown["margin_abstain"] += 1
                else:
                    unknown[verdict[0]] += 1
                    unknown_residuals.append(verdict[1])
            else:
                if verdict is None or not verdict[2]:
                    known["abstain"] += 1
                    continue
                name = verdict[0]
                assigned = (templates[name][0], templates[name][1])
                tag = "fuel" if key in fuel_pages else "held_out"
                if assigned == (form_class, revision):
                    known[f"agree_{tag}"] += 1
                else:
                    known[f"disagree_{tag}"] += 1
                    disagreements.append(
                        (record_id, page, form_class, revision, name))

    print("KNOWN-REVISION PAGES (label check; fuel rows are inflated by "
          "construction)")
    for outcome, count in sorted(known.items()):
        print(f"  {outcome:20s} {count:4d}")

    print("\nUNKNOWN-REVISION PAGES (the mechanism's own population)")
    for outcome, count in sorted(unknown.items()):
        print(f"  {outcome:24s} {count:4d}")
    if unknown_residuals:
        print(f"  assigned residuals: median "
              f"{statistics.median(unknown_residuals):.4f}, "
              f"max {max(unknown_residuals):.4f}")

    if disagreements:
        print("\nDISAGREEMENTS, each one read rather than counted (R14)")
        for record_id, page, form_class, revision, name in disagreements:
            print(f"  {record_id} p{page}: labeled {form_class} {revision}, "
                  f"assigned {name}")


if __name__ == "__main__":
    main()
