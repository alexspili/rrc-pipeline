#!/usr/bin/env python3
"""What would wiring the paper confirmer into reassembly actually change?

Spends nothing. Reads the identity cache and the small-mark cache, both already
on disk; no API calls.

**Why this and not another pair-level measurement.** Every number the paper
channels have produced is per pair. Reassembly's number is per document, and
the two come apart asymmetrically: a wrong attachment ruins a whole document by
putting one well's pages under another well's identity, while a right one only
helps a document that was incomplete. So a channel can be right three times in
four on pairs and still make the product worse.

`docs/labeling-protocol-paper.md` said this on 2026-09-06 and it has never been
measured:

    Not measured here: whether reassembly gets better. Passing both bars and
    making that number worse is possible, and crediting this mechanism with an
    accuracy improvement needs a document-level evaluation.

This is that evaluation's first half: which documents change at all. Only those
need a human, and the count decides whether a sitting is even warranted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import identity                       # noqa: E402
from pipeline import pageclass as pc                # noqa: E402
from pipeline import paper                          # noqa: E402
from pipeline import papermatch                     # noqa: E402
from pipeline import reassemble as ra               # noqa: E402
from pipeline import render                         # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
IDENTITY = ROOT / "data" / "extract" / "cache_identity.jsonl"
SMALL = ROOT / "data" / "cache" / "paper_small"
MARKS = ROOT / "data" / "cache" / "paper"


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def build_pages(recs):
    """Every page the identity reader has already read, as PageRecords.

    Uses the same cache key and parser as scripts/measure_reassemble.py rather
    than rebuilding them: the key carries the prompt hash, and constructing it
    here would leave the prompt out, which is the thing CLAUDE.md rule 7
    exists to prevent. A first attempt did exactly that and matched zero pages.
    """
    from pipeline import classify

    census = {}
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        record_id, file_index, page = pc.parse_page_id(row["page_id"])
        if row.get("error") or row.get("form_class") not in (
                "w2", "g1", "other_form"):
            continue
        census[(record_id, file_index, page)] = row

    cache = classify.ResultCache(IDENTITY, prompt_hash=identity.PROMPT_HASH)
    built, missing = {}, 0
    hashes = {}
    for (record_id, file_index, page), row in sorted(census.items()):
        entry = recs.get(record_id)
        if not entry:
            continue
        pdf = RAW / record_id / entry["files"][file_index]["name"]
        if not pdf.exists():
            continue
        if pdf not in hashes:
            hashes[pdf] = render.doc_hash(pdf)
        hit = cache.get(cache.key(hashes[pdf], page, "identity"))
        if hit is None:
            missing += 1
            continue
        read = identity.parse(hit["body"], page)
        if read is None:
            continue
        built[(record_id, file_index, page)] = ra.PageRecord(
            record_id=record_id, file_index=file_index, page=page,
            form_class=row["form_class"], part=row.get("part"),
            identity=identity.identity_for(read),
            sources=read.found_in, stamps=read.stamps)
    print(f"census pages of interest {len(census)}, "
          f"read from cache {len(built)}, not cached {missing}")
    return built


def make_confirmer(recs, verbose=False):
    """(face, candidate) -> bool, from the small marks on the two pages.

    Detects on a cache miss rather than abstaining. The first version read the
    cache only, and every one of the 314 candidate pairs missed, because the
    small-mark cache had been built for district 02 and these pages are
    district 03. A confirmer that silently abstains on a cold cache reports
    "nothing changes" and means "nothing was looked at".
    """
    cache = papermatch.SmallMarkCache(SMALL)
    hashes, misses, asked = {}, [0], [0]

    def marks(rec):
        pdf = RAW / rec.record_id / \
            recs[rec.record_id]["files"][rec.file_index]["name"]
        if not pdf.exists():
            return None
        if pdf not in hashes:
            hashes[pdf] = render.doc_hash(pdf)
        try:
            return papermatch.page_small_marks(pdf, rec.page, cache,
                                               hashes[pdf])
        except Exception:                                    # noqa: BLE001
            return None

    def confirms(face, candidate):
        asked[0] += 1
        a, b = marks(face), marks(candidate)
        if a is None or b is None:
            misses[0] += 1
            return False
        verdict = paper.compare_small(a, b)
        if verdict.confirmed and verbose:
            print(f"    confirms {face.record_id}-{face.file_index} "
                  f"p{face.page} + p{candidate.page}  {verdict.reason}")
        return verdict.confirmed

    confirms.stats = lambda: (asked[0], misses[0])
    return confirms


def group_all(pages, confirms=None):
    by_file = {}
    for record in pages.values():
        by_file.setdefault(record.file_key, []).append(record)
    documents = {}
    for file_key, group in sorted(by_file.items()):
        docs, _ = ra.group(group, confirms=confirms)
        for doc in docs:
            face = doc.pages[0]
            key = (face.record_id, face.file_index, face.page)
            documents[key] = tuple(sorted(p.page for p in doc.pages))
    return documents


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    recs = records()
    pages = build_pages(recs)
    print(f"pages with both a census row and an identity read: {len(pages)}")

    before = group_all(pages)
    confirms = make_confirmer(recs, args.verbose)
    after = group_all(pages, confirms)
    asked, missed = confirms.stats()
    print(f"candidate pairs offered to the confirmer: {asked}, "
          f"of which {missed} had no cached marks")

    print(f"\ndocuments before {len(before)}, after {len(after)}")
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    print(f"documents whose page set CHANGES: {len(changed)}")
    for key in changed:
        was, now = before.get(key), after.get(key)
        gained = tuple(p for p in (now or ()) if p not in (was or ()))
        lost = tuple(p for p in (was or ()) if p not in (now or ()))
        print(f"  {key[0]}-{key[1]} face p{key[2]}: {was} -> {now}"
              f"   gained {gained or '-'}  lost {lost or '-'}")

    if not changed:
        print("\nNothing changes. The confirmer fires on pairs reassembly")
        print("already attaches, or on none it is offered.")


if __name__ == "__main__":
    main()
