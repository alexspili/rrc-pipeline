#!/usr/bin/env python3
"""Measure reassembly against the pre-registered rule.

The rule, the must-attach cases and the must-not-attach cases are fixed in
docs/labeling-protocol-reassemble.md and were amended to be two-sided before
this ran (DEFECTS #35). Read it before reading this.

Reads the identity fields off every page of the ground-truth records with
pipeline.identity, caches them by (document hash, prompt hash) under
CLAUDE.md rule 7, groups each file, and reports both sides plus the
contradicted-but-agreeing list in full.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import identity                      # noqa: E402
from pipeline import pageclass as pc               # noqa: E402
from pipeline import reassemble as ra              # noqa: E402
from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
CACHE = ROOT / "data" / "extract" / "cache_identity.jsonl"
OUT = ROOT / "data" / "extract" / "reassemble.jsonl"
REPORT = ROOT / "data" / "extract" / "reassemble_report.txt"

#: The records the ground-truth documents come from, plus the worked cases.
RECORDS = ("1493495", "1493540", "1493608", "1494274", "1494690", "1494774",
           "1494847", "1494905", "1495193", "1495195", "1495350", "1499700",
           "1504957", "1505031", "1510666", "1511465", "1912687", "1995378",
           "1760703")

#: Fixed in the protocol before this ran. (record, file, page) -> face page.
MUST_ATTACH = {
    "A": (("1493495", 0, 10), 9, "confirmed"),
    "B": (("1495193", 0, 8), 7, "confirmed"),
    "C": (("1495195", 0, 6), None, "probable"),
    "D": (("1495195", 0, 38), None, "probable"),
}
MUST_NOT_ATTACH = {"E": (("1495193", 0, 8), 9)}


def census_pages():
    out = {}
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        record_id, file_index, page = pc.parse_page_id(row["page_id"])
        if record_id in RECORDS:
            out[(record_id, file_index, page)] = row
    return out


def read_identity(client, pdf: Path, page: int, cache, key: str):
    """Cached by (document hash, page, prompt hash), per CLAUDE.md rule 7.

    The key comes from the cache's own `key()` so the prompt hash is in it.
    Building the key here would have left the prompt out, which is the whole
    thing rule 7 exists to prevent.
    """
    hit = cache.get(key)
    if hit is not None:
        return identity.parse(hit["body"], page)
    if client is None:
        return None
    response = client.messages.create(
        model=identity.MODEL, max_tokens=identity.MAX_TOKENS,
        system=identity.SYSTEM,
        messages=[{"role": "user",
                   "content": identity.build_content(pdf, page)}])
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"truncated on {key}; never cached")
    # Same as pipeline/extractor.py: the response may open with a thinking
    # block, so take the text blocks rather than the first block.
    body = "".join(b.text for b in response.content if b.type == "text")
    cache.put(key, {"body": body,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens})
    return identity.parse(body, page)


class Tee:
    """Print and keep. My own `tail -55` discarded the must-attach section of
    the first run and the verdicts had to be reconstructed from the results
    file, so the report is written as well as printed."""

    def __init__(self, path):
        self.lines = []
        self.path = path

    def __call__(self, *parts):
        text = " ".join(str(p) for p in parts)
        print(text)
        self.lines.append(text)

    def close(self):
        self.path.write_text("\n".join(self.lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true",
                    help="cache only; make no API calls")
    args = ap.parse_args()
    say = Tee(REPORT)

    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    cache = classify.ResultCache(CACHE, prompt_hash=identity.PROMPT_HASH)
    client = None if args.offline else __import__("anthropic").Anthropic()

    pages = census_pages()
    wanted = {k: v for k, v in pages.items()
              if v.get("form_class") in ("w2", "g1", "other_form")}
    say(f"{len(wanted)} pages over {len(RECORDS)} records\n")

    built, missing, failures = {}, 0, []
    for (record_id, file_index, page), row in sorted(wanted.items()):
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        key = cache.key(render.doc_hash(pdf), page, "identity")
        try:
            values = read_identity(client, pdf, page, cache, key)
        except Exception as exc:                   # noqa: BLE001
            failures.append((record_id, file_index, page, str(exc)[:80]))
            continue
        if values is None:
            missing += 1
            continue
        built[(record_id, file_index, page)] = ra.PageRecord(
            record_id=record_id, file_index=file_index, page=page,
            form_class=row["form_class"], part=row.get("part"),
            identity=identity.identity_for(values))
    if missing:
        say(f"  {missing} pages not in cache; rerun without --offline")
    if failures:
        say(f"  {len(failures)} pages failed and are reported, not hidden:")
        for record_id, file_index, page, why in failures:
            say(f"    {record_id}-{file_index}-{page}: {why}")
    say()

    by_file = {}
    for key, record in built.items():
        by_file.setdefault(record.file_key, []).append(record)

    documents, unattached, contradicted = [], [], []
    for file_key, group in sorted(by_file.items()):
        docs, left = ra.group(group)
        documents += [(file_key, d) for d in docs]
        unattached += [(file_key, u) for u in left]
        contradicted += ra.contradicted_but_agreeing(group)

    attached = sum(len(d.pages) - 1 for _, d in documents)
    say(f"documents {len(documents)}, pages attached {attached}, "
          f"unattached {len(unattached)}")
    from collections import Counter
    say("  unattached by reason:",
          dict(Counter(u.reason for _, u in unattached)))

    home = {}
    for _, doc in documents:
        for p in doc.pages:
            if p.page != doc.face.page:
                home[(p.record_id, p.file_index, p.page)] = doc.face.page

    say("\nMUST-ATTACH (pre-registered)")
    for name, (target, face, grade) in MUST_ATTACH.items():
        got = home.get(target)
        if face is None:
            verdict = f"attached to page {got}" if got else "NOT ATTACHED"
        else:
            verdict = "PASS" if got == face else (
                f"FAIL, attached to {got}" if got else "FAIL, not attached")
        say(f"  {name} {target} -> expected {face} ({grade}): {verdict}")

    say("\nMUST-NOT-ATTACH (pre-registered)")
    for name, (target, forbidden) in MUST_NOT_ATTACH.items():
        got = home.get(target)
        say(f"  {name} {target} must not attach to {forbidden}: "
              f"{'PASS' if got != forbidden else 'FAIL'} (attached to {got})")

    say(f"\nCONTRADICTED BUT AGREEING ({len(contradicted)} pairs) "
          "-- read by eye before the semantics are settled")
    for candidate, face, disagreed, agreed in contradicted:
        say(f"  {candidate.record_id}-{candidate.file_index} "
              f"p{candidate.page} vs face p{face.page}")
        for field in disagreed:
            say(f"      DISAGREE {field}: "
                  f"{candidate.identity.get(field)!r} vs "
                  f"{face.identity.get(field)!r}")
        say(f"      agreed on: {', '.join(agreed)}")

    with OUT.open("w") as fh:
        for file_key, doc in documents:
            fh.write(json.dumps({
                "record_id": file_key[0], "file_index": file_key[1],
                "face": doc.face.page,
                "pages": [p.page for p in doc.pages],
                "evidence": [[p, list(f)] for p, f in doc.evidence]}) + "\n")
    say(f"\n{OUT}")
    say(f"{REPORT}")
    say.close()


if __name__ == "__main__":
    main()
