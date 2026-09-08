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

## Second measurement, 2026-09-03: the prompt fix traded one case for the other

The identity reader's prompt was rewritten to define each field by its printed
label (DEFECTS #40), which invalidated the cache, so all 123 pages were read
again for $0.91.

**Three predictions were committed before the run and all three held.** Page 8
of record 1495193 returned `completion_date` as `not_on_this_form`; case B
attached to page 7 for the first time; and date-driven rejections fell, with
the contradicted-but-agreeing list dropping from 54 pairs to 10.

**And the stated verification failed.** "Case A must still pass after the
change" was written into the plan, and case A now fails.

| Case | Evidence | Run 1 | Run 2 (defined prompt) |
|---|---|---|---|
| A | confirmed | PASS | **FAIL** |
| B | confirmed | FAIL | **PASS** |
| C | probable | not attached | not attached |
| D | probable | attached to p37 | not attached |
| E | vacuous, DEFECTS #41 | — | — |

| | run 1 | run 2 |
|---|---|---|
| attachments | 17 | 14 |
| below threshold | 20 | 29 |
| contradicted | 28 | 20 |
| contradicted-but-agreeing pairs | 54 | 10 |

### Why it traded, and it is not a bug

The stricter prompt made the reader far more conservative, which is what it
was for. What it cost is visible in how many identity fields a candidate page
now carries:

| fields carried | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| run 1 | 20 | 1 | 2 | 12 | 17 | 5 |
| run 2 | 21 | 2 | **20** | 9 | 3 | 1 |

Before, a typical section page came back with three or four fields. Now it
comes back with exactly two. The number that could in principle reach a
threshold of two barely moved, 36 of 57 against 33 of 56, but **the margin
collapsed**: most candidates now sit exactly on the threshold, so any single
field going the other way drops them under it.

Case A is that, concretely. Record 1493495 page 10 returned operator, lease
and completion date under the old prompt and returns **operator alone** under
the new one, because the new prompt tells it that `lease_name` is the box
printed "LEASE NAME" and a W-2 Section II may not print one.

### The question that is now open, and it is about the paper

**Is the lease name printed on record 1493495 page 10 or not?**

If it is not, the new reading is correct, case A's pages genuinely carry one
shared identity field, and **a threshold of two is unreachable for that pair
by any comparison rule**. That is the second explanation the pre-registered
rule named, arriving on a different case from the one it was written for, and
it would be a finding about what a section page carries rather than about the
code.

If it is printed, the reader has become too strict and the prompt needs a
sentence, not the design.

Held until the paper is read. Redesigning on an unverified reading is what
produced DEFECTS #40 in the first place.

### One page truncated

`1510666-1-2` exceeded the reader's 2,000-token cap and was **reported and
never cached**, which is the rule from the extraction milestone working: a
truncated response is its own error, because a cache key that does not cover
`max_tokens` would otherwise serve the truncation back forever.

## Third measurement, 2026-09-03: both confirmed cases pass

Two prompt changes, both invalidating the cache, both costing $0.91: the
Section II lease name in field 32 (DEFECTS #40) and `found_in` on every
present value (DEFECTS #42).

**All four predictions were committed before the run and all four held**,
including the one flagged in advance as most likely to miss.

| Predicted | Result |
|---|---|
| Page 10 returns `lease_name` as `State Tract 130` | held, and `found_in` says field 32 |
| Case A attaches to page 9 again | **held** |
| Case B still passes | **held** |
| Attachments rise from 14 | **held, 18** |

| Case | Evidence | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| A | confirmed | pass (wrong reason) | fail | **PASS** |
| B | confirmed | fail | pass | **PASS** |
| C | probable | not attached | not attached | attached to p5 |
| D | probable | attached to p37 | not attached | not attached |
| E | vacuous, #41 | — | — | — |

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| attachments | 17 | 14 | **18** |
| below threshold | 20 | 29 | 21 |
| tie | 2 | 3 | **6** |
| contradicted | 28 | 20 | 22 |
| contradicted-but-agreeing pairs | 54 | 10 | 8 |

**This is the first run in which both confirmed cases pass at once**, and the
first in which the values behind them are known to come from the boxes they
claim. Run 1's case A was a wrong-field read returning the right number by
coincidence (DEFECTS #42).

### Case D not attaching is the module working, not failing

Page 38 agrees on operator and lease with **eight different faces**: pages 15,
16, 37, 52, 53, 87, 89 and 114. Every one is Gulf Oil Corporation on the Mary
Fitzhugh et al lease. So it ties eight ways and attaches to nothing.

That is the correct answer. **Operator plus lease clears a threshold of two
without identifying anything**, on a file holding many wells of one lease. The
tie rule exists for exactly this and the rise in ties from 2 to 6 is the
module refusing to guess more often, not performing worse.

It also says something about case D itself. D was recorded as "probable" and
its expectation was that page 38 attaches to *the face before it*. That
expectation is positional, which is the one thing this module is built not to
use. Run 1 satisfied it only because a wrong-field date broke the tie. **The
module is declining to confirm an assumption that was never read off the
paper, which is what it should do.**

The real lesson is about which fields, not how many: two agreements is a floor
on quantity and says nothing about selectivity. Recorded, not acted on.

### `found_in` earned its cost on its first run

It surfaced something nobody had looked for, and it forecloses a whole class
of rule: **the same printed field is numbered differently across revisions.**

| Record | Page | Value | Printed label the reader cites |
|---|---|---|---|
| 1493495 | 10 | `State Tract 130` | **32.** Location of Well, Relative to Nearest Lease Boundaries |
| 1495193 | 8 | `Debbie` | **31.** Location of Well, Relative to Nearest Lease Boundaries |
| 1495195 | 6 | `Mary Fitzhugh` | **32.** Location of Well, Relative to Lease Boundaries |
| 1495195 | 38 | `Mary Fitzhugh et al` | **32.** Location of Well, Relative to Nearest Lease Boundaries |

Same label, two different numbers, and the label text itself varies by a word.

**So no rule anywhere in this pipeline may be keyed to a printed field
number.** Not in reassembly, not in extraction, not in a future validation
rule. A rule that says "field 32 carries the lease name" is silently wrong on
every document of the other revision, and silently wrong is the failure mode
this repo has spent the most time on. Rules key to the printed **label**,
matched as text, which is what the identity prompt already does and what the
extraction labelling protocol already told anyone who read it: "read the
printed label rather than counting boxes".

The corollary is that this finding is not local to reassembly. It is a
constraint on the whole corpus, found by a diagnostic added for a different
purpose on its first run.

Every value behind the two confirmed cases now carries the box it came from:

```
1493495 p9   operator      <- 3. OPERATOR
             lease_name    <- 2. LEASE NAME
1493495 p10  operator      <- 26. Notice of Intention to Drill this Well was filed in Name of
             lease_name    <- 32. Location of Well, Relative to Nearest Lease Boundaries
1495193 p7   completion    <- 14. Completion or Recompletion Date
1495193 p8   lease_name    <- 31. Location of Well, Relative to Nearest Lease Boundaries
```

**It remains a claim and not proof.** The model is reporting on its own
reading, exactly as the provenance boxes did, and it is no more
self-verifying than they were. A handful get spot-checked against paper in the
next eyeball sitting. Until then it makes a wrong-field read checkable, and
that is all it does.

## The verification sitting, 2026-09-04: the gate closed

Eight attachments judged against the paper under the rule fixed before the
sample was drawn. **Five are wrong. No corpus spend.**

Three of the five are among the four drawn at random, so the failure is not
confined to the two pairs flagged as risky in advance.

**Every correct attachment is a face with its own back page. Every wrong one
joins two faces, or joins a back page across filings.** DEFECTS #43 has the
table and the diagnosis: identity fields identify the well, and the module was
reading them as identifying the document.

### found_in was right 12 times out of 12, and that is not "reliable"

Every one of the twelve marked spot-checks came back correct: the value really
was in the box the reader named. Wilson 95% on 12 of 12 is **[75.7%, 100%]**,
which is consistent with a true error rate as high as one in four. Twelve
checks cannot license the word reliable and it is not used here.

What it does license is using `found_in` as a signal while continuing to check
it, which is how it was described when it was added: a claim that makes a
wrong-field read visible, not proof.

### The signal it exposes, recorded and NOT implemented

Sorting the eight pairs by what boxes each page cites separates seven of them:

| Verdict | Parent cites | Child cites |
|---|---|---|
| yes | face boxes | back boxes |
| yes | face boxes | back boxes |
| yes | face boxes | back boxes |
| **no** | face boxes | **face boxes** |
| **no** | face boxes | **face boxes** |
| **no** | face boxes | **face boxes** |
| **no** | face boxes | **face boxes** |
| **no** | face boxes | back boxes |

Every join of two real faces is wrong, four times out of four. Every
face-and-back join is right, three times out of four.

A rule that let only a back page be a child would have got **seven of eight**
right instead of three. It would keep both ground-truth passes, keep the pin
that DEFECTS #37 was fixed to satisfy, and undo all four of the
two-filings-in-one-document errors.

**It is not implemented, and the reason is the important part.** That rule was
derived from the same eight pairs that would be used to judge it. Fitting a
rule to a test set and then reporting the test set's score is the failure this
repo pre-registers everything to avoid. If it is adopted it has to be
pre-registered against pairs that are not these eight, which needs another
sitting, and that trade is Alex's to make rather than mine.

### The other thing the sitting produced, which the module cannot see

Alex separated two filings twice by their **Received date stamps**, printed on
the page and different between filings of one well. He also used the shape of
the punch holes once, which is a real signal and not an extractable one.

The date stamp is printed, machine-readable and not among the six fields. So
is `purpose_of_filing`, the field 11 checkboxes that say Initial Potential
against Retest, which is the distinction four of the five failures turn on.
Recorded, not built: adding a field changes the prompt and costs another run.

## The physical signal, 2026-09-05: real, era-independent, and unextracted

**Correction first.** On 2026-09-05 I told Alex the physical signal was
era-dependent, present on 1966-1983 microfilm and absent from the clean 2009
scans. **That was wrong, and wrong for a lazy reason:** I tested for a dark
border at the page edge, which detects microfilm framing and is blind to small
marks inside the page. Alex pointed at staple marks on a 2009 filing and they
are plainly there.

**What the paper carries.** Record 1774674, a 2009 G-1 with no punch holes, no
border and no visible damage. Page 2 has a cluster in the top-left margin: a
curl, a solid blob, a small `v` immediately right of it, a tick below-right.
Page 6 carries the same cluster in the **bottom**-left, in the same relative
geometry. One sheet seen from both sides.

**First quantitative attempt, and it does not separate.** Small isolated blobs
in the page margins, matched as a point set under a small shift:

| | matched |
|---|---|
| 1774674 p2 vs p6 **flipped** | 5 of 22 (23%) |
| 1774674 p2 vs p6 **not flipped** | **0** |
| 2345595 p3 vs p8 flipped | 5 (22%) |
| 1493639 p4 vs p5 flipped | 1 (4%) |
| three unrelated-page controls | 2, 2, 3 (9-13%) |

Restricting to the margins cut detections from 217 to 22 and took the true
pair from 12% to 23%. **The zero when unflipped is the striking number**: it
is the signature of one physical sheet, since marks that pass through paper
only align when the sheet is turned over. But two of three true pairs at
22-23% against controls at 9-13%, with the third below every control, is not
something to threshold on.

**The pattern across two attempts, which is the useful finding.** Punch rims:
visibly the same hole, +0.911 on a clean pair, defeated by ink touching it.
Staple marks: visibly the same cluster, zero when unflipped, drowned by
detection noise. **Both times the signal was real and the extraction failed.**
That is an image-processing problem, not a question about the paper, and it
wants margin isolation, mark classification and cluster matching rather than
global point counting.

**Why it matters more than precision does now.** Every field the module
compares is a fact about a class: operator and lease describe the well, the
printed field numbers describe the form revision. In record 1495195 one back
page ties between **six** candidate faces, all citing identical field numbers
and identical identity values, because they are six filings on one well. No
class-level fact can break that. The sheet is the only instance-level
evidence, and it is what Alex used to verify all three sittings.

**Parked deliberately, with the reason.** Its value is recall, recall cannot
be measured on 39 records, and the corpus run is what creates the data a
recall measurement would need. It is reopened after that, not abandoned, and
the evidence above is its starting point.

## Road not taken: matching the punch holes, 2026-09-04

Alex pairs a sheet's front and back by eye from the shape of the punch hole,
and did so during the verification sitting: "Definitely face and back of the
same form, I can tell by the shape of the punch holes." The idea was probed
and **parked, not adopted**. The evidence is recorded because the parking is a
judgement about cost, not about whether the signal exists.

**The signal exists and was measured.** On record 1493608, the confirmed
same-sheet pair, the second hole's rim outline correlates at **+0.911** between
front and back under the flip a sheet physically performs. The same torn flap
is visible at the lower right of both holes. Controls sit at zero: two holes
punched by the same machine score -0.08, holes from unrelated records -0.04.

**Two representations were tried and only one works.** Overlapping the filled
hole gives nothing, because any two circles overlap well: unrelated records
score 0.85. The rim has to be turned into a radial outline, the distance from
the centre to the edge at each angle, which is where the tear becomes signal.

**What stopped it: ink touching the hole.** The holes sit in the page margin,
which is also where letterheads, received stamps and table rules live. A
connected-component step swallows the hole and the touching type into one
blob, and the measured rim is then partly typography.

| Confirmed pair | Result |
|---|---|
| 1493608 p5+p6, both holes clean | **+0.911** |
| 1493495 p9+p10, one hole fused to a `RECEIVED` stamp | not measurable |
| 1495193 p7+p8, one hole fused to a letterhead | +0.023 |

Three rounds of fixes each repaired one failure and created another, at which
point the work was tuning against the only three labelled pairs there are,
which is the trap this module already pre-registers everything to avoid.

**What a real version needs**, since none of it is speculative: separating a
disc from ink that touches it, by morphological opening or by fitting a circle
and reading the rim only along the uncontaminated arc. The rim comparison
itself is sound. The isolation step is what fails.

**Why it was parked rather than finished.** Punch matching can only ever pair
the front and back of one physical sheet. **Four of the five wrong attachments
in the verification sitting were two separate sheets**, so a perfect hole
matcher would not have caught them. It attacks a different problem from the one
that is broken.

Also measured and worth keeping: the punch pitch is a corpus-wide constant,
2¾ inches across 19 unrelated pages, so hole *position* discriminates almost
nothing. Unrelated pages agree on both offsets 16.9% of the time. Only the rim
shape carries information.

`numpy` and `scipy` were added for this and then removed with it, rather than
left in `requirements.txt` for code that no longer exists.

## The third sitting, 2026-09-05: the gate passes

**Six of six verify on held-out data.** Both pre-registered regression
conditions hold: all five pairs judged correct in the earlier sittings still
attach, and cases A and B still pass.

| Pair | Verdict |
|---|---|
| 1493639 p5+p4 | yes |
| 1494028 p7+p6 | yes |
| 1494408 p5+p4 | yes |
| 1512952 p2+p1 | yes |
| 1774674 p6+p2 | yes |
| 2345595 p8+p3 | yes |

Every one is on a record drawn at random before it was read, and no page of any
of them had ever been judged. So unlike the 13 of 15 across the first two
sittings, this is not a rule scoring well on the data it came from.

**What the sequence measured, and it is the part worth keeping.** The second
sitting scored **7 of 8 on the pairs the fixes were built from and 2 of 7 on
fresh pairs**. Without a held-out sample, 7 of 8 would have been reported as
the result and the corpus run would have followed it. The held-out sitting is
the only reason the two remaining holes were ever found.

| Sitting | Data | Result |
|---|---|---|
| 1 | first measurement | 3 of 8 |
| 2 | fresh, after three fixes | 2 of 7 |
| 2 (same fixes, development) | the pairs they were built from | 7 of 8 |
| 3 | fresh, after two more fixes | **6 of 6** |

### How Alex verified, three sittings running

Not by the identity fields. By the physical sheet: "I can tell by the shape of
the punch holes", then "punch holes match perfectly", then "the creases,
staple markings, folds and missing parts on the paper gave me certainty".

**The module has none of that evidence and passes anyway**, which is worth
stating plainly rather than claiming more than it earns. It agrees with a human
who is reading a different signal. That agreement is what six of six means, and
it is also the reason the punch-hole road is recorded rather than deleted: the
signal a person actually uses is measurable, was measured at +0.911 on a clean
pair, and is defeated by ink touching the hole rather than by the paper.

### What it does not settle

- **The known limitation stands.** A W-2 section can still attach to a G-1
  face, because the rule that would stop it is keyed to a classifier label
  that is wrong on this module's own pin. None of the six had that shape.
- **13 attachments over 39 records.** The module is conservative by
  construction and its recall has never been measured, only its precision.
  How many documents it fails to assemble is unknown.
- **20 of 57 candidate pages carry no identity fields at all** and can never
  attach on any rule.

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

R11. A face holds one back. Identity agreement fills at most one child
    slot; two identity children on one face is a slot tie and attaches
    nothing, with an evicted face standing back up as its own filing. A
    paper confirmation names the sheet's actual back and carries its own
    slot; once it has, an identity child that is itself back-like, a
    section or a face demoted by its own box evidence, is a different
    filing's back and stands down, while a continuation, being a further
    sheet, is not displaced. Two confirmations on one face is the
    machinery contradicting itself and both stand down.
    Origin: every document over two pages in the corpus grouping was a
    two-page filing plus one page of another filing for the same well,
    joined by well-level agreement (1493399-0-41, 1494036-0-12,
    1912687-0-2, the last being the hole left open on 2026-09-04 because
    the family rule that would close it breaks the 1495193 pin; this
    rule closes it structurally and the pin, one face one child, never
    sees it). Cost stated: a genuine face plus section plus continuation
    with no paper confirmation is a slot tie and keeps only its face; no
    such document exists in the corpus grouping today.
    Pinned by: tests/tier1/test_reassemble.py::test_two_identity_backs_for_one_face_are_a_slot_tie
    and ::test_a_confirmed_back_displaces_an_identity_back
    and ::test_one_back_never_sees_the_slot_rule

## RETIRED

Nothing yet. The module is not built.

## The paper outline does not identify the sheet. Probed 2026-09-05, $0

**Why this was tried.** Identity fields can only exclude. They describe the
well, and the failures are several filings for one well, so agreement between
them is guaranteed rather than informative. Alex matched pages by eye using the
paper itself and said it is the only direction that can confirm. This probe
asked whether the outline of a sheet — every tear, fold and trimmed edge, read
as the distance from the image border to the paper along each of the four
sides — can say that two pages are one piece of paper.

**Scope, measured first.** On the 71 pages involved in a multi-page document,
**56% have a black scanner border on all four sides, 42% have none at all.**
Where the scan is cropped tight to the paper there is no visible paper edge and
the outline is a straight rectangle by construction. 23 of the 39 judged pairs
have a usable border on both pages, so the channel could speak to 59% of pairs
at best.

**The result on the 18 pairs it could read**, 7 verified true and 11 verified
false, after removing the linear trend so that scanner skew cancels:

| | Predicted flip | Control flip |
|---|---|---|
| True pairs | 0.675 to 0.918 | 0.666 to 0.907 |
| False pairs | 0.019 to 0.715 | 0.013 to 0.657 |

Ranked on the predicted flip alone this looks like a working signal: six of
seven true pairs score above every false pair.

**The control says that ranking is not evidence, and this is the whole point of
having run one.** A sheet flipped front-to-back about the horizontal axis maps
(x, y) to (x, H − y). The control is the flip about the vertical axis, which a
sheet cannot perform between these two scans. **Predicted minus control is
−0.002 on true pairs and −0.010 on false ones.** The score is the same under a
transform the paper can do and one it cannot, so it is not measuring the sheet.
It is measuring something orientation-blind that pages scanned together share:
feeder alignment, paper stock, batch geometry.

High-pass filtering the profile, to keep only detail finer than 1.4 in and then
finer than 0.35 in, does not change it: predicted minus control stays at −0.004
on true pairs. And the highest-scoring pair in the whole table is a **false**
one, 1493451 p19+p10 at 0.733, above four of the seven true pairs.

**Without the control I would have reported six of seven as a success.** That
is the same shape as DEFECTS #29, where well-formed geometry was mistaken for
grounded geometry, and the reason a physically impossible transform is scored
alongside every real one.

**What this does not kill.** The outline was my generalisation of what Alex
described, and it was the wrong one. Both matches he made himself used features
**inside** the paper: punch-hole rim shape on 1493608, staple marks on 1774674.
The punch-rim probe of 2026-09-04 showed exactly the signature this one lacks —
+0.911 under the predicted flip with every control collapsing to about zero —
and failed on detection robustness rather than on signal, finding one hole 110
px wide on one page and 82 on the other. Interior features remain the live
candidate; the outline is closed.

**What any further work needs first.** All 39 corpus attachments have now been
judged, so there is no held-out pair left. A mechanism developed against these
verdicts cannot be validated against them, and new labelled pairs would have to
be produced before any number from it means anything.

## Punch-hole rim shape carries the signal. Marks and positions do not.
## 2026-09-05, $0

**A physics error first, because it changes what a control is.** The outline
probe treated the flip about the vertical axis as impossible. It is not: a
sheet can be turned over about either edge, and which one the scanner operator
used is unknown. Both flips are legitimate. The transforms a turned-over sheet
**cannot** produce are the orientation-preserving ones — identity and 180
degrees — because turning paper over always reverses orientation. Two real
options and two controls, so best-of on the real side gets no freedom the
control lacks.

**What was rebuilt, and it should not have been.** A matcher over the positions
and sizes of solid marks, run over all 26 pairs of the fourth sitting. It
separates nothing: the controls match it pair for pair. That is not a surprise
in hindsight. The design pass of 2026-09-04 had already measured hole
**position** as weak — the punch pitch is a corpus-wide constant, 2¾ in across
19 unrelated pages, and unrelated pages collide 16.9% of the time — and had
written down that position finds the holes while **the rim shape decides**.
Alex said the same thing in his own words. I built the weak half anyway,
because a single pair matched convincingly on position and area and I read that
as the mechanism working.

**The detection problem does now look solved.** A morphological opening that
severs hairline connections before labelling is what the earlier attempt
lacked. On 1495414 it lifts both punch holes out of the printed rules they sit
on and returns them as clean discs, 4,449 and 5,034 px, density 0.75 and 0.77.
That is the failure that stopped the 2026-09-04 rim work, where one hole came
back 110 px wide on one page and 82 on the other.

**Rim shape, on the sheet Alex pointed at, with no rotation search and only the
mirror the paper performs:**

| Comparison | Correlation |
|---|---|
| The same hole, both sides of one sheet, mirrored | **+0.618** |
| The same hole, not mirrored (paper cannot do this) | +0.295 |
| A different hole on the same page, same punch machine, mirrored | −0.043 |
| A different hole, not mirrored | +0.055 |
| The two holes of one page against each other | +0.045 |
| A hole from an unrelated record, mirrored | −0.228 |

Every control collapses to about zero. This is the second record to show that
shape: 1493608 gave +0.911 against controls of −0.08 to +0.002 on 2026-09-04.

**Searching rotations destroys it.** Allowing the best correlation over all
angular offsets lifts the true pair to +0.633 and the controls to +0.42 and
+0.49, which is no separation at all. The earlier probe recorded the same
effect. The transform is predicted, never searched.

**Reach.** 18 of the 26 pairs have a round solid hole on both pages, so this
channel could speak to 69% of them. It needs no scanner border, which is what
limited the outline to 59% and excluded the very pairs Alex matched by eye.

**What this is not.** Two pairs is not a measurement, and today's work iterated
several times against the same 26 verdicts that would have to grade it. A rim
matcher built now and scored on these pairs would be fitted to them. All 39
corpus attachments are judged, so a real number needs pairs that do not exist
yet.

## The cross-form attachments are mislabelled pages, not wrong pairings
## Measured 2026-09-06

DEFECTS #44 left one hole open deliberately: a page the classifier calls a
different form family may still attach. The rule that would close it — two
pages are one document only when they are the same form family — was refused
because it breaks this module's founding pin, record 1495193 pages 7 and 8,
which the classifier calls `w2` and `g1` and which **are** one document.

All 39 corpus attachments have now been judged, so the hole can be sized.

| | |
|---|---|
| Attachments where child and face share a form family | 23 |
| Attachments **crossing** form families | **16** |
| of those 16, judged correct | **7** |
| of those 16, judged wrong | 9 |

**So a form-family rule would delete 7 correct attachments to remove 9 wrong
ones.** That is the measurement the refusal was waiting for, and it confirms
the refusal.

**The label is what is wrong, not the pairing.** Four of the seven correct
cross-family attachments are pairs confirmed from the paper itself — 1495414
p6+p7 and 1774674 p2+p6 among them — so the two pages are physically one sheet
and cannot be two different forms. The classifier is wrong about one of them
in every such case.

That is consistent with what classification already measured: G-1 face
precision 94.0%, W-2 face precision 57.4% with an interval that still contains
its own before-figure, so W-2 face precision was never established at all. And
a back page frequently prints no form number anywhere, leaving the classifier
nothing to read.

`part` is no better a guide here: of the ten cross-family children the
classifier calls a `face`, four are correct attachments and six are wrong.

**What follows.** The hole stays open, now for a measured reason rather than a
worked example. Closing it needs a form label that is right about back pages,
which is a classification problem and not a reassembly one.
