#!/usr/bin/env python3
"""The page's embedded text layer, as word boxes in page fractions.

Moved here from scripts/snap_coverage.py when the template probe became the
second reader of the same layer. Two readers with two copies of the parser
would be free to drift, and the snap tier and the template tier have to agree
about what a word box is or their numbers are not comparable.

Coordinate caveat, carried over from the snap script rather than dropped:
word boxes are fractions of the PDF page box while model boxes are fractions
of the embedded scan image. On this corpus the scan fills the page, so the
two spaces align. A page where it did not would shear every distance in
registration. tests/tier2 pins the assumption instead of trusting the comment.
"""

from __future__ import annotations

import re
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
