#!/usr/bin/env python3
"""Build the stage-five multi-sample templates from cached Textract words.

Pre-registered in docs/labeling-protocol-extract.md under "Box grading,
stage five"; read that first. This is the build the one-sample probe could
not be: word boxes from Textract instead of the embedded layer, fuel pooled
across every corpus document whose extracted revision folds here, and the
anchor floor raised so that only what recurs across a quarter of the fuel
can pool. Registration itself is pipeline/template.py unchanged.

Declared here because they are choices, all fixed in the protocol before
the read:

- A template is built where at least FLOOR_PAGES pages register onto the
  seed; below that it abstains and the count is reported.
- The anchor membership floor is max(2, ceil(ANCHOR_FRACTION x fuel)).
- Seeds are deterministic: the labeled-revision page whose census part
  matches the role with the most unique Textract tokens.
- A spelling-variant revision (fewer documents than FLOOR_PAGES) folds into
  a template only if its pages register onto the seed. Folds are listed.
- The alias harvest (pipeline/textractwords.py) runs beside the build and
  its registration comparison is printed. Aliases are stored in the
  template JSON and consumed by NOTHING in the graded configuration.

Output: pipeline/templates/<class>_<revision>_<role>.json, committed after
the anchor token list is read by eye for anything name- or address-shaped
(CLAUDE.md rule 3; the scan is stated in the commit message).

No API calls. Every word box here was cached by scripts/textract_read.py.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import formlabels as fl              # noqa: E402
from pipeline import pageclass as pc               # noqa: E402
from pipeline import template as tpl               # noqa: E402
from pipeline import textractwords as tw           # noqa: E402
from pipeline.textlayer import page_words          # noqa: E402

CORPUS = ROOT / "data" / "extract" / "corpus.jsonl"
MANIFEST = ROOT / "data" / "manifest.jsonl"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
RAW = ROOT / "data" / "raw"
TEXTRACT = ROOT / "data" / "textract"
OUT = ROOT / "pipeline" / "templates"

#: Sealed: both records the stage-five rule can grade, whole (DEFECTS
#: #78). 1493608 has no Textract cache at all; 1495195 is cached but
#: contributes nothing, because the escape grades its page 15 and its
#: other filings would otherwise reach the rev7566 fuel. The tier-2 seal
#: test pins this against refactors.
EXCLUDED_RECORDS = frozenset({"1493608", "1495195"})

#: The templates stage five builds: the ones with field specs or a
#: pre-registered role in the sitting. Revisions with enough fuel but no
#: specs (rev61278 at 8 documents) wait for a number that says the
#: mechanism is worth extending.
BUILDS = (("w2", "rev7566", ("face", "sec_ii")),
          ("w2", "rev4183", ("face", "sec_ii")),
          ("g1", "rev4183", ("face",)),
          ("w2", "rev63075", ("face", "sec_ii")))

FLOOR_PAGES = 5
ANCHOR_FRACTION = 0.25

#: A pooled anchor whose centre spread exceeds this on either axis is
#: filling, not form (DEFECTS #77). Printed anchors on this fuel pool at
#: 0.002 to 0.004; typed county values, addresses and ZIPs at 0.013 to
#: 0.605. The bound is the one the stage-three diagnostic measured for
#: printed text. Filling that is homogeneous AND box-aligned (`brazoria`
#: at 0.013) still passes, and the defect entry characterises that residue
#: rather than claiming the separation is complete.
MAX_ANCHOR_SPREAD = 0.03


def spread_gate(anchors: dict, cap: float = MAX_ANCHOR_SPREAD) -> dict:
    return {t: a for t, a in anchors.items()
            if a.spread[0] <= cap and a.spread[1] <= cap}

ROLE_PARTS = {"face": {"face"}, "sec_ii": {"sec_ii", "continuation"}}


def manifest():
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def textract_index() -> dict[tuple[str, int, int], str]:
    out = {}
    for line in (TEXTRACT / "index.jsonl").open():
        if not line.strip():
            continue
        row = json.loads(line)
        out[(row["record_id"], row["file_index"], row["page"])] = row["sha256"]
    return out


def textract_words(index, key) -> list:
    digest = index.get(key)
    if digest is None:
        raise KeyError(f"no cached Textract response for {key}; "
                       "run scripts/textract_read.py first")
    response = json.loads((TEXTRACT / f"{digest[:16]}.json").read_text())
    return tw.words_only(response)


def census_parts() -> dict[tuple[str, int, int], str]:
    out = {}
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("form_class") not in ("g1", "w2"):
            continue
        out[pc.parse_page_id(row["page_id"])] = row.get("part")
    return out


def corpus_docs():
    """(form_class, revision_key, [(record, file, page), ...]) per doc."""
    out = []
    for line in CORPUS.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        if doc.get("form_class") not in ("g1", "w2"):
            continue
        record_id, file_index = doc["page_id"].rsplit("-", 2)[:2]
        if record_id in EXCLUDED_RECORDS:
            continue
        pages = [(record_id, int(file_index), int(p)) for p in doc["pages"]]
        out.append((doc["form_class"], tpl.revision_key(doc["form_revision"]),
                    pages))
    return out


def fit_to_seed(seed_unique, words):
    page = tpl.unique_tokens(words)
    pairs = [(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
              ((seed_unique[t][0] + seed_unique[t][2]) / 2,
               (seed_unique[t][1] + seed_unique[t][3]) / 2))
             for t, box in page.items() if t in seed_unique]
    if len(pairs) < tpl.MIN_ANCHORS:
        return len(pairs), None
    transform, residuals, _, _ = tpl.robust_fit(pairs)
    if transform is None:
        return len(pairs), None
    return len(pairs), statistics.median(residuals)


def registration_line(template, words):
    reg = tpl.register(template, words)
    if reg is None:
        return "refused"
    return f"{reg.matched} anchors at {reg.residual_median:.4f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revision", help="build only this revision key")
    args = ap.parse_args()

    records = manifest()
    index = textract_index()
    parts = census_parts()
    docs = corpus_docs()
    OUT.mkdir(parents=True, exist_ok=True)

    exact_keys = {(c, r) for c, r, _ in BUILDS}
    class_counts = Counter((c, r) for c, r, _ in docs)

    for form_class, revision, roles in BUILDS:
        if args.revision and revision != args.revision:
            continue
        labeled = [pages for c, r, pages in docs
                   if c == form_class and r == revision]
        # variant candidates: same class, a key too thin to stand alone,
        # and not another template's exact key
        variants = [(r, pages) for c, r, pages in docs
                    if c == form_class and (c, r) not in exact_keys
                    and r != "unknown" and class_counts[(c, r)] < FLOOR_PAGES]
        print(f"\n=== {form_class} {revision}: {len(labeled)} labeled "
              f"documents, {len(variants)} variant candidates ===")

        labeled_pages = [key for pages in labeled for key in pages]
        variant_pages = [(r, key) for r, pages in variants for key in pages]

        for role in roles:
            wanted = ROLE_PARTS[role]
            seed_pool = [key for key in labeled_pages
                         if parts.get(key) in wanted and key in index]
            if not seed_pool:
                print(f"  {role}: no census-part page to seed from, "
                      "template abstains")
                continue
            seed_key = max(seed_pool, key=lambda k: len(
                tpl.unique_tokens(textract_words(index, k))))
            seed_words = textract_words(index, seed_key)
            seed_unique = tpl.unique_tokens(seed_words)
            print(f"  {role}: seed {seed_key[0]}-{seed_key[1]} "
                  f"p{seed_key[2]}, {len(seed_unique)} unique tokens")

            fuel, folds = [], Counter()
            for key in labeled_pages:
                if key == seed_key or key not in index:
                    continue
                shared, residual = fit_to_seed(
                    seed_unique, textract_words(index, key))
                if residual is not None and residual <= tpl.MAX_RESIDUAL:
                    fuel.append(key)
            for variant_rev, key in variant_pages:
                if key not in index:
                    continue
                shared, residual = fit_to_seed(
                    seed_unique, textract_words(index, key))
                if residual is not None and residual <= tpl.MAX_RESIDUAL:
                    fuel.append(key)
                    folds[variant_rev] += 1
            fuel = [seed_key] + fuel
            assert all(k[0] not in EXCLUDED_RECORDS for k in fuel)
            print(f"    fuel: {len(fuel)} pages registered onto the seed"
                  + (f"; folds: {dict(folds)}" if folds else "; folds: none"))
            stale = OUT / f"{form_class}_{revision}_{role}.json"
            if len(fuel) < FLOOR_PAGES:
                print(f"    ABSTAINS: fewer than {FLOOR_PAGES} pages")
                if stale.exists():
                    # an abstention must take its previous build with it,
                    # or a sealed record lives on in a file the build no
                    # longer writes (DEFECTS #78)
                    stale.unlink()
                    print(f"    removed stale {stale.relative_to(ROOT)}")
                continue

            floor = max(2, math.ceil(ANCHOR_FRACTION * len(fuel)))
            fuel_words = [textract_words(index, k) for k in fuel]
            pooled, used, rejected = tpl.build_anchors(fuel_words,
                                                       min_pages=floor)
            anchors = spread_gate(pooled)
            heights = sorted(tpl.line_height(w) for w in fuel_words)
            height = heights[len(heights) // 2]
            print(f"    anchor floor {floor} of {len(fuel)} pages: "
                  f"{len(pooled)} pooled, {len(pooled) - len(anchors)} "
                  f"gated as filling (spread > {MAX_ANCHOR_SPREAD}), "
                  f"{len(anchors)} canonical anchors, "
                  f"{len(rejected)} pages rejected in pooling")

            key3 = (form_class, revision, role)
            specs = fl.LABELS.get(key3, {})
            banned = tpl.shared_label_tokens(specs) | set(
                fl.DECOYS.get(key3, ()))
            top, bottom = fl.BODY.get(key3, (0.0, 1.0))
            body = {n: a for n, a in anchors.items()
                    if top <= a.centre[1] <= bottom}
            located, abstained = {}, []
            for name, spec in specs.items():
                label = tpl.resolve_label(body, spec.tokens, banned,
                                          spec.checkbox)
                region = (tpl.value_region(anchors, label, height,
                                           spec.checkbox)
                          if label is not None else None)
                if region is None:
                    abstained.append(name)
                else:
                    located[name] = region
            heads = {}
            for table, tokens in fl.BLOCKS.get(key3, {}).items():
                head = tpl.resolve_label(body, tokens, set())
                if head is not None:
                    heads[table] = head
            blocks = tpl.block_region(anchors, heads, height)
            if specs:
                print(f"    fields located {len(located)}/{len(specs)}, "
                      f"blocks {len(blocks)}/"
                      f"{len(fl.BLOCKS.get(key3, {}))}")
                for name in sorted(abstained):
                    print(f"      - {name} abstained")
            else:
                print("    no field specs for this key yet; anchors only")

            # alias harvest, and the free registration comparison
            merged: dict[str, Counter] = defaultdict(Counter)
            for key in fuel:
                pdf = (RAW / key[0]
                       / records[key[0]]["files"][key[1]]["name"])
                for token, spelling in tw.harvest_aliases(
                        textract_words(index, key),
                        page_words(pdf, key[2])).items():
                    if token in anchors:
                        merged[token][spelling] += 1
            template = tpl.Template(
                revision=revision, form_class=form_class, page_role=role,
                anchors=anchors, fields=located, line_height=height,
                built_from=[f"{r}-{f}-{p}" for r, f, p in fuel])
            expanded = tpl.Template(
                revision=revision, form_class=form_class, page_role=role,
                anchors=tw.expand_anchors(
                    anchors, {t: list(c) for t, c in merged.items()}),
                line_height=height)
            exact_ok = alias_ok = 0
            for key in fuel:
                pdf = (RAW / key[0]
                       / records[key[0]]["files"][key[1]]["name"])
                embedded = page_words(pdf, key[2])
                a = tpl.register(template, embedded)
                b = tpl.register(expanded, embedded)
                exact_ok += a is not None
                alias_ok += b is not None
            print(f"    aliases: {sum(len(c) for c in merged.values())} "
                  f"spellings over {len(merged)} anchors")
            print(f"    embedded-layer registration of the fuel pages: "
                  f"exact {exact_ok}/{len(fuel)}, "
                  f"alias-augmented {alias_ok}/{len(fuel)} "
                  "(reported, governs nothing)")

            path = OUT / f"{form_class}_{revision}_{role}.json"
            path.write_text(json.dumps({
                "revision": revision, "form_class": form_class,
                "page_role": role, "line_height": height,
                "word_source": "textract",
                "anchor_floor": floor, "fuel_pages": len(fuel),
                "folds": dict(folds),
                "built_from": template.built_from,
                "anchors": {t: {"box": list(a.box), "pages": a.pages,
                                "spread": list(a.spread)}
                            for t, a in anchors.items()},
                "fields": {n: list(b) for n, b in located.items()},
                "blocks": {n: list(b) for n, b in blocks.items()},
                "abstained": sorted(abstained),
                "aliases": {t: dict(c) for t, c in sorted(merged.items())},
            }, indent=2) + "\n")
            print(f"    wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
