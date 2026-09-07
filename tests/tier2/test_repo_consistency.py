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
        "28,827",      # every record the district 02 / 2007-2009 search
                       # matches, of which 155 were pulled (2026-09-07). It is
                       # the number that proved the session was binding, since
                       # an unprimed one returns the whole archive.
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
    """What the manifest holds, in total and per district.

    Two populations since 2026-09-07: district 03, closed, which every
    measurement in the docs rests on, and district 02, the sitting frame. A
    document may legitimately state either subtotal or the total, so all three
    are returned and a claim matching any of them passes. A claim matching none
    of them is drift, which is what DEFECTS #6 is about.
    """
    manifest = ROOT / "data" / "manifest.jsonl"
    if not manifest.exists():
        return None
    import json
    from collections import defaultdict

    records = [json.loads(line) for line in manifest.open() if line.strip()]
    by_district = defaultdict(list)
    for record in records:
        by_district[(record.get("meta") or {}).get("district") or "?"].append(record)

    def counts(rows):
        files = [f for r in rows for f in r["files"]]
        return {"records": len(rows), "files": len(files),
                "pages": sum(f.get("pages") or 0 for f in files)}

    populations = [counts(records)] + [counts(rows)
                                       for rows in by_district.values()]
    return {noun: {p[noun] for p in populations}
            for noun in ("records", "files", "pages")}


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
            if int(value.replace(",", "")) not in truth[noun]:
                allowed = ", ".join(f"{v:,}" for v in sorted(truth[noun]))
                wrong.append(f"{name}: {value} {noun} "
                             f"(manifest holds: {allowed})")

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

#: Every labelling protocol, not just the one whose failure prompted the
#: check. Origin: DEFECTS #35. The first version of this test scanned one
#: file's stage headings, so the reassembly protocol repeated the same defect
#: two hours later and the test found nothing to look at. A rule scoped to
#: the shape of the instance rather than the shape of the failure is not a
#: rule.
PROTOCOLS = sorted((ROOT / "docs").glob("labeling-protocol-*.md"))

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


def test_the_overlay_scripts_carry_no_draw_loop_of_their_own():
    """Origin: DEFECTS #33. The bug lived in two near-identical copies of a
    drawing loop, so fixing it in one would have left it in the other. This
    is the test that stops the copies coming back."""
    offenders = []
    for name in ("overlay_boxes.py", "probe_boxes.py"):
        body = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for symbol in ("ImageDraw", "ImageFont"):
            if symbol in body:
                offenders.append(f"{name} imports or uses {symbol}")
    assert not offenders, (
        "drawing belongs in pipeline.render.draw_numbered_boxes:\n  "
        + "\n  ".join(offenders))


MODULES = ROOT / "docs" / "modules"


def test_every_module_file_meets_the_convention_the_readme_claims():
    """The README tells a reader that every module file carries a numbered
    rule section and a RETIRED section. Two of the three did not.

    A README claiming a convention the files do not meet is the drift this
    repo already logs elsewhere, and it is worse here than in code, because
    the claim is the thing being shown to a reader who cannot check it
    quickly. So the claim is a test.
    """
    import re
    missing = []
    for path in sorted(MODULES.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        if not re.search(r"^## Rules\s*$", body, re.M):
            missing.append(f"{path.name}: no '## Rules' section")
        elif not re.search(r"^R\d+\. ", body, re.M):
            missing.append(f"{path.name}: Rules section has no numbered rule")
        if not re.search(r"^## RETIRED\s*$", body, re.M):
            missing.append(f"{path.name}: no '## RETIRED' section")
    assert not missing, "\n  ".join([""] + missing)


def test_every_numbered_rule_names_what_pins_it():
    """A rule with no pin is a note. The README's example carries one, so
    every rule has to."""
    import re
    orphans = []
    for path in sorted(MODULES.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        blocks = re.split(r"^(R\d+\.)", body, flags=re.M)[1:]
        for head, text in zip(blocks[::2], blocks[1::2]):
            if "Pinned by:" not in text:
                orphans.append(f"{path.name} {head}")
    assert not orphans, "rules with no pin:\n  " + "\n  ".join(orphans)


def _decision_sections(body: str):
    """Sections of a protocol that can carry a decision rule.

    Either a stage heading, as the extraction protocol uses, or the whole
    document, as the shorter protocols do.
    """
    import re
    heads = list(re.finditer(r"^## Box grading, stage (\w+)", body, re.M))
    if not heads:
        return {"(whole document)": body}
    out = {}
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(body)
        out[head.group(1)] = body[head.start():end]
    return out


def test_every_protocol_that_decides_something_marks_where():
    """Origin: DEFECTS #35.

    Not every protocol decides an outcome. Two of these are labelling
    instructions and have nothing to decide, so requiring a marker of them
    would be ceremony. The invariant is narrower and is the one that failed:
    a protocol that decides an outcome says where.
    """
    missing = []
    for path in PROTOCOLS:
        body = path.read_text(encoding="utf-8")
        decides = any(phrase in body.lower() for phrase in DECIDING)
        if decides and MARKER not in body:
            missing.append(path.name)
    assert not missing, (
        "protocols that decide an outcome with no marked rule: "
        + ", ".join(missing))


def test_no_protocol_decides_an_outcome_outside_a_marked_rule():
    """The generalised form of DEFECTS #31's check, after #35 showed the
    first version only looked where the first failure happened."""
    offenders = []
    for path in PROTOCOLS:
        for name, body in _decision_sections(
                path.read_text(encoding="utf-8")).items():
            marked = superseded = False
            for line in body.splitlines():
                if MARKER in line:
                    marked = True
                    continue
                if SUPERSEDED in line:
                    superseded = True
                    continue
                if line.startswith("### ") and not marked:
                    superseded = False
                if line.startswith("## ") and MARKER not in line:
                    marked = superseded = False
                if marked or superseded or line.lstrip().startswith(">"):
                    continue
                if any(phrase in line.lower() for phrase in DECIDING):
                    offenders.append((path.name, name, line.strip()))
    assert not offenders, (
        "a sentence decides an outcome outside a marked DECISION RULE:\n"
        + "\n".join(f"  {f} [{s}]: {l}" for f, s, l in offenders))
