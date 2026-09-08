#!/usr/bin/env python3
"""Score extraction against the hand-keyed ground truth.

Reads tests/fixtures/extract_truth.csv and the smoke run's result cache. No
API calls: every document is a cache hit, so this is repeatable for free.

Two reporting rules were fixed before the ground truth was keyed and are
applied here rather than chosen after seeing a number:

  DEFECTS #23  Document 1, record 1493495, is the document the schema was
               designed on and the probe measured. It is excluded from the
               headline and reported separately.
  DEFECTS #25  Documents 6, 8 and 9 are sections separated from their faces,
               so their identity fields test absence detection rather than
               extraction. Reported separately.

Three value comparisons, and which were decided when is stated rather than
buried:

  exact        the two strings equal after stripping surrounding whitespace
  normalised   also casefolds, collapses internal whitespace, drops commas
               and trailing punctuation
  equivalent   dates compared as dates and depths as numbers, using the
               parsers in pipeline/validate.py

exact and normalised were fixed before the ground truth was keyed. **equivalent
was added after the first scoring run**, when it showed 0 of 7 on dates because
"4-23-75" and "1975-04-23" are the same date written twice. That is a real
result about representation rather than about extraction, and it is reported as
its own column rather than folded into the others.

The labels carry raw text, as the protocol instructed, so comparison is against
the model's `raw` field. Comparing against its normalised `value` was the first
version of this script and it scored every date wrong.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import classify                      # noqa: E402
from pipeline import extract as ex                 # noqa: E402
from pipeline import extractor                     # noqa: E402
from pipeline.validate import parse_date, parse_depth   # noqa: E402

TRUTH = ROOT / "tests" / "fixtures" / "extract_truth.csv"
CACHE = ROOT / "data" / "extract" / "cache_smoke.jsonl"
SMOKE = ROOT / "data" / "extract" / "smoke.jsonl"

#: Which run is being scored, switched by --results/--cache so the batched
#: arm can be scored against the same truth. Module-level because the
#: helpers below are called from several places; set once in main.
RUN = {"results": SMOKE, "cache": CACHE}
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"

DESIGNED_ON = 1                 # DEFECTS #23
FACELESS = (6, 8, 9)            # DEFECTS #25

IDENTITY = tuple(f"identity.{f}" for f in ex.IDENTITY_FIELDS)


def normalise(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip()).casefold()
    return re.sub(r"[.,;:]+$", "", text.replace(",", ""))


def equivalent(want: str, got: str) -> bool:
    """Same value, possibly written differently.

    A date keyed 4-23-75 and returned 1975-04-23 is one correct extraction and
    two spellings. So is a depth keyed 9200' and returned 9200.
    """
    if normalise(want) == normalise(got):
        return True
    if not want or not got:
        return False
    first, second = parse_date(want), parse_date(got)
    if first and second:
        return first == second
    first, second = parse_depth(want), parse_depth(got)
    if first is not None and second is not None:
        # Only when neither side carries anything but the number, or a
        # unit mark. "8-1/2 inch casing" is not a depth.
        if re.fullmatch(r"[^\d]*[\d,]+(\.\d+)?['\"]?[^\d]*", want.strip()):
            return first == second
    return False


def truth():
    docs: dict[int, dict] = {}
    for row in csv.DictReader(TRUTH.open(encoding="utf-8-sig")):
        seq = int(row["seq"])
        doc = docs.setdefault(seq, {"record_id": row["record_id"],
                                    "pages": tuple(int(p) for p in
                                                   row["pages"].split()),
                                    "fields": {}})
        doc["fields"][row["field"]] = {
            "status": row["status"].strip(),
            "value": row["value"].strip(),
            "note": row["note"].strip()}
    return docs


def file_indexes() -> dict[tuple[str, tuple[int, ...]], int]:
    """(record, pages) -> file index, from the run that produced the results.

    The ground-truth sheet carries a record id and page numbers but not a file
    index, and a record can hold five files. Records drawn from file 1 would
    otherwise be hashed against file 0 and quietly miss the cache. The sheet
    should carry the index; until it is redrawn, the run is the source.
    """
    smoke = RUN["results"]
    out = {}
    if smoke.exists():
        for line in smoke.open():
            if line.strip():
                row = json.loads(line)
                record, index, _ = row["page_id"].rsplit("-", 2)
                out[(record, tuple(row["pages"]))] = int(index)
    return out


def files_of(record_id: str):
    for line in MANIFEST.open():
        if line.strip() and json.loads(line)["record_id"] == record_id:
            return json.loads(line)["files"]
    sys.exit(f"{record_id} not in the manifest")


def run_prompt_hash() -> str:
    """The prompt the scored run used, not whatever the prompt is today."""
    return extractor.recorded_prompt_hash(RUN["results"])


def extracted(doc) -> ex.CompletionReport | None:
    index = file_indexes().get((doc["record_id"], doc["pages"]), 0)
    pdf = RAW / doc["record_id"] / files_of(doc["record_id"])[index]["name"]
    cache = classify.ResultCache(RUN["cache"], prompt_hash=run_prompt_hash())
    result = extractor.extract_document(
        None, pdf, doc["pages"], record_id=doc["record_id"],
        file_index=index, cache=cache)
    if not result.cached:
        sys.exit("a document was not in the cache; run `make smoke` first")
    return result.report


def model_field(report, name: str):
    """The model's value object for a dotted field name, or None."""
    group, _, field = name.partition(".")
    if group == "document":
        return report.form_revision if field == "form_revision" else None
    source = {"identity": report.identity, "completion": report.completion,
              "test": report.test}.get(group, {})
    return source.get(field)


def compare(docs) -> list[dict]:
    rows = []
    for seq, doc in sorted(docs.items()):
        report = extracted(doc)
        for name, want in doc["fields"].items():
            got = model_field(report, name) if report else None
            got_status = got.status.value if got else "missing"
            # raw first: the protocol has the labels carrying what is written
            # on the page, so the model's raw is the comparable field. Using
            # its normalised value scored every date wrong.
            got_value = (got.raw or got.value or "") if got else ""
            rows.append({
                "seq": seq, "field": name, "group": name.split(".")[0],
                "want_status": want["status"], "got_status": got_status,
                "want_value": want["value"], "got_value": got_value,
                "note": want["note"],
                "status_ok": want["status"] == got_status,
                "exact": want["value"].strip() == got_value.strip(),
                "normalised": normalise(want["value"]) == normalise(got_value),
                "equivalent": equivalent(want["value"], got_value),
                "revision": doc["fields"].get(
                    "document.form_revision", {}).get("value", "") or "unknown",
            })
    return rows


def table(rows, title):
    if not rows:
        print(f"\n{title}\n   nothing in this slice")
        return
    status = sum(r["status_ok"] for r in rows)
    both = [r for r in rows
            if r["want_status"] == "present" and r["got_status"] == "present"]
    wanted = [r for r in rows if r["want_status"] == "present"]
    print(f"\n{title}   ({len(rows)} fields)")
    print(f"   status correct        {status:4d}/{len(rows):<4d} "
          f"{status / len(rows):6.1%}")
    if both:
        print(f"   value exact          {sum(r['exact'] for r in both):4d}"
              f"/{len(both):<4d} {sum(r['exact'] for r in both) / len(both):6.1%}"
              "   (both say present)")
        print(f"   value normalised     "
              f"{sum(r['normalised'] for r in both):4d}/{len(both):<4d} "
              f"{sum(r['normalised'] for r in both) / len(both):6.1%}")
        print(f"   value equivalent     "
              f"{sum(r['equivalent'] for r in both):4d}/{len(both):<4d} "
              f"{sum(r['equivalent'] for r in both) / len(both):6.1%}"
              "   (dates as dates, depths as numbers)")
    if wanted:
        recovered = sum(r["equivalent"] for r in wanted)
        print(f"   recovered            {recovered:4d}/{len(wanted):<4d} "
              f"{recovered / len(wanted):6.1%}   "
              "(a value exists and the model has it)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--detail", action="store_true",
                    help="print every disagreement")
    ap.add_argument("--results", type=Path, default=SMOKE,
                    help="run results jsonl (default: the live smoke run)")
    ap.add_argument("--cache", type=Path, default=CACHE,
                    help="that run's result cache")
    args = ap.parse_args()
    RUN["results"], RUN["cache"] = args.results, args.cache

    # A clean clone has neither the corpus nor a finished run, and the
    # honest answer is a sentence, not a traceback (DEFECTS #75).
    for path, what in ((MANIFEST, "the fetched corpus"),
                       (args.results, "a finished extraction run"),
                       (args.cache, "that run's cache")):
        if not Path(path).exists():
            sys.exit(f"{path} is missing: scoring needs {what}. data/ is "
                     "never committed; see README, Running it.")

    docs = truth()
    rows = compare(docs)
    print(f"{len(docs)} documents, {len(rows)} fields\n" + "=" * 72)

    headline = [r for r in rows if r["seq"] != DESIGNED_ON
                and not (r["seq"] in FACELESS and r["group"] == "identity")]
    table(headline, "HEADLINE  (excludes document 1, and identity on 6/8/9)")

    for group in ("identity", "completion", "test", "document"):
        table([r for r in headline if r["group"] == group],
              f"  by group: {group}")

    print("\n" + "=" * 72)
    table([r for r in rows if r["seq"] == DESIGNED_ON],
          "DOCUMENT 1 ALONE  (DEFECTS #23: the schema was designed on it)")
    table([r for r in rows if r["seq"] in FACELESS and r["group"] == "identity"],
          "IDENTITY ON 6/8/9  (DEFECTS #25: absence detection, not extraction)")

    print("\n" + "=" * 72)
    print("STATUS CONFUSION, headline slice")
    print("=" * 72)
    matrix = Counter((r["want_status"], r["got_status"]) for r in headline)
    for (want, got), n in sorted(matrix.items(), key=lambda kv: -kv[1]):
        flag = "" if want == got else "   <-- disagreement"
        print(f"   {n:4d}  labelled {want:22s} model {got:22s}{flag}")

    print("\n" + "=" * 72)
    print("BY FORM ERA, headline slice")
    print("=" * 72)
    by_era = defaultdict(list)
    for row in headline:
        by_era[row["revision"] or "unknown"].append(row)
    for era, group in sorted(by_era.items()):
        ok = sum(r["status_ok"] for r in group)
        both = [r for r in group if r["want_status"] == r["got_status"] == "present"]
        value = (sum(r["equivalent"] for r in both) / len(both)) if both else None
        shown = f"{value:6.1%}" if value is not None else "     -"
        print(f"   {era:20s} n={len(group):4d}  status {ok / len(group):6.1%}"
              f"  value {shown}")

    noted = [r for r in headline if r["note"]]
    if noted:
        print(f"\n   {len(noted)} headline fields carry a note; "
              f"status correct on {sum(r['status_ok'] for r in noted)}")

    if args.detail:
        print("\n" + "=" * 72)
        print("DISAGREEMENTS")
        print("=" * 72)
        for row in headline:
            if row["status_ok"] and (row["equivalent"] or
                                     row["want_status"] != "present"):
                continue
            print(f"   doc {row['seq']:>2} {row['field']:34s}")
            print(f"      labelled {row['want_status']:20s} {row['want_value'][:40]!r}")
            print(f"      model    {row['got_status']:20s} {row['got_value'][:40]!r}")
            if row["note"]:
                print(f"      note: {row['note'][:60]}")


if __name__ == "__main__":
    main()
