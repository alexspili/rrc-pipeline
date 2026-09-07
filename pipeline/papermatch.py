#!/usr/bin/env python3
"""Reading pages off disk and matching them. The I/O half of pipeline/paper.py.

Same split as pageclass/classify and extract/extractor: the domain module is
pure and testable on synthetic arrays, and this one touches files.

Detection costs 1.2 s a page, of which 0.5 s is `pdfimages`, and the false
positive measurement needs thousands of pairs. So marks are cached per page,
keyed on the document hash, the page, and a hash of the detection constants —
CLAUDE.md rule 7 applied to a detector instead of a prompt. Change a threshold
and every cached page is invalidated by construction, which is the property
that makes the cache safe rather than merely fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline import paper
from pipeline import pageclass as pc
from pipeline import render

#: Half the cache key. Every constant that changes what a mark is belongs in
#: here; a constant left out is a stale cache nobody notices.
DETECTOR = pc.prompt_hash(json.dumps({
    "samples": paper.SAMPLES,
    "strip": paper.STRIP,
    "min_area": paper.MIN_MARK_AREA,
    "min_fill": paper.MIN_FILL,
    "max_aspect": paper.MAX_ASPECT,
    "hole_fill": paper.HOLE_FILL,
    "hole_aspect": paper.HOLE_ASPECT,
    "hole_area": list(paper.HOLE_AREA),
}, sort_keys=True))

#: The other half of the other cache key. Separate from DETECTOR on purpose:
#: the two channels have separate constants, and folding them together would
#: make a change to one invalidate every page cached under the other. There
#: are 1,451 of those and each costs about 1.5 s to rebuild.
SMALL_DETECTOR = pc.prompt_hash(json.dumps({
    "area": list(paper.SMALL_AREA_IN2),
    "max_aspect": paper.SMALL_MAX_ASPECT,
    "edge": paper.SMALL_EDGE_IN,
    "run_pitch": paper.SMALL_RUN_PITCH_IN,
    "max_neighbours": paper.SMALL_MAX_NEIGHBOURS,
    "inset": paper.SMALL_INSET_IN,
}, sort_keys=True))


class MarkCache:
    """Marks for one page, on disk, keyed on (document, page, detector).

    One compressed file per page rather than a shared JSONL: an outline is 720
    numbers and a page carries several marks, so the rows are far too fat for
    the line-oriented caches used elsewhere in this repo.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, doc_hash: str, page: int, dpi: float) -> Path:
        # The resolution is part of the key and is not optional. It is a
        # property of the page rather than of the detector, so it does not
        # belong in DETECTOR, where a change invalidates every cached page in
        # the corpus. It has to be in the key at all because it decides what
        # counts as a mark: DEFECTS #61.
        return self.root / f"{doc_hash}-{page}-{dpi:g}-{DETECTOR}.npz"

    def get(self, doc_hash: str, page: int,
            dpi: float) -> list[paper.Mark] | None:
        path = self.path(doc_hash, page, dpi)
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as data:
            meta, kinds, outlines = data["meta"], data["kinds"], data["outlines"]
        return [paper.Mark(x=float(m[0]), y=float(m[1]), area_in2=float(m[2]),
                           fill=float(m[3]), kind=str(k),
                           outline=tuple(float(v) for v in o))
                for m, k, o in zip(meta, kinds, outlines)]

    def put(self, doc_hash: str, page: int, dpi: float,
            marks: list[paper.Mark]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        meta = np.array([[m.x, m.y, m.area_in2, m.fill] for m in marks],
                        dtype=np.float64).reshape(len(marks), 4)
        kinds = np.array([m.kind for m in marks], dtype="U8")
        outlines = np.array([m.outline for m in marks],
                            dtype=np.float32).reshape(len(marks), -1)
        np.savez_compressed(self.path(doc_hash, page, dpi), meta=meta,
                            kinds=kinds, outlines=outlines)


class SmallMarkCache:
    """Small marks for one page, on disk, keyed on (document, page, dpi, detector).

    A plain JSONL row per page rather than the compressed arrays MarkCache
    needs: a small mark carries three numbers and no 720-sample outline, so the
    rows are thin enough for the line-oriented pattern used elsewhere here.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, doc_hash: str, page: int, dpi: float) -> Path:
        # Resolution is in the key for the same reason as in MarkCache: it
        # decides what counts as a mark, and this channel's constants are all
        # distances (DEFECTS #61).
        return self.root / f"{doc_hash}-{page}-{dpi:g}-{SMALL_DETECTOR}.json"

    def get(self, doc_hash: str, page: int,
            dpi: float) -> list[paper.SmallMark] | None:
        path = self.path(doc_hash, page, dpi)
        if not path.exists():
            return None
        return [paper.SmallMark(x=m[0], y=m[1], area_in2=m[2])
                for m in json.loads(path.read_text())]

    def put(self, doc_hash: str, page: int, dpi: float,
            marks: list[paper.SmallMark]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path(doc_hash, page, dpi).write_text(
            json.dumps([[m.x, m.y, m.area_in2] for m in marks]))


def page_small_marks(pdf: Path, page: int,
                     cache: SmallMarkCache | None = None,
                     doc_hash: str | None = None) -> list[paper.SmallMark]:
    """Every small mark on one page: the second channel's half of page_marks."""
    dpi = page_dpi(pdf, page)
    if cache is not None:
        doc_hash = doc_hash or render.doc_hash(pdf)
        hit = cache.get(doc_hash, page, dpi)
        if hit is not None:
            return hit

    image = render.extract_page_image(pdf, page).convert("L")
    marks = paper.small_marks(np.asarray(image) < 128, dpi=dpi)

    if cache is not None:
        cache.put(doc_hash, page, dpi, marks)
    return marks


def page_dpi(pdf: Path, page: int) -> float:
    """The scan resolution of one page, or 300 if the file will not say.

    `paper.solid_marks` states its size envelope in square inches, so somebody
    has to supply the conversion, and until DEFECTS #61 nobody did: this module
    took the 300 dpi default on every page. 53 corpus pages are 200 dpi and all
    of them share a file with 300 dpi pages, where the assumption both raised
    the floor to 0.045 in² and reported every area 2.25x small, which is
    outside AREA_RATIO and so stopped a mark pairing with itself across the
    change.

    The fallback is 300 and is the corpus mode. It is reached only if poppler
    reports no resolution at all, which happens on no page of the corpus.
    """
    resolutions = render.page_resolutions(pdf)
    if page < 1 or page > len(resolutions) or resolutions[page - 1] <= 0:
        return 300.0
    return resolutions[page - 1]


def page_marks(pdf: Path, page: int, cache: MarkCache | None = None,
               doc_hash: str | None = None) -> list[paper.Mark]:
    """Every solid mark on one page of one file."""
    dpi = page_dpi(pdf, page)
    if cache is not None:
        doc_hash = doc_hash or render.doc_hash(pdf)
        hit = cache.get(doc_hash, page, dpi)
        if hit is not None:
            return hit

    image = render.extract_page_image(pdf, page).convert("L")
    marks = paper.solid_marks(np.asarray(image) < 128, dpi=dpi)

    if cache is not None:
        cache.put(doc_hash, page, dpi, marks)
    return marks


def compare_pages(pdf_a: Path, page_a: int, pdf_b: Path, page_b: int,
                  cache: MarkCache | None = None,
                  hashes: dict | None = None) -> paper.Verdict:
    """Are these two pages the front and back of one sheet?"""
    hashes = hashes or {}
    a = page_marks(pdf_a, page_a, cache, hashes.get(pdf_a))
    b = page_marks(pdf_b, page_b, cache, hashes.get(pdf_b))
    return paper.compare(a, b)
