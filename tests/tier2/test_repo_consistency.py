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

#: README.md joined this list on 2026-08-31, when it stopped being a template
#: and started carrying measured numbers. It is the document most likely to be
#: read by somebody who cannot check it, which makes it the one drift hurts
#: most.
DOCS = ("CLAUDE.md", "HANDOFF.md", "SETUP.md", "README.md")

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
        "68",          # the OCR floor in records (DEFECTS #15), not a corpus
                       # count: records with a legible G-1 or W-2 header
    },
    "files": set(),
    "pages": {
        "60",          # the stage-1 hand-labelled sample
        "157",         # other_form pages in the 2026-08-31 census
        "143",         # the stage-2 stratified sample, drawn 2026-08-31
        "373",         # the P-5 header leak before DEFECTS #11, and still
                       # wrong after it (DEFECTS #20)
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


# --------------------------------------------------------------- DEFECTS #31

PROTOCOL = ROOT / "docs" / "labeling-protocol-extract.md"

#: Phrases that decide an outcome. A tripwire, not a parser: the list is
#: short and curated, and it exists because the one time this went wrong the
#: offending sentence used the first of them.
DECIDING = ("is the number that decides", "the number that decides",
            "decides the", "governs the", "is what decides")

#: Every genuine decision rule carries this marker. Stage four has two
#: because it grades two mechanisms against two different bars.
MARKER = "**DECISION RULE:**"

#: A clause kept verbatim as the record of a mistake, with its correction
#: appended below it. Origin: DEFECTS #31.
SUPERSEDED = "**SUPERSEDED"
EXPECTED_MARKERS = {"two": 1, "three": 1, "four": 2}


def _stages():
    """Each '## Box grading, stage N' section, by its word-number."""
    import re
    text = PROTOCOL.read_text(encoding="utf-8")
    heads = list(re.finditer(r"^## Box grading, stage (\w+)", text, re.M))
    out = {}
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        out[head.group(1)] = text[head.start():end]
    return out


def test_each_grading_stage_marks_its_decision_rules():
    """Origin: DEFECTS #31. A pre-registration with two decision clauses is
    not a pre-registration, and the second one was written by accident while
    documenting a caveat. Marking them makes the count checkable."""
    stages = _stages()
    assert set(stages) >= set(EXPECTED_MARKERS), sorted(stages)
    for stage, expected in EXPECTED_MARKERS.items():
        found = stages[stage].count(MARKER)
        assert found == expected, (
            f"stage {stage} carries {found} decision-rule markers, "
            f"expected {expected}")


def test_no_stage_decides_an_outcome_outside_a_marked_rule():
    """The specific shape of DEFECTS #31: a sentence naming which figure
    decides an outcome, sitting in a section meant to record a caveat.

    Two things are allowed through, and both have to be. A blockquote, which
    is where a correction is appended and which must be able to quote the
    mistake it is correcting. And a paragraph explicitly marked SUPERSEDED,
    because the offending sentence is kept verbatim on purpose: a
    pre-registration that quietly edits out the clause it failed to honour
    would be worth nothing.
    """
    offenders = []
    for stage, body in _stages().items():
        marked = superseded = False
        for line in body.splitlines():
            if MARKER in line:
                marked = True
                continue
            if SUPERSEDED in line:
                superseded = True
                continue
            if line.startswith("### "):
                marked = superseded = False
            if marked or superseded or line.lstrip().startswith(">"):
                continue
            if any(phrase in line.lower() for phrase in DECIDING):
                offenders.append((stage, line.strip()))
    assert not offenders, (
        "a sentence decides an outcome outside a marked DECISION RULE:\n"
        + "\n".join(f"  stage {s}: {l}" for s, l in offenders))
