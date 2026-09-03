#!/usr/bin/env python3
"""The page's embedded text layer, as word boxes in page fractions.

Moved here from scripts/snap_coverage.py when the template probe became the
second reader of the same layer. Two readers with two copies of the parser
would be free to drift, and the snap tier and the template tier have to agree
about what a word box is or their numbers are not comparable.

It also computes the region a reviewer is shown for a text-layer match. The
matched word is the evidence and the printed run around it is what a person
needs to see: a box drawn around `SKELLY` alone, for a value of `SKELLY OIL
COMPANY`, was reported as a partial capture five times out of fifteen in the
2026-09-03 grading, and a one-word box gave a grader nothing with which to
notice that a match had landed in the wrong form field at all (DEFECTS #32).

Coordinate caveat, carried over from the snap script rather than dropped:
word boxes are fractions of the PDF page box while model boxes are fractions
of the embedded scan image. On this corpus the scan fills the page, so the
two spaces align. A page where it did not would shear every distance in
registration. tests/tier2 pins the assumption instead of trusting the comment.
"""

from __future__ import annotations

import re
import statistics
import subprocess
from pathlib import Path

#: A word box: left, top, right, bottom in page fractions, then its text.
Word = tuple[float, float, float, float, str]

_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)"'
    r'>([^<]*)</word>')
_PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')

#: OCR digit confusions folded on BOTH sides before comparing. Narrow on
#: purpose; a wide table would merge words that are genuinely different.
_FOLD = str.maketrans({"o": "0", "l": "1", "i": "1"})


#: "Same printed line", as a fraction of the page's own median word height.
#: Not a chosen constant: on the graded pages a printed label line and the
#: typed value under it sit 1.5 to 1.9 median word heights apart, so anything
#: below 1.0 separates them and 0.6 does so with room. It is also
#: `template.BAND_LINES`, which is 0.6 for the same reason on the same paper;
#: reusing the number rather than inventing a second one is deliberate.
LINE_TOL = 0.6

#: A horizontal gap wider than this many median inter-word gaps is a
#: different form field rather than a space. Measured on record 1493608: the
#: median gap is 0.0039, set by the dense printed labels; a space inside a
#: typed value runs to 0.009; the nearest real field separation is 0.0196. So
#: the multiple has to clear about 2.4 and stay under about 5.0.
GAP_GAPS = 4.0

#: Fallback when the page has too few gaps to take a median from.
GAP_LINES = 1.5
MIN_GAP_SAMPLES = 20


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def fold(text: str) -> str:
    return norm(text).translate(_FOLD)


def page_words(pdf: Path, page: int) -> list[Word]:
    """Word boxes from `pdftotext -bbox`, in page fractions."""
    html = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page),
         str(pdf), "-"], capture_output=True, text=True).stdout
    size = _PAGE.search(html)
    if not size:
        return []
    width, height = float(size.group(1)), float(size.group(2))
    words: list[Word] = []
    for m in _WORD.finditer(html):
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        words.append((x0 / width, y0 / height, x1 / width, y1 / height,
                      m.group(5)))
    return words


def line_height(words: list[Word]) -> float:
    """The page's median word height, which is its most stable statistic.

    Median word *width* swings by 43% between two pages of one document here,
    because OCR fragments tokens. Height moves between 0.0069 and 0.0085
    across the graded pages, so every tolerance in this module is expressed
    as a multiple of it.
    """
    heights = [w[3] - w[1] for w in words if w[3] > w[1]]
    return statistics.median(heights) if heights else 0.012


def _printed(words: list[Word]) -> list[Word]:
    """Words with actual characters in them.

    Leader dots are the reason this exists. `pdftotext` emits the rows of
    dots that separate the depth fields as their own tokens about 0.0034
    apart, which is under any sane gap cutoff, so a run walking through them
    bridges `8030` straight to `8465`: two different fields on one line,
    which is the exact failure the cutoff is there to prevent. `norm` empties
    any token with no alphanumerics, which is precisely those glyphs.
    """
    return [w for w in words if norm(w[4])]


def _same_line(a: Word, b: Word, height: float,
               tol: float = LINE_TOL) -> bool:
    return abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) <= tol * height


def word_gaps(words: list[Word], height: float) -> list[float]:
    """Positive horizontal gaps between neighbouring words on one line."""
    ordered = sorted(_printed(words), key=lambda w: (w[1], w[0]))
    gaps = []
    for first, second in zip(ordered, ordered[1:]):
        if not _same_line(first, second, height):
            continue
        gap = second[0] - first[2]
        if gap > 0:
            gaps.append(gap)
    return gaps


def gap_cutoff(words: list[Word], height: float) -> float:
    """How wide a gap has to be before it is a different field.

    Derived from the page's own typography, so a differently scaled scan gets
    a differently scaled cutoff without anybody retuning a constant.
    """
    gaps = word_gaps(words, height)
    if len(gaps) >= MIN_GAP_SAMPLES:
        return GAP_GAPS * statistics.median(gaps)
    return GAP_LINES * height


def line_run(words: list[Word], box: tuple[float, float, float, float],
             line_tol: float = LINE_TOL,
             gap_gaps: float = GAP_GAPS) -> tuple[float, float, float, float]:
    """The printed run on one line that contains `box`.

    Walks outward from the anchor, word to word, absorbing each neighbour
    that sits on the same line until the gap to the next one is wide enough
    to be a different field. Returns `box` unchanged on every degenerate
    path, so a caller never has to handle None and a display region is never
    smaller than the evidence it is showing.

    Chained rather than compared to the anchor throughout. The typed line on
    record 1493608 page 5 drifts by 0.0030 in y from one end to the other,
    while the printed label line sits 0.012 above it: a tolerance loose
    enough to hold that drift as one block is within a factor of four of
    loose enough to swallow the neighbouring line. Comparing each step to the
    word it just absorbed makes the tolerance a per-word budget instead of a
    whole-line one.
    """
    printed = _printed(words)
    if not printed:
        return box
    height = line_height(words)
    cutoff = gap_cutoff(words, height)
    anchor = (box[0], box[1], box[2], box[3], "")
    left, right = box[0], box[2]
    top, bottom = box[1], box[3]

    for direction in (1, -1):
        current = anchor
        edge = right if direction == 1 else left
        candidates = sorted(printed, key=lambda w: w[0] * direction)
        for word in candidates:
            if direction == 1 and word[0] < right:
                continue
            if direction == -1 and word[2] > left:
                continue
            if not _same_line(word, current, height, line_tol):
                continue
            gap = word[0] - edge if direction == 1 else left - word[2]
            if gap > cutoff:
                break
            current = word
            if direction == 1:
                right = edge = max(right, word[2])
            else:
                left = edge = min(left, word[0])
            top, bottom = min(top, word[1]), max(bottom, word[3])
    return (max(0.0, left), max(0.0, top), min(1.0, right), min(1.0, bottom))
