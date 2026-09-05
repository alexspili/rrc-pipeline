#!/usr/bin/env python3
"""Score every pair on a verification sheet with the paper-outline matcher.

Spends nothing. No API calls.

The mechanism is the one probed on 2026-09-05 and closed in
docs/modules/reassemble.md: for each of the four sides of a page, the distance
from the image border to the paper, correlated between the two pages under the
flip a sheet can physically perform.

**Read the control column, not the score column.** A sheet flipped
front-to-back maps (x, y) to (x, H - y). The control is the flip about the
vertical axis, which paper cannot do between two scans. If a pair scores the
same under both, the number is not about the sheet. On the probe slice the
predicted-minus-control gap was -0.002 on true pairs, which is why the
mechanism is closed. The columns are here so that can be checked rather than
taken on trust.

A page whose scan has no black scanner border has no visible paper edge: the
outline is a straight rectangle by construction. Those pairs abstain and say so
in the `abstained` column rather than scoring zero.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
FIXTURES = ROOT / "tests" / "fixtures"
OUT = ROOT / "data" / "probe"

#: Samples per edge. 1024 over an 11 in side is one sample every 0.011 in.
SAMPLES = 1024

#: A white run this long is paper rather than speckle: 24 px at 300 dpi.
PAPER_RUN = 24

#: How far the sheet may sit differently between the two scans, as a fraction
#: of the profile. Bounded and declared: a translation, not a search over
#: transforms, and the only freedom the score is given.
MAX_SHIFT = 0.012

#: A side needs paper found on this fraction of its lines to be usable.
MIN_FOUND = 0.80

#: Front-to-back about the horizontal axis: left stays left and runs backwards,
#: top meets bottom.
PREDICTED = [("left", "left", True), ("right", "right", True),
             ("top", "bottom", False), ("bottom", "top", False)]

#: About the vertical axis. Paper cannot do this between two scans, so it is
#: the control: any score it earns is a score the mechanism did not earn.
CONTROL = [("left", "right", False), ("right", "left", False),
           ("top", "top", True), ("bottom", "bottom", True)]

_pages: dict = {}


def pdf_of(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            name = json.loads(line)["files"][file_index]["name"]
            return RAW / record_id / name
    raise KeyError(record_id)


def _profiles(mask: np.ndarray) -> tuple[dict, dict, int]:
    """Edge profiles for all four sides, and how much of each was found."""
    out, found = {}, {}
    for side in ("left", "right", "top", "bottom"):
        lines = (mask if side == "left" else mask[:, ::-1] if side == "right"
                 else mask.T if side == "top" else mask.T[:, ::-1])
        counts = np.cumsum(lines.astype(np.int32), axis=1)
        window = counts[:, PAPER_RUN - 1:] - np.concatenate(
            [np.zeros((counts.shape[0], 1), np.int32),
             counts[:, :-PAPER_RUN]], axis=1)
        hit = window == PAPER_RUN
        any_hit = hit.any(axis=1)
        raw = np.where(any_hit, hit.argmax(axis=1), -1).astype(float)
        raw[~any_hit] = np.nan
        found[side] = float(np.mean(any_hit))
        out[side] = _resample(raw)

    # How many sides carry a real scanner border. A page with none has no
    # visible paper edge at all and the mechanism must abstain on it.
    height, width = mask.shape
    band = max(2, width // 200)
    dark = [1 - mask[:, :band].mean(), 1 - mask[:, -band:].mean(),
            1 - mask[:band, :].mean(), 1 - mask[-band:, :].mean()]
    return out, found, sum(1 for d in dark if d > 0.5)


def page(record_id: str, file_index: int, number: int):
    key = (record_id, file_index, number)
    if key not in _pages:
        img = render.extract_page_image(
            pdf_of(record_id, file_index), number).convert("L")
        _pages[key] = _profiles(np.asarray(img) > 127)
    return _pages[key]


def _resample(profile: np.ndarray, n: int = SAMPLES) -> np.ndarray:
    known = ~np.isnan(profile)
    if known.sum() < n // 4:
        return np.full(n, np.nan)
    return np.interp(np.linspace(0, len(profile) - 1, n),
                     np.flatnonzero(known), profile[known])


def _detrend(v: np.ndarray) -> np.ndarray:
    """Remove the straight line, so scanner skew cancels and only the
    departures from a straight edge — the tears and folds — remain."""
    x = np.arange(len(v))
    basis = np.vstack([x, np.ones_like(x)]).T
    coef, *_ = np.linalg.lstsq(basis, v, rcond=None)
    return v - basis @ coef


def _corr(a: np.ndarray, b: np.ndarray, reverse: bool) -> float:
    if np.isnan(a).any() or np.isnan(b).any():
        return float("nan")
    b = b[::-1] if reverse else b
    a, b = _detrend(a), _detrend(b)
    if a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    limit = max(1, int(MAX_SHIFT * len(a)))
    best = -1.0
    for shift in range(-limit, limit + 1):
        rolled = np.roll(a, shift)
        cut = abs(shift)
        u, v = ((rolled[cut:], b[cut:]) if shift > 0
                else (rolled[:len(rolled) - cut], b[:len(b) - cut]))
        if len(u) < 32:
            continue
        u, v = u - u.mean(), v - v.mean()
        if u.std() < 1e-9 or v.std() < 1e-9:
            continue
        best = max(best, float(np.corrcoef(u, v)[0, 1]))
    return best


def score_pair(record_id: str, file_index: int, child: int, face: int) -> dict:
    pa, fa, ba = page(record_id, file_index, child)
    pb, fb, bb = page(record_id, file_index, face)

    row = {"borders_child": ba, "borders_face": bb}
    if ba == 0 or bb == 0:
        row["abstained"] = ("no scanner border on "
                            + ("both pages" if ba == 0 and bb == 0
                               else f"p{child}" if ba == 0 else f"p{face}"))
        return row

    per_side = {}
    for side_a, side_b, reverse in PREDICTED:
        if min(fa[side_a], fb[side_b]) < MIN_FOUND:
            per_side[side_a] = float("nan")
            continue
        per_side[side_a] = _corr(pa[side_a], pb[side_b], reverse)
    control = {}
    for side_a, side_b, reverse in CONTROL:
        if min(fa[side_a], fb[side_b]) < MIN_FOUND:
            control[side_a] = float("nan")
            continue
        control[side_a] = _corr(pa[side_a], pb[side_b], reverse)

    usable = [v for v in per_side.values() if not np.isnan(v)]
    ctrl = [v for v in control.values() if not np.isnan(v)]
    if not usable:
        row["abstained"] = "no side had a readable paper edge on both pages"
        return row

    row["abstained"] = ""
    row["predicted"] = round(float(np.mean(usable)), 4)
    row["control"] = round(float(np.mean(ctrl)), 4) if ctrl else ""
    if ctrl:
        row["gap"] = round(row["predicted"] - row["control"], 4)
    row["sides_used"] = len(usable)
    for side in ("left", "right", "top", "bottom"):
        value = per_side.get(side, float("nan"))
        row[side] = "" if np.isnan(value) else round(float(value), 4)
    return row


def sheet_rows(path: Path):
    raw = path.read_bytes().decode("utf-8", errors="replace")
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("part", "A") != "A" or "+" not in row.get("item", ""):
            continue
        child, face = (int(x.lstrip("p"))
                       for x in row["item"].split()[-1].split("+"))
        yield row, child, face


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default="attachment_verify_4.csv")
    args = ap.parse_args()

    source = FIXTURES / args.sheet
    target = OUT / f"outline_scores_{source.stem}.csv"
    OUT.mkdir(parents=True, exist_ok=True)

    fields = ["item", "record_id", "file_index", "child_page", "face_page",
              "your_verdict", "predicted", "control", "gap", "left", "right",
              "top", "bottom", "sides_used", "borders_child", "borders_face",
              "abstained", "joined_on"]
    rows = []
    for row, child, face in sheet_rows(source):
        scored = score_pair(row["record_id"].strip(), int(row["file_index"]),
                            child, face)
        rows.append({
            "item": row["item"], "record_id": row["record_id"].strip(),
            "file_index": row["file_index"], "child_page": child,
            "face_page": face,
            "your_verdict": (row.get("verdict") or "").strip(),
            "joined_on": row.get("joined_on", ""),
            **{k: scored.get(k, "") for k in fields if k in scored}})
        print(f"  {row['item']:26s} "
              f"{str(rows[-1].get('predicted','')):>8s} "
              f"{str(rows[-1].get('control','')):>8s}  "
              f"{rows[-1]['your_verdict']:9s} {scored.get('abstained','')}")

    with target.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    scored = [r for r in rows if r.get("predicted") not in (None, "")]
    print(f"\n{len(rows)} pairs, {len(scored)} scored, "
          f"{len(rows) - len(scored)} abstained for want of a paper edge")
    if scored:
        yes = [r["predicted"] for r in scored if r["your_verdict"] == "yes"]
        no = [r["predicted"] for r in scored if r["your_verdict"] != "yes"]
        gy = [r["gap"] for r in scored
              if r["your_verdict"] == "yes" and r.get("gap") != ""]
        gn = [r["gap"] for r in scored
              if r["your_verdict"] != "yes" and r.get("gap") != ""]
        if yes:
            print(f"  you said yes ({len(yes)}): "
                  f"{min(yes):.3f} to {max(yes):.3f}")
        if no:
            print(f"  you said no  ({len(no)}): "
                  f"{min(no):.3f} to {max(no):.3f}")
        if gy and gn:
            print(f"  predicted minus control: yes {np.mean(gy):+.3f}, "
                  f"no {np.mean(gn):+.3f}")
            print("  (a mechanism that reads the sheet has a large positive "
                  "gap on true pairs.)")
    print(f"\nspreadsheet: {target}")


if __name__ == "__main__":
    main()
