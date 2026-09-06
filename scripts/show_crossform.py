#!/usr/bin/env python3
"""Lay out the cross-family attachments Alex judged correct, for eyeballing.

Spends nothing. No API calls.

These are the attachments a "same form family or no attachment" rule would
delete. The census gives the two pages different form classes; Alex judged the
pairing correct; and the printed field numbers say the census is wrong about
one of the pages (DEFECTS #59).

Writes one folder per pair, face first, with a README naming what each source
says so the pages can be checked against the claim rather than taken on trust.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                       # noqa: E402
from pipeline import identity                       # noqa: E402
from pipeline import render                         # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
IDENTITY_CACHE = ROOT / "data" / "extract" / "cache_identity.jsonl"
DOCS = ROOT / "data" / "extract" / "reassemble.jsonl"
OUT = ROOT / "data" / "labelset" / "crossform"

BOX = re.compile(r"^\s*(\d{1,2})\s*[.\s]")

#: Read straight off the printed forms, measured on 27 back pages (DEFECTS #59).
FAMILY = {("notice", 19): "g1", ("notice", 26): "w2",
          ("location", 24): "g1", ("location", 31): "w2",
          ("location", 32): "w2",
          ("depth", 28): "g1", ("depth", 35): "w2", ("depth", 36): "w2"}
KEY = (("notice of intention", "notice"), ("location of well", "location"),
       ("location of the well", "location"), ("total depth", "depth"))


def records() -> dict:
    return {json.loads(l)["record_id"]: json.loads(l)
            for l in MANIFEST.open() if l.strip()}


def census() -> dict:
    out = {}
    for line in CENSUS.open():
        if line.strip():
            row = json.loads(line)
            out[row["page_id"]] = row
    return out


def verdicts() -> dict:
    out = {}
    for path in sorted((ROOT / "tests" / "fixtures").glob(
            "attachment_verify*.csv")):
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for row in csv.DictReader(io.StringIO(raw)):
            if "+" not in row.get("item", ""):
                continue
            try:
                a, b = row["item"].split()[-1].split("+")
                out[(row["record_id"].strip(), int(row["file_index"]),
                     int(a.lstrip("p")), int(b.lstrip("p")))] = (
                    row.get("verdict") or "").strip().lower()
            except (ValueError, TypeError):
                continue
    return out


def boxes_of(recs, cache, record_id, file_index, page):
    """The printed box labels the reader cited, and what family they imply."""
    pdf = RAW / record_id / recs[record_id]["files"][file_index]["name"]
    hit = cache.get(cache.key(render.doc_hash(pdf), page, "identity"))
    if not hit:
        return None, []
    read = identity.parse(hit["body"], page)
    votes, cited = Counter(), []
    for field, label in (read.found_in or {}).items():
        if not label:
            continue
        match = BOX.match(label)
        low = label.lower()
        for needle, box in KEY:
            if needle in low:
                cited.append(f"{field}: {label.strip()[:60]}")
                if match:
                    family = FAMILY.get((box, int(match.group(1))))
                    if family:
                        votes[family] += 1
                break
    if not votes:
        return None, cited
    ranked = votes.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None, cited
    return ranked[0][0], cited


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verdict", default="yes",
                    help="which of your judgements to lay out (default yes)")
    args = ap.parse_args()

    render.preflight()
    recs, cen, judged = records(), census(), verdicts()
    cache = classify.ResultCache(IDENTITY_CACHE,
                                 prompt_hash=identity.PROMPT_HASH)

    wanted = []
    for line in DOCS.open():
        if not line.strip():
            continue
        doc = json.loads(line)
        if len(doc["pages"]) < 2:
            continue
        rid, fi, face = doc["record_id"], int(doc["file_index"]), doc["face"]
        face_class = (cen.get(f"{rid}-{fi}-{face}") or {}).get("form_class")
        for page in doc["pages"]:
            if page == face:
                continue
            child_class = (cen.get(f"{rid}-{fi}-{page}") or {}).get(
                "form_class")
            if child_class == face_class:
                continue
            if judged.get((rid, fi, page, face)) != args.verdict:
                continue
            wanted.append((rid, fi, face, page, face_class, child_class))

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Cross-family attachments you judged correct",
        "",
        "These are the pairs a \"same form family or no attachment\" rule "
        "would delete.",
        "The census gives the two pages different form classes. You judged the "
        "pairing",
        "correct. So the census is wrong about one of the two pages, and the "
        "printed",
        "field numbers say which (DEFECTS #59).",
        "",
        "G-1 numbers its back-page boxes 19 / 24 / 28 for Notice of Intention, "
        "Location",
        "of Well and Total Depth. W-2 numbers the same three 26 / 31 or 32 / "
        "35 or 36.",
        "",
        "Each folder holds the face first, then the attached page.",
        "",
    ]
    for n, (rid, fi, face, page, fc, cc) in enumerate(sorted(wanted), 1):
        family, cited = boxes_of(recs, cache, rid, fi, page)
        folder = OUT / f"{n:02d}_{rid}-{fi}_p{page}_to_p{face}"
        folder.mkdir(parents=True, exist_ok=True)
        pdf = RAW / rid / recs[rid]["files"][fi]["name"]
        for role, number in (("face", face), ("attached", page)):
            image = render.downscale_image(
                render.extract_page_image(pdf, number).convert("RGB"),
                cap=2400)
            image.save(folder / f"{role}_p{number:03d}.png")
        verdict = ("agrees with the face" if family == fc
                   else "still disagrees" if family
                   else "no numbered back box cited, so it abstains")
        lines += [
            f"## {n:02d}. {rid}-{fi}, page {page} attached to face {face}",
            "",
            f"- census: face `{fc}`, attached page `{cc}`",
            f"- printed field numbers on the attached page: "
            f"**{family or 'abstain'}** ({verdict})",
        ]
        lines += [f"  - cited `{c}`" for c in cited] or ["  - cited nothing"]
        lines.append("")
        print(f"  {folder.name}   census {fc}/{cc}   boxes say "
              f"{family or 'abstain'}")

    (OUT / "README.md").write_text("\n".join(lines))
    print(f"\n{len(wanted)} pairs in {OUT}")


if __name__ == "__main__":
    main()
