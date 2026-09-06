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


class MarkCache:
    """Marks for one page, on disk, keyed on (document, page, detector).

    One compressed file per page rather than a shared JSONL: an outline is 720
    numbers and a page carries several marks, so the rows are far too fat for
    the line-oriented caches used elsewhere in this repo.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, doc_hash: str, page: int) -> Path:
        return self.root / f"{doc_hash}-{page}-{DETECTOR}.npz"

    def get(self, doc_hash: str, page: int) -> list[paper.Mark] | None:
        path = self.path(doc_hash, page)
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as data:
            meta, kinds, outlines = data["meta"], data["kinds"], data["outlines"]
        return [paper.Mark(x=float(m[0]), y=float(m[1]), area_in2=float(m[2]),
                           fill=float(m[3]), kind=str(k),
                           outline=tuple(float(v) for v in o))
                for m, k, o in zip(meta, kinds, outlines)]

    def put(self, doc_hash: str, page: int, marks: list[paper.Mark]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        meta = np.array([[m.x, m.y, m.area_in2, m.fill] for m in marks],
                        dtype=np.float64).reshape(len(marks), 4)
        kinds = np.array([m.kind for m in marks], dtype="U8")
        outlines = np.array([m.outline for m in marks],
                            dtype=np.float32).reshape(len(marks), -1)
        np.savez_compressed(self.path(doc_hash, page), meta=meta, kinds=kinds,
                            outlines=outlines)


def page_marks(pdf: Path, page: int, cache: MarkCache | None = None,
               doc_hash: str | None = None) -> list[paper.Mark]:
    """Every solid mark on one page of one file."""
    if cache is not None:
        doc_hash = doc_hash or render.doc_hash(pdf)
        hit = cache.get(doc_hash, page)
        if hit is not None:
            return hit

    image = render.extract_page_image(pdf, page).convert("L")
    marks = paper.solid_marks(np.asarray(image) < 128)

    if cache is not None:
        cache.put(doc_hash, page, marks)
    return marks


def compare_pages(pdf_a: Path, page_a: int, pdf_b: Path, page_b: int,
                  cache: MarkCache | None = None,
                  hashes: dict | None = None) -> paper.Verdict:
    """Are these two pages the front and back of one sheet?"""
    hashes = hashes or {}
    a = page_marks(pdf_a, page_a, cache, hashes.get(pdf_a))
    b = page_marks(pdf_b, page_b, cache, hashes.get(pdf_b))
    return paper.compare(a, b)
