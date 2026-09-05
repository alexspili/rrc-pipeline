#!/usr/bin/env python3
"""Feasibility probe: can the outline of a sheet of paper identify the sheet?

Spends nothing. No API calls. Reads page images we already have.

**The question.** Identity fields can only exclude. They describe the well, and
the failures are several filings for one well, so agreement between them is
guaranteed rather than informative. The only thing in the archive that
identifies a piece of paper is the paper: tears, folds, trimmed edges, punch
holes, staple marks. Alex matched pages by eye that way and says it is the only
conclusive direction.

**What is measured here.** For each of the four sides of a page, how far the
paper edge sits from the image border, sampled along that side. Two sides of
one sheet have the same outline, because they are the same outline. The front
and back carry completely different printing, which is why every previous
attempt at this fought the wrong battle by comparing page interiors; an
outline does not care what is printed on it.

**The transform is predicted, not searched.** A sheet flipped front-to-back
about the horizontal axis maps (x, y) to (x, H - y): the top edge becomes the
bottom edge and left stays left. That is what Alex observed on 1774674, where
staple marks at the top left of page 2 appear at the bottom left of page 6.
The other flip, about the vertical axis, is run as a **control on the same
pair** and should not score. Testing every transform and keeping the best is
what destroys discrimination.

**Which pairs, fixed before running.** Only the two pairs Alex identified from
the paper himself, plus four hard negatives from the pairs he rejected, plus
unrelated pages as easy negatives. Every other judged pair is held back so it
can still grade a real mechanism later.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "probe" / "sheet"

#: Samples along each edge. 512 over an 11-inch side is one sample every
#: 0.021 in, which is finer than any tear we care about and coarse enough to
#: average out scanner speckle.
SAMPLES = 512

#: A run of white this long counts as paper rather than as speckle. 24 px at
#: 300 dpi is 0.08 in.
PAPER_RUN = 24

#: How far the sheet may sit differently on the scanner bed between the two
#: passes. Bounded and declared: this is a translation, not a search over
#: transforms, and it is the only freedom the score is given.
MAX_SHIFT_IN = 0.12

#: The pairs this probe is allowed to look at. Everything else is held back.
TRUE_PAIRS = [
    ("1493608", 0, 5, 6, "Alex matched these by punch-hole shape"),
    ("1774674", 0, 2, 6, "Alex matched these by staple marks, x-axis flip"),
]
HARD_NEGATIVES = [
    ("1493451", 0, 7, 10, "joined on operator+total_depth, no lease agreement"),
    ("1500024", 2, 3, 1, "a real Section II, of a different filing"),
    ("1493616", 0, 5, 8, "rejected"),
    ("1494036", 0, 9, 12, "rejected"),
]
EASY_NEGATIVES = [
    ("1493608", 0, 5, "1494036", 0, 12, "unrelated records"),
    ("1774674", 0, 2, "1493451", 0, 10, "unrelated records"),
]


def pdf_of(record_id: str, file_index: int) -> Path:
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            name = json.loads(line)["files"][file_index]["name"]
            return RAW / record_id / name
    raise KeyError(record_id)


def page_array(pdf: Path, page: int) -> tuple[np.ndarray, float]:
    """One page as a boolean paper mask, plus pixels per inch.

    True is white. These are 1-bit CCITT G4 scans, so white is paper and the
    scanner background outside the sheet is black.
    """
    img = render.extract_page_image(pdf, page).convert("L")
    arr = np.asarray(img) > 127
    width_px, height_px = img.size
    # dpi is read, never assumed: 79 of the 3,689 corpus pages are not 300.
    dims = render.page_dimensions(pdf)
    w_pt, h_pt = dims[page - 1]
    dpi = width_px / (w_pt / 72.0) if w_pt else 300.0
    return arr, dpi


def edge_profile(mask: np.ndarray, side: str, run: int = PAPER_RUN):
    """Distance from the image border to the paper, along one side.

    Returns (profile in pixels, fraction of lines where paper was found).
    A line with no paper run at all is left as NaN rather than as zero: an
    undetected edge must not read as an edge at the border.
    """
    if side in ("left", "right"):
        lines = mask if side == "left" else mask[:, ::-1]
    else:
        lines = mask.T if side == "top" else mask.T[:, ::-1]

    # First index where `run` consecutive True begin, per line.
    window = np.ones(run, dtype=int)
    out = np.full(lines.shape[0], np.nan)
    for i, line in enumerate(lines):
        if line.size < run:
            continue
        runs = np.convolve(line.astype(int), window, mode="valid")
        hit = np.flatnonzero(runs == run)
        if hit.size:
            out[i] = hit[0]
    found = float(np.mean(~np.isnan(out)))
    return out, found


def resample(profile: np.ndarray, n: int = SAMPLES) -> np.ndarray:
    """Fixed-length profile, NaN-aware, so two pages compare index for index."""
    idx = np.linspace(0, len(profile) - 1, n)
    known = ~np.isnan(profile)
    if known.sum() < n // 4:
        return np.full(n, np.nan)
    return np.interp(idx, np.flatnonzero(known), profile[known])


def score(a: np.ndarray, b: np.ndarray, dpi_a: float, dpi_b: float,
          reverse: bool) -> float:
    """Correlation of two edge profiles, in inches, after mean removal.

    Mean removal because where the sheet sat on the bed is not evidence; the
    shape of its edge is. A bounded shift is allowed for the same reason and
    for no other.
    """
    a = a / dpi_a
    b = (b[::-1] if reverse else b) / dpi_b
    if np.isnan(a).any() or np.isnan(b).any():
        return float("nan")
    a = a - a.mean()
    b = b - b.mean()
    if a.std() < 1e-6 or b.std() < 1e-6:
        return float("nan")          # a perfectly straight edge carries nothing
    step = (len(a) / (11.0 * max(dpi_a, dpi_b) / dpi_a)) if dpi_a else 1
    limit = max(1, int(MAX_SHIFT_IN * len(a) / 11.0))
    best = -1.0
    for shift in range(-limit, limit + 1):
        x = a if shift == 0 else np.roll(a, shift)
        cut = abs(shift)
        u, v = (x[cut:], b[cut:]) if shift > 0 else (x[:len(x) - cut],
                                                    b[:len(b) - cut])
        if len(u) < 32:
            continue
        u = u - u.mean()
        v = v - v.mean()
        if u.std() < 1e-6 or v.std() < 1e-6:
            continue
        best = max(best, float(np.corrcoef(u, v)[0, 1]))
    return best


#: Front-to-back about the horizontal axis: (x, y) -> (x, H - y). Left stays
#: left and runs backwards; top meets bottom and runs forwards.
PREDICTED = [("left", "left", True), ("right", "right", True),
             ("top", "bottom", False), ("bottom", "top", False)]

#: The control. About the vertical axis: (x, y) -> (W - x, y). If a pair
#: scores here as well as under the predicted flip, the score is measuring
#: something other than the sheet.
CONTROL = [("left", "right", False), ("right", "left", False),
           ("top", "top", True), ("bottom", "bottom", True)]


def compare(pdf_a, page_a, pdf_b, page_b):
    mask_a, dpi_a = page_array(pdf_a, page_a)
    mask_b, dpi_b = page_array(pdf_b, page_b)
    prof_a, prof_b, found = {}, {}, {}
    for side in ("left", "right", "top", "bottom"):
        raw_a, fa = edge_profile(mask_a, side)
        raw_b, fb = edge_profile(mask_b, side)
        prof_a[side], prof_b[side] = resample(raw_a), resample(raw_b)
        found[side] = min(fa, fb)

    def run(plan):
        out = {}
        for side_a, side_b, rev in plan:
            out[side_a] = score(prof_a[side_a], prof_b[side_b],
                                dpi_a, dpi_b, rev)
        return out

    return run(PREDICTED), run(CONTROL), found, (dpi_a, dpi_b)


def summarise(scores: dict) -> float:
    values = [v for v in scores.values() if not np.isnan(v)]
    return float(np.mean(values)) if values else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draw", action="store_true",
                    help="write the detected outlines as images")
    args = ap.parse_args()

    cases = []
    for rid, fi, a, b, why in TRUE_PAIRS:
        cases.append(("TRUE ", rid, fi, a, rid, fi, b, why))
    for rid, fi, a, b, why in HARD_NEGATIVES:
        cases.append(("hard ", rid, fi, a, rid, fi, b, why))
    for ra, fa, pa, rb, fb, pb, why in EASY_NEGATIVES:
        cases.append(("easy ", ra, fa, pa, rb, fb, pb, why))

    print(f"{'kind':6s} {'pair':28s} {'predicted':>9s} {'control':>8s} "
          f"{'edge found':>10s}   detail")
    rows = []
    for kind, ra, fa, pa, rb, fb, pb, why in cases:
        pred, ctrl, found, dpis = compare(pdf_of(ra, fa), pa,
                                          pdf_of(rb, fb), pb)
        p, c = summarise(pred), summarise(ctrl)
        label = (f"{ra}-{fa} p{pa}+p{pb}" if ra == rb
                 else f"{ra} p{pa} + {rb} p{pb}")
        print(f"{kind} {label:28s} {p:9.3f} {c:8.3f} "
              f"{min(found.values()):10.0%}   {why}")
        rows.append((kind, label, p, c, pred, ctrl, found, dpis))

    print("\nper-side detail, predicted flip:")
    print(f"{'pair':30s} " + " ".join(f"{s:>7s}" for s in
                                      ("left", "right", "top", "bottom"))
          + "   dpi")
    for kind, label, p, c, pred, ctrl, found, dpis in rows:
        print(f"{kind}{label:25s} "
              + " ".join(f"{pred[s]:7.3f}" for s in
                         ("left", "right", "top", "bottom"))
              + f"   {dpis[0]:.0f}/{dpis[1]:.0f}")

    trues = [p for k, _, p, _, _, _, _, _ in rows if k.strip() == "TRUE"]
    others = [p for k, _, p, _, _, _, _, _ in rows if k.strip() != "TRUE"]
    print()
    if trues and others and not any(np.isnan(trues + others)):
        print(f"true pairs      : {min(trues):.3f} to {max(trues):.3f}")
        print(f"everything else : {min(others):.3f} to {max(others):.3f}")
        gap = min(trues) - max(others)
        print(f"separation      : {gap:+.3f}")
        print("\nSEPARATED." if gap > 0 else
              "\nNOT SEPARATED on this slice.")
    else:
        print("some comparison returned NaN; see the per-side table above.")

    if args.draw:
        OUT.mkdir(parents=True, exist_ok=True)
        print(f"\nimages: {OUT}")


if __name__ == "__main__":
    main()
