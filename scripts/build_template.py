#!/usr/bin/env python3
"""Build a per-revision form template from the corpus's own text layer.

The probe this serves is pre-registered in docs/labeling-protocol-extract.md
under "Box grading, stage three". Read that before reading this.

Fuel discovery, declared here because the threshold is a choice. The smoke
set holds four Rev. 7/5/66 documents and one of them is the graded target, so
pooling from the smoke set alone would leave the reverse-side template with a
single page, which is a copy of one document rather than a template. The
corpus has 166 W-2 faces, 31 Section II pages and 33 continuations that the
census already classified, and `pdftotext` over them is free.

**Discovery is by registration, not by token count.** The first attempt
scored a candidate on how many normalised tokens it shared with a seed page
of the revision. That does not separate revisions: these forms keep the same
masthead, the same instructions and the same affidavit across revisions, so
the top-scoring Section II candidates included records the smoke run knows
are Rev. 4/1/83. A shared-token count answers "is this a W-2 reverse", which
is the question the census already answered.

So a candidate joins the fuel when its unique tokens can be registered onto
the seed's: at least MIN_ANCHORS shared unique tokens, and a median residual
at or below --max-residual after one round of outlier trimming. A page of a
different revision has its fields in different places and does not fit. This
is also the instrument the mechanism would need at runtime to recognise a
page's revision, so the probe tests it here rather than assuming it.

The rule is checked against labels rather than trusted: the smoke run records
a form_revision for twenty documents, and any discovered page belonging to
one of those records is compared against it. Disagreements are printed.

**Record 1493608 is excluded everywhere, unconditionally.** It is the graded
document and the probe scores against it. The exclusion is asserted rather
than assumed, because a leak here would make every number that follows
meaningless and would not look like an error.

Selecting fuel is engineering rather than outcome tuning: the graded document
is sealed and the grades are made blind. The threshold and the resulting pool
size are both reported so the choice is visible.

No API calls, no cost.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import formlabels as fl             # noqa: E402
from pipeline import pageclass as pc              # noqa: E402
from pipeline import template as tpl              # noqa: E402
from pipeline.textlayer import norm, page_words   # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
OUT = ROOT / "data" / "extract" / "templates"

#: Sealed. The graded document never contributes to the template that scores
#: against it.
EXCLUDED_RECORDS = frozenset({"1493608"})

#: Seed pages: one known page per (revision, role), from the smoke run.
SEEDS = {("w2", "rev7566", "face"): ("1494690", 0, 9),
         ("w2", "rev7566", "sec_ii"): ("1494690", 0, 10)}

#: Census classes that could hold a page of each role.
ROLE_CLASSES = {"face": {("w2", "face")},
                "sec_ii": {("w2", "sec_ii"), ("w2", "continuation")}}


def manifest():
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def pdf_for(records, record_id: str, file_index: int) -> Path:
    return RAW / record_id / records[record_id]["files"][file_index]["name"]


def token_set(words) -> set[str]:
    return {norm(w[4]) for w in words
            if len(norm(w[4])) >= tpl.MIN_ANCHOR_CHARS}


def fit_to_seed(seed_unique, words):
    """(shared anchors, median residual) for a candidate against the seed."""
    page = tpl.unique_tokens(words)
    pairs = []
    for token, box in seed_unique.items():
        other = page.get(token)
        if other is None:
            continue
        pairs.append((((other[0] + other[2]) / 2, (other[1] + other[3]) / 2),
                      ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)))
    if len(pairs) < tpl.MIN_ANCHORS:
        return len(pairs), None
    transform, residuals, _, _ = tpl.robust_fit(pairs)
    if transform is None:
        return len(pairs), None
    import statistics
    return len(pairs), statistics.median(residuals)


def known_revisions():
    """form_revision per record, from the finished smoke run: labels the
    discovery rule can be checked against rather than trusted."""
    path = ROOT / "data" / "extract" / "smoke.jsonl"
    out = {}
    for line in path.open():
        if not line.strip():
            continue
        row = json.loads(line)
        record_id = row["page_id"].rsplit("-", 2)[0]
        out[record_id] = tpl.revision_key(row.get("form_revision"))
    return out


def candidates(role: str):
    """Census pages that could be this role, minus the sealed record."""
    out = []
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (row.get("form_class"), row.get("part"))
        if key not in ROLE_CLASSES[role]:
            continue
        record_id, file_index, page = pc.parse_page_id(row["page_id"])
        if record_id in EXCLUDED_RECORDS:
            continue
        out.append((record_id, file_index, page))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revision", default="rev7566")
    ap.add_argument("--form-class", default="w2")
    ap.add_argument("--min-shared", type=int, default=tpl.MIN_ANCHORS,
                    help="shared unique tokens a candidate needs to register")
    ap.add_argument("--max-residual", type=float, default=tpl.MAX_RESIDUAL,
                    help="median registration residual, in page fractions")
    ap.add_argument("--report-only", action="store_true",
                    help="print the fuel-score distribution and stop")
    args = ap.parse_args()

    records = manifest()
    OUT.mkdir(parents=True, exist_ok=True)

    for role in ("face", "sec_ii"):
        key = (args.form_class, args.revision, role)
        seed_id = SEEDS.get(key)
        if seed_id is None:
            continue
        assert seed_id[0] not in EXCLUDED_RECORDS, "seed leaks the target"
        seed_words = page_words(pdf_for(records, seed_id[0], seed_id[1]),
                                seed_id[2])
        seed_tokens = token_set(seed_words)
        print(f"\n=== {args.form_class} {args.revision} {role} ===")
        print(f"  seed {seed_id[0]} p{seed_id[2]}: "
              f"{len(seed_words)} words, {len(seed_tokens)} tokens")

        seed_unique = tpl.unique_tokens(seed_words)
        labels = known_revisions()

        scored = []
        for record_id, file_index, page in candidates(role):
            pdf = pdf_for(records, record_id, file_index)
            if not pdf.exists():
                continue
            words = page_words(pdf, page)
            shared, residual = fit_to_seed(seed_unique, words)
            scored.append((shared, residual, record_id, file_index, page,
                           words))
        registrable = [row for row in scored if row[1] is not None]
        registrable.sort(key=lambda row: row[1])
        print(f"  {len(scored)} candidate pages, {len(registrable)} with at "
              f"least {tpl.MIN_ANCHORS} shared unique tokens")
        histogram: Counter = Counter()
        for row in registrable:
            histogram[min(int(row[1] * 1000), 60) // 5 * 5] += 1
        print("  median registration residual against the seed, x1000:")
        for bucket in sorted(histogram):
            label = f"{bucket}-{bucket + 4}" if bucket < 60 else "60+"
            print(f"    {label:>7s} {histogram[bucket]:4d}")
        print("  closest: " + ", ".join(
            f"{row[2]}p{row[4]}({row[1] * 1000:.1f})"
            for row in registrable[:10]))

        fuel = [row for row in registrable
                if row[0] >= args.min_shared and row[1] <= args.max_residual]
        assert all(row[2] not in EXCLUDED_RECORDS for row in fuel)
        print(f"  fuel at residual <= {args.max_residual}: {len(fuel)} pages")
        checked = [(row[2], labels[row[2]]) for row in fuel
                   if row[2] in labels]
        wrong = [r for r, rev in checked if rev != args.revision
                 and rev != "unknown"]
        print(f"  of those, {len(checked)} belong to records whose revision "
              f"the smoke run recorded; {len(wrong)} disagree"
              + (f" ({', '.join(sorted(set(wrong)))})" if wrong else ""))
        if len(fuel) < 2:
            print("  REFUSING to build: fewer than two pages is not a "
                  "template, it is a copy of one document")
            continue

        anchors, used, rejected = tpl.build_anchors([row[5] for row in fuel])
        heights = [tpl.line_height(row[5]) for row in fuel]
        height = sorted(heights)[len(heights) // 2]
        template = tpl.Template(
            revision=args.revision, form_class=args.form_class,
            page_role=role, anchors=anchors, line_height=height,
            built_from=[f"{row[2]}-{row[3]}-{row[4]}" for row in fuel],
            rejected=[f"{fuel[i][2]}-{fuel[i][3]}-{fuel[i][4]}"
                      for i in rejected])
        print(f"  registered {len(used)}/{len(fuel)} pages, "
              f"rejected {len(rejected)}")
        print(f"  canonical anchors: {len(anchors)}  "
              f"(line height {height:.4f})")

        specs = fl.LABELS.get(key, {})
        banned = (tpl.shared_label_tokens(specs)
                  | set(fl.DECOYS.get(key, ())))
        top, bottom = fl.BODY.get(key, (0.0, 1.0))
        body = {name: a for name, a in anchors.items()
                if top <= a.centre[1] <= bottom}
        print(f"  anchors in the field body ({top}-{bottom}): {len(body)}; "
              f"banned tokens: {len(banned)}")

        located, abstained = {}, []
        for name, spec in specs.items():
            label = tpl.resolve_label(body, spec.tokens, banned,
                                      spec.checkbox)
            if label is None:
                abstained.append(name)
                continue
            region = tpl.value_region(anchors, label, height, spec.checkbox)
            if region is None:
                abstained.append(name)
                continue
            located[name] = region
        heads = {}
        for table, tokens in fl.BLOCKS.get(key, {}).items():
            head = tpl.resolve_label(body, tokens, set())
            if head is not None:
                heads[table] = head
        blocks = tpl.block_region(anchors, heads, height)
        template.fields = located

        print(f"  fields located {len(located)}/{len(specs)}, "
              f"abstained {len(abstained)}")
        for name, box in sorted(located.items()):
            print(f"    + {name:34s} "
                  f"({box[0]:.3f}, {box[1]:.3f}, {box[2]:.3f}, {box[3]:.3f})")
        for name in sorted(abstained):
            print(f"    - {name:34s} abstained")
        print(f"  table blocks located {len(blocks)}/"
              f"{len(fl.BLOCKS.get(key, {}))}")
        for name, box in sorted(blocks.items()):
            print(f"    + {name:34s} "
                  f"({box[0]:.3f}, {box[1]:.3f}, {box[2]:.3f}, {box[3]:.3f})")

        path = OUT / f"{args.form_class}_{args.revision}_{role}.json"
        path.write_text(json.dumps({
            "revision": template.revision, "form_class": template.form_class,
            "page_role": role, "line_height": height,
            "built_from": template.built_from, "rejected": template.rejected,
            "anchors": {t: {"box": list(a.box), "pages": a.pages,
                            "spread": list(a.spread)}
                        for t, a in anchors.items()},
            "fields": {n: list(b) for n, b in located.items()},
            "blocks": {n: list(b) for n, b in blocks.items()},
            "abstained": sorted(abstained),
        }, indent=2) + "\n")
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
