# Module: page reassembly

Groups the pages of one completion report together, so extraction is given a
document rather than a page.

**Not built.** This file is the design record and the evidence for it, written
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

## Rules

All pins are pending: this module is designed and not built, and the pending
marker is replaced with a test path in the commit that builds it.

R1. Pairing looks in both directions.
    Origin: DEFECTS #25. The placeholder looked only forward, and three of
    the fifteen ground-truth documents turned out to be sections whose face
    precedes them. A forward-only heuristic has no way to notice.
    Pinned by: pending, on record 1495193 pages 7 and 8.

R2. Position narrows the candidate list. Agreement decides.
    Origin: DEFECTS #25, and the stage-2 measurement behind it: roughly two
    in five predicted faces are not faces, so "start from a face and look
    forward" starts from the wrong page a large fraction of the time.
    Pinned by: pending, on record 1511465, three faces and one section.

R3. Candidates never cross a file boundary within a record.
    Origin: DEFECTS #28. Two readers assumed a record has one file; the
    corpus is 202 records over 249 files and one record holds five. Page 3 of
    one file has nothing to do with page 3 of another.
    Pinned by: pending.

R4. A page below the agreement threshold stays unmatched, and unmatched pages
    are reported rather than dropped.
    Origin: the abstention principle this pipeline already applies at the
    classifier and at the geometry layer. A page forced onto the nearest face
    is the extraction-layer version of guessing between G-1 and W-2 on an
    unreadable form number.
    Pinned by: pending.

R5. One page attaches to at most one face.
    Pinned by: pending.

R6. The count of unattached pages is reported output, never a number to
    minimise.
    Origin: a wrong attachment puts one well's casing record under another
    well's identity, and every downstream check would then be validating a
    document that never existed.
    Pinned by: pending.

## RETIRED

Nothing yet. The module is not built.
