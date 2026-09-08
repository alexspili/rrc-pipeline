#!/usr/bin/env python3
"""The alias adoption probe: exact-token against alias-augmented routing.

Pre-registered in docs/labeling-protocol-extract.md, "Alias-augmented
registration: the adoption rule". Every g1/w2 corpus page, sealed records
excluded, routed twice through the wired templatetier machinery. The
registration gates are identical in both arms; only the matchable
vocabulary differs, and every alias was observed on paper at its
anchor's position during the stage-five build.

No API calls, no cost.
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

from pipeline import template as tpl               # noqa: E402
from pipeline import templatetier as tt            # noqa: E402
from pipeline import textractwords as tw           # noqa: E402
from pipeline.textlayer import page_words          # noqa: E402
from scripts.stage5_templates import (             # noqa: E402
    corpus_docs, manifest)

RAW = ROOT / "data" / "raw"

#: The gain floor and the rule live in the protocol; restated here so the
#: verdict prints beside its bar.
GAIN_FLOOR = 5


def alias_artifacts() -> dict:
    """The wired artifacts with anchor tables expanded by stored aliases."""
    out = {}
    for key, artifact in tt.load_artifacts().items():
        path = (tt.TEMPLATES
                / f"{key[0]}_{key[1]}_{key[2]}.json")
        raw = json.loads(path.read_text())
        aliases = {token: list(spellings)
                   for token, spellings in raw.get("aliases", {}).items()}
        expanded = tpl.Template(
            revision=artifact.template.revision,
            form_class=artifact.template.form_class,
            page_role=artifact.template.page_role,
            anchors=tw.expand_anchors(artifact.template.anchors, aliases),
            line_height=artifact.template.line_height)
        out[key] = tt.Artifact(template=expanded, fields=artifact.fields,
                               blocks=artifact.blocks, rows=artifact.rows,
                               header_rows=artifact.header_rows)
    return out


def folds() -> dict[str, str]:
    """Variant revision keys the committed builds folded, as agreement."""
    out = {}
    for path in tt.TEMPLATES.glob("*.json"):
        if path.stem.endswith("_forms"):
            continue
        raw = json.loads(path.read_text())
        for variant in raw.get("folds", {}):
            out[variant] = raw["revision"]
    return out


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    records = manifest()
    exact = tt.load_artifacts()
    augmented = alias_artifacts()
    fold = folds()
    committed = {key[1] for key in exact}

    gain, lost = [], []
    agree = {"exact": Counter(), "alias": Counter()}
    changed = []
    residuals = {"exact": [], "alias": []}
    unknown = {"exact": 0, "alias": 0}
    residue = 0

    for form_class, revision, pages in corpus_docs():
        known = (revision in committed or fold.get(revision) in committed)
        for record_id, file_index, page in pages:
            pdf = (RAW / record_id
                   / records[record_id]["files"][file_index]["name"])
            if not pdf.exists():
                continue
            words = page_words(pdf, page)
            raw_revision = revision if revision != "unknown" else None
            routes = {}
            for arm, artifacts in (("exact", exact), ("alias", augmented)):
                routed = tt.route(artifacts, form_class, raw_revision,
                                  words)
                routes[arm] = routed
                if routed is not None:
                    residuals[arm].append(routed[1].residual_median)
                    if revision == "unknown":
                        unknown[arm] += 1
                    if known:
                        routed_rev = routed[0][1]
                        ok = routed_rev in (revision, fold.get(revision))
                        agree[arm]["agree" if ok else "disagree"] += 1
            page_name = f"{record_id}-{file_index} p{page}"
            if routes["exact"] is None and routes["alias"] is not None:
                gain.append((page_name, revision, routes["alias"][0]))
            if routes["exact"] is not None and routes["alias"] is None:
                lost.append((page_name, revision, routes["exact"][0]))
            if (routes["exact"] and routes["alias"]
                    and routes["exact"][0] != routes["alias"][0]):
                changed.append((page_name, revision, routes["exact"][0],
                                routes["alias"][0]))
            if routes["exact"] is None and routes["alias"] is None:
                residue += 1

    print("ALIAS ADOPTION PROBE, both arms through the identical gates\n")
    print(f"  pages exact refuses and aliases route: {len(gain)}  "
          f"(bar: at least {GAIN_FLOOR})")
    for page_name, revision, key in gain:
        print(f"    + {page_name:22s} labeled {revision:12s} -> "
              f"{'_'.join(key)}")
    for page_name, revision, key in lost:
        print(f"    - LOST {page_name} ({revision}); aliases must not "
              "remove a registration and this needs reading")
    rates = {}
    for arm in ("exact", "alias"):
        total = sum(agree[arm].values())
        rates[arm] = agree[arm]["agree"] / total if total else 0.0
        print(f"  {arm:6s}: known-revision routed pages {total}, "
              f"agreement {rates[arm]:.1%}")
    if changed:
        print("  routes that changed arm to arm, each one read (R14):")
        for page_name, revision, before, after in changed:
            print(f"    {page_name}: {'_'.join(before)} -> "
                  f"{'_'.join(after)} (labeled {revision})")
    for arm in ("exact", "alias"):
        if residuals[arm]:
            print(f"  {arm} residuals: median "
                  f"{statistics.median(residuals[arm]):.4f}, "
                  f"max {max(residuals[arm]):.4f}, "
                  f"n {len(residuals[arm])}")
    print(f"  unknown-revision pages routed: exact {unknown['exact']}, "
          f"alias {unknown['alias']}")
    print(f"  residue neither arm registers: {residue} pages "
          "(the number any LLM argument starts from)")

    passed = len(gain) >= GAIN_FLOOR and rates["alias"] >= rates["exact"]
    print("\nPRE-REGISTERED RULE: adopt iff gain >= "
          f"{GAIN_FLOOR} AND alias agreement >= exact agreement")
    print(f"  -> {'ADOPT' if passed else 'DO NOT ADOPT'}")


if __name__ == "__main__":
    main()
