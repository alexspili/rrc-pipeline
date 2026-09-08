#!/usr/bin/env python3
"""Build stage-six geometry: pooled Forms cells and measured table rows.

Pre-registered in docs/labeling-protocol-extract.md, "Box grading, stage
six". This build changes GEOMETRY only: registration, anchors and the
graded configuration's matching all stay stage five's. Per field, the
pooled Forms-derived cell where detected keys match the field's spec
tokens; else the stage-five region stands. Per table, measured row edges
where Tables detects the grid; else the equal-band guess stands. Output
is written BESIDE the stage-five artifacts, never over them.

The pooling discipline is the anchor discipline, applied to keys:

- A page contributes a field only when EXACTLY ONE detected key matches
  every spec token (a tie on a page is that page abstaining, which is how
  the two `date` fields stay honest rather than guessed).
- A field pools only when at least 25% of the analyzed fuel pages
  contribute, minimum 2, and the pooled centres sit within the same 0.03
  spread the anchor gate uses (DEFECTS #77's bound).
- Pooled positions are medians, in the template frame, reached through
  each page's own Textract-word registration onto the stage-five anchors.

Committed artifacts carry geometry, field names, source tags and pooled
KEY text (printed labels, scanned under rule 3 like every anchor list).
Value text stays in the git-ignored cache. No API calls, no cost.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import formlabels as fl              # noqa: E402
from pipeline import template as tpl               # noqa: E402
from pipeline import textractforms as tf           # noqa: E402
from pipeline.textlayer import norm                # noqa: E402
from scripts.stage5_templates import (             # noqa: E402
    ANCHOR_FRACTION, EXCLUDED_RECORDS, MAX_ANCHOR_SPREAD, textract_index,
    textract_words)

TEMPLATES = ROOT / "pipeline" / "templates"
ANALYZE = ROOT / "data" / "textract" / "analyze"

MATCH_RATIO = tpl.LABEL_RATIO
TABLE_MIN_IOU = 0.3


def analyze_index() -> dict[tuple[str, int, int], str]:
    out = {}
    index = ANALYZE / "index.jsonl"
    if not index.exists():
        return out
    for line in index.open():
        if not line.strip():
            continue
        row = json.loads(line)
        out[(row["record_id"], row["file_index"], row["page"])] = row["sha256"]
    return out


def analyze_response(index, key) -> dict:
    digest = index.get(key)
    if digest is None:
        raise KeyError(f"no cached AnalyzeDocument response for {key}; "
                       "run scripts/textract_analyze.py first")
    return json.loads((ANALYZE / f"{digest[:16]}.json").read_text())


def load_stage5(path: Path):
    raw = json.loads(path.read_text())
    anchors = {t: tpl.Anchor(t, tuple(v["box"]), v["pages"],
                             tuple(v["spread"]))
               for t, v in raw["anchors"].items()}
    template = tpl.Template(
        revision=raw["revision"], form_class=raw["form_class"],
        page_role=raw["page_role"], anchors=anchors,
        line_height=raw["line_height"], built_from=raw["built_from"])
    template.fields = {n: tuple(b) for n, b in raw["fields"].items()}
    return raw, template


def key_tokens(text: str) -> list[str]:
    return [norm(part) for part in text.split()
            if len(norm(part)) >= tpl.MIN_ANCHOR_CHARS]


def match_field(pairs: list[tf.KeyValue], spec) -> tf.KeyValue | None:
    """The one detected key matching every spec token, else None.

    Zero matches and two matches are the same answer: this page says
    nothing about this field. Never nearest, same as everywhere else.
    """
    wanted = [t for t in spec.tokens if len(t) >= tpl.MIN_ANCHOR_CHARS]
    if not wanted:
        return None
    matched = []
    for pair in pairs:
        have = key_tokens(pair.key_text)
        if all(any(tpl._ratio(w, h) >= MATCH_RATIO for h in have)
               for w in wanted):
            matched.append(pair)
    return matched[0] if len(matched) == 1 else None


def pool_boxes(boxes: list[tuple[float, float, float, float]],
               floor: int, max_spread: float = MAX_ANCHOR_SPREAD):
    """Median box if enough pages agree tightly, else None."""
    if len(boxes) < floor:
        return None
    centres_x = [(b[0] + b[2]) / 2 for b in boxes]
    centres_y = [(b[1] + b[3]) / 2 for b in boxes]
    if (max(centres_x) - min(centres_x) > max_spread
            or max(centres_y) - min(centres_y) > max_spread):
        return None
    return tuple(statistics.median(b[i] for b in boxes) for i in range(4))


def _iou(a, b) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    return inter / ((a[2] - a[0]) * (a[3] - a[1])
                    + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def field_region(key_box, value_box):
    """The cell: key and pooled value zone together, capped like every
    other asserted region so nothing scores by drawing large."""
    boxes = [key_box] + ([value_box] if value_box else [])
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = min(max(b[2] for b in boxes), left + tpl.MAX_REGION_WIDTH)
    bottom = min(max(b[3] for b in boxes), top + tpl.MAX_REGION_HEIGHT)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def row_edges(grids: list[list[tuple[int, tuple, str]]], floor: int):
    """(pooled per-row boxes, leading header rows), or None.

    Pools where enough pages agree on the row count. Header rows are
    found by the stage's own principle: a row whose text is identical
    across most pages is printed, a row whose text varies is filling.
    The probe maps extracted row k past the headers; guessing an offset
    would be the equal-band rule wearing a hat.
    """
    counts = [max(r for r, _, _ in grid) for grid in grids if grid]
    if not counts:
        return None
    modal = statistics.mode(counts)
    agreeing = [grid for grid in grids
                if grid and max(r for r, _, _ in grid) == modal]
    if len(agreeing) < floor:
        return None
    rows, header_rows, still_leading = [], 0, True
    for index in range(1, modal + 1):
        per_page, texts = [], []
        for grid in agreeing:
            cells = [(box, text) for r, box, text in grid if r == index]
            if cells:
                per_page.append((min(b[0] for b, _ in cells),
                                 min(b[1] for b, _ in cells),
                                 max(b[2] for b, _ in cells),
                                 max(b[3] for b, _ in cells)))
                texts.append(norm(" ".join(t for _, t in cells)))
        pooled = pool_boxes(per_page, max(2, len(agreeing) // 2))
        if pooled is None:
            return None
        rows.append(pooled)
        # printed means recurring, and on this paper recurrence is fuzzy:
        # the 1966 casing header reads differently on every page, so
        # exact equality called it filling and mapped data row 0 onto
        # the header row. Same 0.80 ratio as every other match here.
        recurring = (texts and texts[0] != ""
                     and sum(1 for t in texts
                             if tpl._ratio(t, texts[0]) >= MATCH_RATIO)
                     > len(texts) / 2)
        if still_leading and recurring:
            header_rows += 1
        else:
            still_leading = False
    return rows, header_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revision", help="build only this revision key")
    args = ap.parse_args()

    detect = textract_index()
    analyze = analyze_index()

    for path in sorted(TEMPLATES.glob("*.json")):
        if path.stem.endswith("_forms"):
            continue
        raw, template = load_stage5(path)
        if args.revision and raw["revision"] != args.revision:
            continue
        key3 = (raw["form_class"], raw["revision"], raw["page_role"])
        specs = fl.LABELS.get(key3, {})
        print(f"\n=== {path.stem} ===")

        fuel, skipped = [], 0
        for page_id in raw["built_from"]:
            record_id, file_index, page = page_id.rsplit("-", 2)
            key = (record_id, int(file_index), int(page))
            assert record_id not in EXCLUDED_RECORDS
            if key not in analyze:
                skipped += 1
                continue
            words = textract_words(detect, key)
            reg = tpl.register(template, words)
            if reg is None:
                skipped += 1
                continue
            response = analyze_response(analyze, key)
            fuel.append((key, reg, tf.key_values(response),
                         tf.tables(response)))
        floor = max(2, math.ceil(ANCHOR_FRACTION * len(fuel)))
        print(f"  analyzed fuel: {len(fuel)} pages registered "
              f"({skipped} skipped), pooling floor {floor}")
        if len(fuel) < 2:
            print("  ABSTAINS: not enough analyzed fuel")
            continue

        detected = statistics.median(len(pairs) for _, _, pairs, _ in fuel)
        print(f"  keys detected per page: median {detected:.0f}")

        fields, key_texts, contributions = {}, {}, {}
        for name, spec in specs.items():
            keys_f, values_f, texts = [], [], []
            for _, reg, pairs, _ in fuel:
                pair = match_field(pairs, spec)
                if pair is None:
                    continue
                keys_f.append(reg.transform.box(pair.key_box))
                if pair.value_box is not None:
                    values_f.append(reg.transform.box(pair.value_box))
                texts.append(pair.key_text)
            pooled_key = pool_boxes(keys_f, floor)
            if pooled_key is None:
                continue
            pooled_value = pool_boxes(values_f, max(2, floor // 2),
                                      max_spread=0.10)
            region = field_region(pooled_key, pooled_value)
            if region is None:
                continue
            fields[name] = region
            key_texts[name] = max(set(texts), key=texts.count)
            contributions[name] = len(keys_f)

        blocks_rows, headers = {}, {}
        stage5_blocks = {n: tuple(b) for n, b in raw["blocks"].items()}
        for block_name, block_box in stage5_blocks.items():
            grids = []
            for _, reg, _, page_tables in fuel:
                best, best_iou = None, TABLE_MIN_IOU
                for table in page_tables:
                    iou = _iou(reg.transform.box(table.box), block_box)
                    if iou >= best_iou:
                        best, best_iou = table, iou
                grids.append([] if best is None else
                             [(c.row, reg.transform.box(c.box), c.text)
                              for c in best.cells])
            pooled = row_edges(grids, floor)
            if pooled is not None:
                blocks_rows[block_name], headers[block_name] = pooled

        s5_fields = set(raw["fields"])
        print(f"  forms fields pooled {len(fields)}/{len(specs)}; "
              f"stage five had {len(s5_fields)}; "
              f"new {sorted(set(fields) - s5_fields)}")
        for name in sorted(fields):
            print(f"    + {name:34s} from {contributions[name]:2d} pages  "
                  f"{key_texts[name][:44]!r}")
        print(f"  measured row sets {len(blocks_rows)}/"
              f"{len(stage5_blocks)}: "
              f"{ {n: (len(r), headers[n]) for n, r in blocks_rows.items()} }"
              " (rows, header rows)")

        out = path.with_name(path.stem + "_forms.json")
        out.write_text(json.dumps({
            "revision": raw["revision"], "form_class": raw["form_class"],
            "page_role": raw["page_role"], "word_source": "textract",
            "geometry_source": "analyze_forms_tables",
            "analyzed_fuel": len(fuel), "pooling_floor": floor,
            "fields": {n: list(b) for n, b in fields.items()},
            "field_key_texts": key_texts,
            "field_pages": contributions,
            "blocks_rows": {n: [list(b) for b in rows]
                            for n, rows in blocks_rows.items()},
            "header_rows": headers,
        }, indent=2) + "\n")
        print(f"  wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
