"""Tier 2: the stage-2 sample is well-formed, and still matches its frame.

Two jobs. The first is the stage-1 one: stay quiet while the sheet is blank,
go loud the moment a value is mistyped, because a label typo scores a correct
prediction as wrong and nothing downstream can catch it.

The second is new and matters more. Stage 2 is stratified, so every number it
produces is weighted by a frame size measured before the draw. If the census
file changes underneath the labels, those weights are wrong and the estimate is
quietly wrong with them. So the strata are recomputed from
data/census/vision_1000.jsonl on every run and compared with the committed key.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from pipeline import formscan
from pipeline import pageclass as pc
from pipeline import stage2

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "tests" / "fixtures" / "labels_stage2.csv"
STRATA = ROOT / "tests" / "fixtures" / "stage2_strata.csv"
CENSUS = ROOT / "data" / "census" / "vision_1000.jsonl"
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"

TOTAL = sum(stage2.ALLOCATION.values())


def _sheet():
    if not LABELS.exists():
        pytest.skip("stage-2 sample not drawn yet: make label2")
    return list(csv.DictReader(LABELS.open(encoding="utf-8-sig")))


def _key():
    if not STRATA.exists():
        pytest.skip("stage-2 sample not drawn yet: make label2")
    return list(csv.DictReader(STRATA.open(encoding="utf-8-sig")))


def _labelled():
    rows = _sheet()
    if not any(row["form_class"].strip() for row in rows):
        pytest.skip("stage-2 label set not filled in yet")
    return rows


# ------------------------------------------------------- shape and blinding

def test_the_sample_is_the_agreed_size():
    assert len(_sheet()) == TOTAL == 143


def test_the_workbook_shows_the_labeller_nothing_the_model_said():
    """The sample is stratified over predictions, so the sheet leaking one
    would make every label downstream of it worthless. The stratum name alone
    gives the prediction away, which is why it lives in a separate file.
    """
    leaks = {"stratum", "predicted_class", "predicted_part", "confidence",
             "header_tokens", "alt_class", "extraction_eligible"}
    assert not leaks & set(_sheet()[0])


def test_the_rows_are_not_in_stratum_order():
    """Shuffled under ORDER_SEED. In stratum order, position would tell the
    labeller which stratum a page came from just as loudly as a column would.
    """
    key = {row["seq"]: row["stratum"] for row in _key()}
    order = [key[row["seq"]] for row in _sheet()]
    assert order != sorted(order)
    assert len(set(order[:20])) > 3, "the first rows are all one stratum"


def test_the_key_and_the_sheet_describe_the_same_pages():
    assert ([(r["seq"], r["page_id"]) for r in _sheet()]
            == [(r["seq"], r["page_id"]) for r in _key()])


def test_no_page_is_drawn_twice():
    ids = [row["page_id"] for row in _sheet()]
    assert len(set(ids)) == len(ids)


# ------------------------------------------------------------ frame integrity

def test_every_drawn_page_exists_in_the_census():
    census = {json.loads(line)["page_id"] for line in CENSUS.open()
              if line.strip()} if CENSUS.exists() else None
    if census is None:
        pytest.skip("census absent; data/ is git-ignored (CLAUDE.md rule 3)")
    missing = [row["page_id"] for row in _key() if row["page_id"] not in census]
    assert not missing, f"drawn pages no longer in the census: {missing}"


def test_the_strata_still_match_a_recount_of_the_census():
    """The load-bearing check. Frame sizes are the weights in every stage-2
    number; a census rerun that moved pages between strata would leave the
    labels valid, the arithmetic unchanged and the answer wrong.
    """
    if not (CENSUS.exists() and MANIFEST.exists() and RAW.exists()):
        pytest.skip("corpus absent; data/ is git-ignored (CLAUDE.md rule 3)")

    tokens = {pc.page_id(*coords): formscan.header_tokens(text)
              for coords, text in formscan.page_texts(MANIFEST, RAW).items()}
    frames = Counter()
    recomputed = {}
    for line in CENSUS.open():
        if not line.strip():
            continue
        row = json.loads(line)
        stratum = stage2.assign_stratum(
            row["form_class"], row["part"], bool(row["oversize"]),
            bool(row.get("error")), tokens.get(row["page_id"], set()))
        recomputed[row["page_id"]] = stratum
        if stratum is not None:
            frames[stratum] += 1

    moved = [(r["page_id"], r["stratum"], recomputed.get(r["page_id"]))
             for r in _key() if recomputed.get(r["page_id"]) != r["stratum"]]
    assert not moved, f"pages have changed stratum since the draw: {moved[:5]}"

    assert dict(frames) == {
        stage2.G1_FACE_SILENT: 43, stage2.G1_FACE_CORROBORATED: 29,
        stage2.W2_FACE_SILENT: 113, stage2.W2_FACE_W15_HEADER: 7,
        stage2.W2_FACE_CORROBORATED: 46, stage2.COMPLETION_NON_FACE: 137,
        stage2.CONFUSABLE: 361, stage2.OVERSIZE: 23, stage2.PARSE_FAILURE: 15,
    }, "frame sizes have moved; the protocol's error bars are stale"


def test_each_stratum_got_the_pages_the_protocol_allocated():
    drawn = Counter(row["stratum"] for row in _key())
    assert dict(drawn) == stage2.ALLOCATION


def test_no_oversize_page_sits_in_a_class_stratum():
    """The precedence in assign_stratum makes this true by construction. It is
    asserted anyway because the protocol states it as a measured fact about
    this corpus, and a future census could make it false.
    """
    if not CENSUS.exists():
        pytest.skip("census absent; data/ is git-ignored (CLAUDE.md rule 3)")
    oversize = {json.loads(line)["page_id"] for line in CENSUS.open()
                if line.strip() and json.loads(line)["oversize"]}
    for row in _key():
        if row["page_id"] in oversize:
            assert row["stratum"] == stage2.OVERSIZE, row["page_id"]


# ------------------------------------------------------------------- labels

def test_every_row_is_labelled():
    unlabelled = [r["page_id"] for r in _labelled() if not r["form_class"].strip()]
    assert not unlabelled, f"unlabelled rows: {', '.join(unlabelled)}"


def test_every_value_is_in_the_vocabulary():
    problems = []
    for row in _labelled():
        page_id = row["page_id"]
        try:
            form_class = pc.PageClass(row["form_class"].strip())
        except ValueError:
            problems.append(f"{page_id}: form_class={row['form_class']!r}")
            continue
        part = row["part"].strip() or None
        try:
            part = pc.Part(part) if part else None
        except ValueError:
            problems.append(f"{page_id}: part={row['part']!r}")
            continue
        try:
            orientation = pc.Orientation(row["orientation"].strip())
        except ValueError:
            problems.append(f"{page_id}: orientation={row['orientation']!r}")
            continue
        try:
            pc.PageLabel(
                record_id=row["record_id"], file_index=int(row["file_index"]),
                page=int(row["page"]), form_class=form_class, part=part,
                orientation=orientation, confidence=pc.Confidence.HIGH,
                oversize=row["oversize"] == "yes")
        except ValueError as exc:
            problems.append(f"{page_id}: {exc}")
    assert not problems, "\n  ".join([""] + problems)


def test_the_new_column_is_answered_yes_or_no():
    """`form_number_legible` is the human counterpart to the OCR header token.
    Blank rows would make the two uncomparable on exactly the pages the
    comparison is for.
    """
    bad = [(r["page_id"], r["form_number_legible"]) for r in _labelled()
           if r["form_number_legible"].strip().lower() not in {"y", "n"}]
    assert not bad, f"form_number_legible must be y or n: {bad}"


def test_page_ids_match_their_coordinates():
    for row in _sheet():
        assert pc.parse_page_id(row["page_id"]) == (
            row["record_id"], int(row["file_index"]), int(row["page"]))


def test_a_utf8_bom_does_not_rename_the_first_column():
    raw = LABELS.open("rb").read(3)
    rows = list(csv.DictReader(LABELS.open(encoding="utf-8-sig")))
    assert "seq" in rows[0], (
        f"first column is {list(rows[0])[0]!r}; the file starts with {raw!r} "
        "and is not being read as utf-8-sig somewhere")
