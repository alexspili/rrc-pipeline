"""Tier 2: the repo's own invariants, checked against files on disk.

These are not pipeline tests. They pin claims the repository makes about
itself, which is where this project has actually been losing to drift:
CLAUDE.md's index pointed at files git never had (commit 8248354), and the
Makefile shipped recipes make cannot parse (DEFECTS #8).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- makefile

def test_makefile_recipe_lines_begin_with_tab():
    """Origin: DEFECTS #8. SETUP.md step 3 writes the Makefile from a heredoc
    indented inside the document; a plain heredoc does not strip that
    indentation, so the recipe lines lost their tabs and every target died
    with "missing separator". Nothing caught it because no test ran make.
    """
    lines = (ROOT / "Makefile").read_text().splitlines()
    target = re.compile(r"^[A-Za-z0-9_./%$()-]+:")

    offenders, in_recipe = [], False
    for n, line in enumerate(lines, 1):
        if target.match(line):
            in_recipe = True
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            in_recipe = False
            continue
        if in_recipe and not line.startswith("\t"):
            offenders.append((n, line))

    assert not offenders, (
        "Makefile recipe lines must start with a literal tab; make reports "
        "'missing separator' otherwise. Offending lines: "
        + "; ".join(f"{n}: {line!r}" for n, line in offenders)
    )


# ---------------------------------------------------------------- corpus counts

DOCS = ("CLAUDE.md", "HANDOFF.md", "SETUP.md")

# Numbers that are followed by "records"/"files"/"pages" but describe something
# other than this corpus. Each one is listed deliberately; an unlisted number
# is treated as a corpus claim and must match the manifest.
NOT_CORPUS_COUNTS = {
    "records": {
        "1,907,311",   # every record in profile 17, from the DEFECTS #3 run
        "0",           # the empty 01/2005-01/2007 backfile window
        "2015",        # a year, in "2015 records return well logs/P-17s only"
        "83",          # records holding a form page with no form number,
                       # from the 2026-08-31 census page-grouping finding
    },
    "files": set(),
    "pages": {
        "60",          # the stage-1 hand-labelled sample
        "157",         # other_form pages in the 2026-08-31 census
    },
}

CLAIM = re.compile(r"(?<![\w-])([\d,]+)\s+(records|files|pages)")


def _manifest_counts():
    manifest = ROOT / "data" / "manifest.jsonl"
    if not manifest.exists():
        return None
    import json

    records = [json.loads(line) for line in manifest.open() if line.strip()]
    files = [f for r in records for f in r["files"]]
    return {
        "records": len(records),
        "files": len(files),
        "pages": sum(f.get("pages") or 0 for f in files),
    }


def test_docs_state_the_corpus_the_manifest_actually_holds():
    """Origin: DEFECTS #6. CLAUDE.md and HANDOFF.md recorded a closed corpus of
    198/242/3,640 while data/manifest.jsonl held 202/249/3,689, four records
    having been fetched after the docs were written. "This file stays current"
    was a promise with no enforcement, so the corpus moved and the docs did
    not. Now a corpus change breaks the build until the docs are updated with
    it.

    Skipped, not failed, when data/ is absent: the corpus is git-ignored
    (personal data, CLAUDE.md rule 3), so a fresh clone cannot check this.
    """
    truth = _manifest_counts()
    if truth is None:
        import pytest

        pytest.skip("data/manifest.jsonl absent; corpus is git-ignored")

    wrong = []
    for name in DOCS:
        text = re.sub(r"\s+", " ", (ROOT / name).read_text())
        for value, noun in CLAIM.findall(text):
            if value in NOT_CORPUS_COUNTS[noun]:
                continue
            if int(value.replace(",", "")) != truth[noun]:
                wrong.append(f"{name}: {value} {noun} (manifest: {truth[noun]:,})")

    assert not wrong, (
        "Docs disagree with data/manifest.jsonl. Update the docs, or add the "
        "number to NOT_CORPUS_COUNTS if it describes something else:\n  "
        + "\n  ".join(wrong)
    )


# ------------------------------------------------------------------- page ids

def test_every_page_in_the_corpus_gets_a_unique_batch_id():
    """The tier-1 test freezes 20 rows; this sweeps all of them. Batch results
    come back in arbitrary order keyed only by custom_id, so a collision would
    silently attach one page's label to another page.
    """
    manifest = ROOT / "data" / "manifest.jsonl"
    if not manifest.exists():
        import pytest

        pytest.skip("data/manifest.jsonl absent; corpus is git-ignored")

    import json

    from pipeline import pageclass as pc

    ids = []
    for line in manifest.open():
        if not line.strip():
            continue
        record = json.loads(line)
        for index, entry in enumerate(record["files"]):
            for page in range(1, (entry.get("pages") or 0) + 1):
                ids.append(pc.page_id(record["record_id"], index, page))

    assert ids, "manifest present but yielded no pages"
    assert len(set(ids)) == len(ids), "page id collision"
    assert max(len(i) for i in ids) <= 64
    assert all(pc.parse_page_id(i) for i in ids)
