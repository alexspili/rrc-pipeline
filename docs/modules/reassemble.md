# Module: page reassembly

Groups the pages of one completion report together, so extraction is given a
document rather than a page.

**Built 2026-09-03**, pure domain in `pipeline/reassemble.py` with 21
tier-1 tests. The identity reader that fills its input is not built and its
corpus run is gated. This file is the design record and the evidence for it, written
2026-09-01 after three defect entries converged on the same conclusion. It
replaces the recommendation in classify.md, which was written before the
evidence and got one word wrong.

## Why it has to exist

A completion report is not one page and its pages are not adjacent.

- **137 of the 375 predicted completion pages are not faces**: 52
  continuations, 34 Section II, 31 Section III, 20 printed backs. None of them
  carries a form number, because the number is printed on the face.
- A further **157 pages across 83 records** are `other_form`: plainly a form,
  no readable number.
- The face and its section are often not adjacent. Record 1501720 has a G-1
  face on page 2 and its related pages several pages later with a P-4 in
  between.

A single-page classifier cannot fix this by getting better. The information
needed to name page 8 is not printed on page 8.

## Why proximity alone does not work

classify.md recommended pairing "by proximity and by agreement on the identity
fields". The smoke set implemented the proximity half, in one direction, as an
explicit placeholder, and **three of the fifteen ground-truth documents came
out as sections separated from their faces** (DEFECTS #25).

The corpus says why:

- Only **79 of 238** predicted completion faces are followed by a completion
  page at all. **46 are followed by another face.**
- Roughly two in five predicted faces are not faces. Stage 2 measured `w2`
  face precision at 44%, and 57.4% after the corrections. So "start from a
  face and look forward" starts from the wrong page a large fraction of the
  time and has no way to notice.
- A section can precede its face in the scan order. Record 1495193 page 8 is a
  section of the W-2 whose face is page 7, and the census called page 8 a
  `g1` face.

Alex's own ground truth is the fourth piece of evidence: **47 of 405 rows are
`page_not_in_document`**, a labeller recording, field by field, that the page
carrying a value was not in the document handed to them.

## The rule

**Pair in both directions, and settle candidates by agreement on the identity
fields both pages carry, never by position. A page that matches no face stays
unmatched.**

Position narrows the candidate list. Agreement decides. The two are not
interchangeable and the order matters.

- The candidate set for a face is the pages of the **same file**, not the same
  record: a record can hold five files and page 3 of one has nothing to do with
  page 3 of another.
- Candidates are non-face completion pages and `other_form` pages, before or
  after the face.
- Candidates are scored on the identity fields both pages carry: operator,
  lease name, well number, completion date, and total depth where the section
  repeats it.
- A minimum agreement is required. Below it the page stays unattached, which
  is the abstention principle this pipeline already applies twice: a page
  forced onto the nearest face is the extraction-layer version of guessing
  between G-1 and W-2 on an unreadable form number.
- One page attaches to at most one face.

## Worked cases, all real

| Record | What it demonstrates |
|---|---|
| **1493495** pages 9, 10 | The positive case. A W-2 face and its Section II agreeing on operator (Sun Oil Company), lease (State Tract 130) and completion date (9-22-77), with total depth 9200 on the section matching the face's own inclination note |
| **1495193** pages 7, 8 | A section **preceding** its face in scan order, and the census calling that section a `g1` face. Pages 7 and 8 must group; pages 7 and 9 must not |
| **1760703** | Three separate G-1s in one file. Completions are a time series per well, so "the nearest face" is ambiguous by construction |
| **1511465** pages 7, 8, 9, 10 | Three W-2 faces with a section sitting between two of them. Position cannot decide which face the section belongs to; the identity fields can |
| **1495195** | Supplied three of the fifteen ground-truth documents, two of them suspect. One file can contain many completions |

## It shares machinery with the disagreement detector

Cut order step 5 is a cross-form identity extractor: pull operator, lease, well
and county off non-completion forms and diff them against the completion
report. That is the same read this module needs to score a candidate.

So identity-only extraction over section and `other_form` pages is one piece of
work serving two steps, and it should be built once. It is also the cheaper
half of extraction: a handful of fields rather than the full v1 schema.

## Tier-1 test plan, before any code

All pure, over page records carrying (page, form_class, part, identity fields).

1. Two pages agreeing on operator, lease and completion date group; the same
   face and a page agreeing on none of them do not.
2. Record 1495193's shape: a section before its face groups with it, and the
   next face does not take it.
3. Record 1511465's shape: with three faces and one section, the section goes
   to the face it agrees with, not the nearest one.
4. A page below the agreement threshold stays unmatched, and unmatched pages
   are reported rather than dropped.
5. One page never attaches to two faces.
6. Candidates never cross a file boundary within a record.
7. A face with no candidates is a one-page document, which is the common case:
   most of this archive was imaged front only.

## What this module must not do

It must not improve the numbers by attaching more pages. A wrong attachment
puts one well's casing record under another well's identity, and every
downstream check would then be validating a document that never existed. The
count of unattached pages is a reported metric, not a defect to be minimised.

## Pin

DEFECTS #25 carries the pending pin: record 1495193, pages 7 and 8 resolve to
one document and pages 7 and 9 do not. That case is the first test to write.

## Cost, MEASURED 2026-09-03

`scripts/probe_identity.py`, three pages on `claude-sonnet-5` at $2/$10 per
1M tokens. Approved as a probe; the full run is gated.

| | |
|---|---|
| input | 2,846 tokens per page |
| output | **166 tokens per page** |
| cost | $0.0074 per page standard, $0.0037 batched |
| 274 candidate pages | **$2.01 standard, $1.01 batched** |

The output figure is the point. The full extractor averages 5,114 output
tokens on a document and 85% of its cost is output, so a six-field read is
roughly thirty times smaller on the half of the bill that matters. That is
the whole argument for a separate reader rather than the v1 schema with
fields switched off, and it is now measured rather than argued.

The run stays gated and lands with the full extraction run as one spend
decision, after reassembly passes the ground-truth measurement.

**One observation from the three probe pages, recorded because it is the
first evidence about the exact-matching hypothesis and not because it settles
anything.** Two pages of record 1493399 came back with the operator as
`Crawford Energy, Inc.` and `Crawford Energy. Inc.`, a comma against a full
stop, which normalisation folds to one string as designed. Their lease names
came back as `TRIOLO # 1` and `C.A. Triola Unit`, which normalisation does
not fold and which the veto would reject as a contradiction.

Whether those two pages are one document is unknown; they may be two wells on
one lease, which is the veto working. That is exactly the ambiguity the
contradicted-but-agreeing list exists to put in front of a human, and at n=1
it is an observation to watch rather than a finding. It does say the list
will not be empty.

## First measurement, 2026-09-03

Identity read over 123 pages of the ground-truth records, $0.91, cached. The
rule, its cases and its thresholds were fixed in
docs/labeling-protocol-reassemble.md before any of this ran, and amended to be
two-sided (DEFECTS #35) still before it ran.

Two numbers are reported for each case because the module changed once during
the sitting, after a failure was diagnosed as a design hole rather than a
threshold problem (DEFECTS #37). The change is a design fix and not threshold
tuning, but it was still made after seeing a result, so both figures travel
together and neither is quoted alone.

| Case | Pairing | Evidence | Before | After |
|---|---|---|---|---|
| A | 1493495 p10 → p9 | confirmed | PASS | **PASS** |
| B | 1495193 p8 → p7 | confirmed | FAIL | **FAIL** |
| C | 1495195 p6 → face before it | probable | not attached | not attached |
| D | 1495195 p38 → face before it | probable | not attached | **attached to p37** |
| E | p8 must not attach to p9 | — | PASS | PASS |
| F | no wrong attachment | — | none checkable | see below |

**The threshold did not move and is still 2.** The rule says a confirmed
must-attach failure does not move it, and nothing found argues otherwise: case
B does not fail on how much agreement is required.

| | before | after |
|---|---|---|
| documents | 63 | 54 |
| pages attached | 5 | **17** |
| unattached | 52 | 50 |
| contradicted / below threshold / tie / no face | 29 / 20 / 2 / 1 | 28 / 20 / 1 / 1 |

All five attachments made before the change survive it unchanged. That was
the stated verification and it is the reason the two columns can be compared.

**Case D is reported as attached, not as a pass.** It attached to page 37, the
face immediately before it, which is what the protocol expected. But D was
recorded as "probable" rather than read off the paper, so a match here
confirms the module agrees with an assumption, not that either is right.

**Case B fails for a second reason, and it is open.** Pages 7 and 8 agree on
operator (`U. S. Resources, Inc.`) and lease (`Debbie`) and disagree on
completion date, `10-2-79` against `8/30/79`. Page 8 is a G-1 potential test
and page 7 a W-2. Whether one document legitimately carries two dates across
those two forms is a question about the paper and is not answerable from here.
Held pending a reading.

### What the module cannot reach at all

**20 of the 57 candidate pages carry no identity fields whatever.** They can
never attach on any threshold, with any comparison rule, because there is
nothing on them to compare. That is the ceiling this design has, and it is a
fact about the paper rather than about the code.

### F, stated carefully

Of the 17 attachments, 2 can be checked against ground truth and both are
right. The other 15 are on records with no ground truth. So the honest claim
is **no known wrong attachment**, not none.

Two are worth naming as the highest risk, because they are the least like a
face and its section: record 1495195 pages 52 and 87, and pages 89 and 114.
Each pair agrees on all five identity fields and sits 35 and 25 pages apart in
one file. Agreeing on everything is as consistent with two copies of one
filing as with one document, and only the paper separates those.

### The contradicted-but-agreeing list

54 pairs after the change, up from 17, because faces are now compared against
faces. Full list: `data/extract/reassemble_report.txt`.

What the veto rejected on:

| field | pairs |
|---|---|
| completion date | 42 |
| operator name | 13 |
| lease name | 6 |
| well number | 5 |

**Most of it is the veto working.** Record 1511465 is one lease filed on from
1985 to 2007 under Howell Petroleum, Anadarko and HEA Exploration, and those
really are different documents.

**The lease-name disagreements are the ones that test the exact-matching
hypothesis**, which is that a face and its section were typed by one person in
one sitting so variance within a document should be rare. Five distinct pairs:

```
'A.D. Middleton Alc'              vs 'Anahuac SWD Syst. #3'              different leases
'A.D. Middleton Alc'              vs 'Anahuac SWD System #3'             different leases
'Anahuac SWD System #3'           vs 'Anahuac SWD Syst. #3'              abbreviated mid-name
'Charles Fitch et al M/R (03864)' vs 'Charles Fitch et al M/D (03864)'   one character
'Fleck Lease'                     vs 'Fleck'                             trailing form word
```

Two are genuinely different leases and the veto is right. Three are one name
written two ways. Across the wider set of 46 lease disagreements the variance
takes at least four forms: mid-name abbreviation, appended well number
(`Fleck` against `FLECK #1`), truncation (`Charles Fitch et al M/R (03864)`
against `Charles Fitch`), and single characters.

**Ruled 2026-09-03: change nothing, gather from the full corpus first.**
Suffix stripping would have resolved 3 of the 46, all the same pair, while
looking like it had addressed the problem. Recorded so the corpus run has
something to compare against.

## Rules

All pins are pending: this module is designed and not built, and the pending
marker is replaced with a test path in the commit that builds it.

R0. Comparison is exact after normalising, never fuzzy.
    Origin: approved 2026-09-03 on the physical argument that variance
    within one document is rare, because a face and its section were typed
    by the same person in one sitting. That is a hypothesis, and the
    contradicted-but-agreeing list is the measurement that tests it. Fuzzy
    matching stays out permanently: cross-document name drift is the
    disagreement detector's job, and a similarity judgement that pairs two
    different wells is the one failure this module must never make.
    Pinned by: tests/tier1/test_reassemble.py::test_comparison_is_exact_after_normalising_and_never_fuzzy

R1. Pairing looks in both directions.
    Origin: DEFECTS #25. The placeholder looked only forward, and three of
    the fifteen ground-truth documents turned out to be sections whose face
    precedes them. A forward-only heuristic has no way to notice.
    Pinned by: tests/tier1/test_reassemble.py::test_a_section_before_its_face_groups_with_it_and_not_with_the_next

R2. Position narrows the candidate list. Agreement decides.
    Origin: DEFECTS #25, and the stage-2 measurement behind it: roughly two
    in five predicted faces are not faces, so "start from a face and look
    forward" starts from the wrong page a large fraction of the time.
    Pinned by: tests/tier1/test_reassemble.py::test_agreement_decides_and_position_does_not

R3. Candidates never cross a file boundary within a record.
    Origin: DEFECTS #28. Two readers assumed a record has one file; the
    corpus is 202 records over 249 files and one record holds five. Page 3 of
    one file has nothing to do with page 3 of another.
    Pinned by: tests/tier1/test_reassemble.py::test_candidates_never_cross_a_file_boundary

R4. A page below the agreement threshold stays unmatched, and unmatched pages
    are reported rather than dropped.
    Origin: the abstention principle this pipeline already applies at the
    classifier and at the geometry layer. A page forced onto the nearest face
    is the extraction-layer version of guessing between G-1 and W-2 on an
    unreadable form number.
    Pinned by: tests/tier1/test_reassemble.py::test_an_unmatched_page_is_reported_and_never_dropped

R5. One page attaches to at most one face.
    Pinned by: tests/tier1/test_reassemble.py::test_one_page_never_attaches_to_two_faces

R6. The count of unattached pages is reported output, never a number to
    minimise.
    Origin: a wrong attachment puts one well's casing record under another
    well's identity, and every downstream check would then be validating a
    document that never existed.
    Pinned by: tests/tier1/test_reassemble.py::test_an_unmatched_page_is_reported_and_never_dropped

R7. A contradiction rejects a pair, and a tie attaches to nothing.
    Origin: approved 2026-09-03. Two pages naming different operators are
    not one document whatever else agrees, and breaking a tie by nearness
    would put position back in as the decider, which R2 forbids.
    Pinned by: tests/tier1/test_reassemble.py::test_a_contradiction_rejects_a_pair_however_much_else_agrees
    and ::test_a_tie_between_two_faces_attaches_to_neither

R8. Two agreeing fields are required, and total depth may raise a score but
    never reject a pair.
    Origin: one agreement is ordinary coincidence, since every well on a
    lease shares a lease name and well numbers repeat across leases. Total
    depth is a completion field a section repeats, and a face and its
    section can legitimately differ where one carries a correction. The
    threshold of two is pre-registered and measured, not settled.
    Pinned by: tests/tier1/test_reassemble.py::test_one_agreeing_field_is_not_enough
    and ::test_total_depth_can_never_reject_a_pair

## RETIRED

Nothing yet. The module is not built.
