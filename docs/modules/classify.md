# Module: page classification

Assigns every page in the corpus a `form_class` and, for form pages, a `part`.
Its first corpus-wide run is also the census: the fraction of records holding a
completion report is unknown and decides whether this corpus is usable.

Interface: `pipeline/pageclass.py` (pure domain), `pipeline/render.py` (page
images and OCR text), `pipeline/classify.py` (model calls).

## Decision rule for the arm competition

**Recorded 2026-08-30, before any arm has been run.**

Three arms compete: vision at a 1000px long edge, vision at 1568px, and the
embedded OCR text layer. They run over the union of the stage-1 labelled set
and the smoke slice, and are scored on the 60 labelled pages.

The cheapest arm wins unless a costlier arm beats it by more than 5 percentage
points on the labelled set. Anything inside 5pp is reported as a tie and cost
decides.

The threshold is not tuned to a result. At n=60 the standard error on a single
accuracy estimate is about 6pp, and the difference between two arms scored on
the same 60 pages is not resolvable below roughly 5pp. Writing this down before
the numbers exist is what stops the winner from being chosen after seeing them.

The full census then runs exactly once, on the winner.

## Rules

R1. A page whose aspect ratio exceeds 2.0 is never extraction-eligible.
    Origin: DEFECTS #1. A long-edge downscale crushes the short edge of a
    fold-out; the widest page in the corpus (11,264 x 3,040, record 1495350)
    lands at a 423px short edge under the 1568 cap. Classification still runs
    on a squashed thumbnail, which is adequate for "this is a plat".
    Pinned by: tests/tier1/test_pageclass.py::test_oversize_page_is_never_extraction_eligible

R2. `part` is required for form classes and forbidden for census-only classes.
    A plat has no Section III. Without this the census could report sections of
    documents that do not have any.
    Pinned by: tests/tier1/test_pageclass.py::test_part_is_forbidden_for_census_only_classes

R3. A page whose part is `back_instructions` is never extraction-eligible.
    A pre-printed form reverse carries the same header and form number as the
    face and holds no values. Unlabelled it classifies as a face, reaches
    Sonnet, and produces confident garbage. This is the most likely silent
    failure in this stage.
    Pinned by: tests/tier1/test_pageclass.py::test_printed_form_back_is_never_extraction_eligible

R11. The class list is checked against the corpus, not against recon.
    Origin: DEFECTS #10. The taxonomy was written from the eight documents read
    during recon and missed W-1, P-5, L-1, GT-1 and W-12, five families on
    roughly 400 pages across more than half the records. A tier-2 test scans
    every page's OCR header region and fails if a form appearing on more than
    20 pages has no `PageClass`. Recon documents are selected for being
    interesting, which is the opposite of representative.
    Pinned by: tests/tier2/test_taxonomy_coverage.py::test_every_common_form_has_a_class

R12. `back_instructions` is for prose, `continuation` is for data.
    Origin: DEFECTS #10. A reverse carrying a filled-in table (`RECORD OF
    INCLINATION (Continued from reverse side)`) is a continuation and stays
    extraction-eligible. Only pre-printed filing instructions are
    `back_instructions`. Conflating them discards real data under R3.
    Real backs self-identify; the pointer phrases ("READ INSTRUCTIONS ON
    BACK", "- OVER -") are printed on the face, and only 107 of 486 pages
    carrying such a pointer are followed by an imaged reverse.
    Pinned by: the labelled set's part distribution, 8 back_instructions
    of 60, and the census, 20 completion-report backs of 375.

R4. Never coerce an out-of-vocabulary class into `other_nonform`.
    An unknown value is a prompt or model problem and must surface as one.
    Silently bucketing it hides taxonomy gaps in exactly the class that exists
    to reveal them.
    Pinned by: tests/tier1/test_pageclass.py::test_parse_response_refuses_to_guess

R5. Downscale from grayscale, never from mode "1".
    Origin: the source is 1-bit CCITT. A nearest-neighbour resample does not
    average, so at 0.48x a hairline survives whole or vanishes and the page
    still looks like a page.
    Pinned by: tests/tier1/test_downscale.py::test_downscale_averages_rather_than_samples

R6. Confidence is a measured bucket, not a probability.
    The model self-reports high/medium/low. That value means nothing until the
    accuracy-per-bucket table on the labelled set gives it one. Never report a
    self-reported confidence as a probability, and never threshold on it before
    the table exists.
    Pinned by: the accuracy-per-confidence table in the arm run and the
    census confidence distribution (3,321 high / 287 medium / 66 low).

R7. Document counts, record counts and entity counts are different numbers.
    Origin: DEFECTS #2. `Census` has no permits field because nothing in a page
    label distinguishes an amended filing from its original.
    Pinned by: tests/tier1/test_census.py::test_amended_filings_are_documents_not_entities

R8. A parameter value not observed from a working client gets a bounded probe
    before it reaches a corpus run, and the probe must be able to tell a
    rejected request from a rejected feature.
    Origin: DEFECTS #3, applied to our own vendor rather than Neubus, then
    DEFECTS #9 when the probe's own error handling collapsed both failure
    modes into one verdict.
    Pinned by: scripts/probe_haiku.py, which tries every valid spelling.

R9. Structured outputs stay off for the arm competition.
    They are verified working (see Probe results). Constrained decoding cannot
    emit an out-of-vocabulary class, so it removes exactly the signal R4 exists
    to surface, on the one run where the taxonomy is still being tested. The
    RESOLVED 2026-08-31: census parse failures are 0.4% after the prompt
    correction, below any threshold justifying constrained decoding, so they
    stay off and R4 keeps its signal.
    Pinned by: the census parse-failure rate, 15 of 3,689.

R10. Rank arms by measured cost, never by assumed cost.
    The text arm is cheapest across the corpus and was more expensive than
    vision_1568 on the first page probed. The selection rule below reads
    "cheapest", and cheapest is whatever the run measured.
    Pinned by: tests/tier2/test_arms.py::test_arms_are_ranked_by_measured_cost

R13. A page may not claim a form number it could not read.
    `PageLabel` refuses `g1` or `w2` when `form_number_legible` is false, and
    routes the page to `completion_face_unknown_form`. Origin: the stage-2
    measurement, where 20 of 20 drawn completion faces with an illegible form
    number were misclassified, and 16 of 16 whose number the OCR text layer
    also recovered were correct. This is a rule 6 retirement in advance: the
    guess is not discouraged in the prompt, it is unrepresentable in the type.
    Pinned by: tests/tier1/test_abstention.py, all of it, in particular
    ::test_a_named_completion_report_needs_a_readable_number and
    ::test_a_guess_on_an_unreadable_page_is_refused_at_the_parser

## Probe results

Run 2026-08-30 against record 1501720 page 2, the G-1 face of the demo
document. Two calls, under a cent. See DEFECTS #9 for the first run's wrong
conclusion.

| Probe | Result |
|---|---|
| `output_config.format` on claude-haiku-4-5 | **accepted**, with a nullable enum spelled as an `anyOf` union. Rejected when spelled `{"type": ["string","null"], "enum": [...]}`, which is invalid JSON Schema and says nothing about the model. |
| Control call, plain JSON path | correct: `g1 / face / up / high`, 2,078 in, 54 out, $0.00235 |

Measured request tokens, whole request including the ~500-token system prompt:

| Arm | Sent | Counted | Image alone | w*h/750 estimate | Corpus, standard / batched |
|---|---|---|---|---|---|
| vision_1000 | 775x1000 | 1,546 | ~1,046 | 1,033 | $5.70 / $2.85 |
| vision_1568 | 1215x1568 | 2,078 | ~1,578 | 2,540 | $7.67 / $3.83 |
| text | n/a | 2,115 (this page) | n/a | n/a | $3.88 / $1.94 |

Three things the measurement changed:

1. **The 1568 arm is not a 1568 arm.** 1,578 image tokens is about 1.18
   megapixels, so the server downsized 1215x1568 (1.9 MP) to roughly a 1,220px
   long edge before charging for it. The estimate overshot by 38% because it
   assumed the long-edge cap binds; the area cap binds first. The two vision
   arms are really 1000 against ~1220, a narrower comparison than intended.
   Sending 1568 uploads roughly twice the bytes for identical model input
   (453 KB against 245 KB per page), which matters for a 3,689-page batch and
   not at all for cost. Left as it is for the competition rather than changed
   mid-experiment; if this arm wins, the census sends the area cap instead.
2. **The estimate was good at 1000 and bad at 1568**, for the same reason.
   estimate_image_tokens keeps its UNVERIFIED marker for anything above about
   1.15 MP.
3. **The text arm is cheapest corpus-wide but not on every page.** 8,126,697
   OCR characters across 249 files, mean 2,274 per page. On this page the text
   arm cost more than vision_1568, because a dense G-1 face carries more text
   than a plat. Cost ordering must be measured per run, never assumed.

## Census, 2026-08-31

Run on `vision_1000`, the winning arm. 3,689 pages, ~10 batches, **$4.25**
batched. Reconciled: 3,674 labelled, 15 parse failures (0.4%), none missing,
202 records. Oversize came back as exactly 23, matching the geometry
measurement taken independently before any model ran.

This produced **two findings at two different confidence levels**. They must
not be quoted as if they carried the same weight.

### Finding 1 — completion detection. VERIFIED. Load-bearing.

**115 of 202 records (57%) contain a completion report.**

Above the OCR floor (68) and above HANDOFF's sufficiency threshold (80). A
seeded random sample of 15 of those 115 records was rendered and hand-checked
by Alex: **15 of 15 confirmed**, zero over-counting. Verdicts in
`data/census/verify.csv`.

This is the decision the milestone existed to produce. The corpus is
sufficient; `fetch.py` stays closed; extraction is the next milestone.

The check was per record, not per page, and deliberately so: the claim is "this
record contains a completion report", one unambiguous face settles it, and a
Section II page carries no form number so "is this page a W-2" is not
answerable from it.

### Finding 2 — per-form composition. PROVISIONAL. Not reportable.

| Basis | g1 records | w2 records | both | union |
|---|---|---|---|---|
| all completion pages | 67 | 105 | 57 | 115 |
| **face pages only** | **53** | **80** | **25** | **108** |

The hand-check contradicted the composition on **6 of the 9** sampled records
where the census claimed both a G-1 and a W-2. Two mechanisms:

1. **Sectionless pages are attributed by guess.** 137 of 375 completion-report
   pages (37%) are not faces: 52 continuation, 34 Section II, 31 Section III,
   20 backs. None carries a form number, and G-1 and W-2 share a near-identical
   layout, so the model picks one. Restricting to faces drops records-claimed-
   both from 57 to 25.
2. **Face-level confusion.** Four sampled records have conflicting faces, and
   W-15 faces were read as completion reports on three pages across two
   records.

**Do not report a G-1 versus W-2 split until stage-2 labels make it
measurable.** Those labels now exist; the numbers are below, and the split is
still not reportable as a count. See "Stage 2 results".

### Why it is not fixed yet

The stage-1 labelled set contains **0 G-1 pages and 2 W-2 pages** out of 60.
That is what a uniform sample of a corpus with 112 G-1 pages in 3,689 looks
like, not a labelling failure. But it means there is currently no instrument
capable of telling whether a fix worked.

Changing the prompt now would spend the one iteration the labelled set can
absorb on a blind change. Measure first: stage-2 labels stratified over the 238
predicted completion-report faces, plus W-15 faces, plus every `low`-confidence
page, plus oversize pages a uniform sample never reaches.

**Stage 2's job is to make the distinction measurable, not to fix it.** The
prompt fix is a separate step, gated on stage 2 existing, with its own
before-and-after on those labels.

### Stage 2 as drawn, 2026-08-31

143 pages in nine strata over the census predictions, blinded, both seeds and
all five metrics recorded in `docs/labeling-protocol-stage2.md` before the
draw. 105 scored, plus all 23 oversize pages and all 15 parse failures.

The design variable that made it affordable: the OCR header scan agrees with
the model on all 75 completion faces where it resolves a form number at all,
and contradicts it on none, so those pages take 16 labels between them and the
163 where the printed number did not survive imaging take 47. Worth 4.85
percentage points of standard error on each face precision, computed by
`pipeline/estimate.py` from the allocation before any page was labelled.

The scan is trusted only that far. DEFECTS #15 and #16 are both cases of it
reading a mention as a header, so: of those 75 corroborated faces, 0 carry
"status report", "when to file", "where to file" or "instructions" in their
header region, which is the shape the leak takes.

## Stage 2 results, 2026-08-31

143 pages hand-labelled by Alex, 0 noted unsure. Scored by
`scripts/score_stage2.py` against metrics fixed in the protocol before the
labels existed.

### The headline

| Predicted | Precision | Drawn | Frame |
|---|---|---|---|
| `g1` face | **64.7% +/- 4.5pp** | 17 of 30 | 72 pages |
| `w2` face | **44.0% +/- 5.2pp** | 14 of 40 | 166 pages |

Stratified, with the finite-population correction, weighted by frame size.
Part never disagreed with class on these strata, so class-only and
class-and-part precision are the same number.

Applied to the census: of 72 predicted G-1 faces about 47 are one, and of 166
predicted W-2 faces about 73 are. Those are corrected counts of *true positives
among predictions*, not corrected totals. Recall is bounded, not measured, so
neither number is a count of the G-1 faces in this corpus and must not be
presented as one.

### The finding that explains the rest

**Every page whose printed form number is illegible was misclassified. 20 of
20, no exceptions.** Of the 50 drawn completion faces whose number is legible,
31 are right.

The two signals agree completely. Where OCR reads the form number the model
chose, the model is right: stratum B 8 of 8, stratum E 8 of 8. Where OCR reads
a *different* number, the model is wrong: stratum D, 7 of 7 predicted W-2 faces
are W-15s. Where OCR reads nothing, the model is right 15 of 47 times.

So the classifier is not confusing G-1 with W-2 by misreading a form's layout.
On a page whose number it can read it is essentially never wrong; on a page
whose number it cannot read it is guessing, and the near-identical G-1 and W-2
layouts give it nothing to guess with. This is a legibility problem wearing a
classification problem's clothes, and no prompt change addresses it.

Confidence does not help. All 72 predicted G-1 faces are `high` with no
alternative class offered, and the drawn sample scored 61 of 119 on `high`.

### Mechanism 1 confirmed

Of the predicted completion pages that are not faces, **86.7% +/- 8.6pp carry
no form number at all** (13 of 15 drawn from a 137-page frame): 8 continuations
and 5 printed backs, none of which names a form. The census gave every one of
them a form number and a part. The attribution is invented, at the rate the
census section above suspected.

### Recall

0 completion faces among 20 pages drawn from the 361-page confusable frame. A
bound, as pre-registered, not an estimate. Nothing in the labels suggests
completion faces are hiding in `w15`, `g5`, `l1`, `ws1_sw1` or `other_form`.

### R1 measured for the first time

23 of 23 oversize pages labelled: 17 plats, 5 letters, 1 separator card, class
correct on 17. Stage 1 contained no oversize page at all, so this is the first
evidence that classifying a squashed thumbnail is adequate for "this is a
plat". It is adequate. R1 keeps its wording.

### The parse failures earned their place

All 15 labelled. Record 1500694 page 23 is a **Form P-6**, which is exactly
what the model answered before the parser rejected it as out of vocabulary.
R4 worked: the refusal to coerce an unknown class surfaced a real form family
rather than burying it in `other_nonform`.

### What this does not settle

DEFECTS #17: about 19 of the 238 predicted completion faces are a completion
report older than the G-1 and W-2 numbering, filed as `FORM 3`, `FORM 2` or
`FORM GWT-1`. They have no class, and `formscan` cannot see them either. They
count as errors in the precision figures above, correctly, and they are the
reason a corrected per-form count needs a taxonomy decision before it needs a
prompt.

DEFECTS #18: no `low`-confidence page was drawn, so R6's table still has no
`low` row and R6 stays unretired.

The census headline is unaffected. "115 of 202 records contain a completion
report" is a record-level claim, hand-verified 15 of 15, and a Form 3 gas well
record is a completion report.

## The decided fix: abstain, do not guess

**Decided and implemented 2026-08-31. The re-run and its before-and-after on
the stage-2 labels are still pending, and no number below has moved yet.**

The measurement says the classifier fails when it cannot read the form number,
not when it cannot tell two layouts apart. So the fix is not to help it guess
better. It is to stop it guessing.

On a page that is plainly a completion report face but carries no legible form
number, the classifier emits `completion_face_unknown_form` rather than picking
`g1` or `w2`. The error becomes an abstention, which is honest, countable and
reviewable, and the review queue in the viewer is where such pages belong
anyway.

### Why this does not cost the census headline

The record-level claim is a union, and the union is taken over every class that
means "this record holds a completion report":

    g1, w2, completion_face_unknown_form, completion_face_legacy

115 of 202 is computed over that set, so abstaining on a page moves it between
members of the union and never out of it. The verified headline is stable under
this change by construction, which is the property that made abstention the
right answer rather than a retreat.

What it does cost is the per-form split, and correctly: pages the census
currently counts as G-1 or W-2 on no evidence stop being counted as either. The
split gets smaller and becomes defensible, which is the trade being made.

### Making it unrepresentable rather than merely instructed (rule 6)

A prompt instruction not to guess is a rule. The stronger version is a type.

The stage-2 labels added a `form_number_legible` column, and it turned out to
be the variable that explains the errors, so it should become part of the
model's output rather than staying a property of the ground truth. Then
`PageLabel` can refuse to be constructed with `form_class` in
`EXTRACTION_TARGETS` while `form_number_legible` is false, and the confusion
this milestone measured cannot be expressed anywhere in the pipeline.

Approved and built the same day as R13. `form_number_legible` is now a required
field of every model response and an optional field of `PageLabel`, defaulting
to None so that stage-1 labels and every census row written before the change
stay constructible. The constructor refuses the guess; the parser refuses a
response that does not answer the question at all, which is the hole that would
otherwise let a model omit the field and slip past the constructor.

Verified non-destructive before anything was re-run: replaying the existing
census through the widened union still gives 115 records with a completion
report and 355 extraction-eligible pages.

### The tier-1 test plan, before the code

1. A label with an illegible form number and `form_class=g1` raises.
2. `completion_face_unknown_form` and `completion_face_legacy` are both
   extraction-eligible and both `part`-required: they are faces, and a face
   carries the identity fields the cross-form checker needs.
3. The record-level union counts all four classes, pinned against the census
   number 115 so that a change to the class list which moves that number
   fails loudly.
4. The classes are not interchangeable: `legacy` means the number is readable
   and older than the numbering, `unknown_form` means it is not readable. A
   page cannot be both.

### Road not taken: read the number instead of abstaining

The higher-ceiling alternative is to recover the illegible slice rather than
abstain on it, with a targeted OCR or vision read of the form-number region
alone: crop the top-right corner, upsample it, and ask only "what number is
printed here".

Deferred deliberately, and not a backlog item. It reopens the AWS Textract
dependency that the pipeline currently does not need, for a gain bounded above
by the illegible share of completion faces, and abstention already handles that
slice honestly. Recorded here so that the choice is visible as a choice.

## Era drift, as a measured classifier defect

The project thesis is that this archive drifts across eras and that a pipeline
which assumes one form vintage will fail quietly on the others. DEFECTS #17 is
that thesis arriving as a number rather than an argument, and it failed in
three layers at once.

**1. The taxonomy had no class to be right with.** The completion report
predates the G-1 and W-2 numbering; the older sheets are `Form 2`, `Form 3`
and `GWT-1`. About 19 of the 238 predicted completion faces are one of these,
7.9% +/- 2.6pp. Offered no correct answer, the model picked the nearest wrong
one, confidently.

**2. The guard could not fire.** R4 exists so that an out-of-vocabulary class
surfaces instead of being coerced. It never triggered, because the model did
not emit an unknown class. It emitted `g1`, which is in the vocabulary and
wrong. A parser guard catches a model that admits it does not know; it cannot
catch one that does not know that it does not know.

**3. The instrument built to catch taxonomy gaps was blind to this one.** R11
scans every page's OCR header and fails the build when a common form has no
class. `FORM_TOKEN` required a hyphen and at most two letters, so `FORM 3` and
`GWT-1` both returned the empty set. The check that exists to find missing
families could not see the family it most needed to report. Fixed 2026-08-31,
and the fix had to be measured rather than assumed: allowing a bare
three-letter prefix invented six families in one pass.

And the drift compounds. Even with the scanner fixed, the text layer finds 6
legacy pages where the labels imply about 19, because 1950s microfilm OCRs
worse than 1990s microfilm. The corpus's one GWT-1 reads `8ern GW':'.>>i`.
Older paper is harder to read at every layer of the stack at once, which is
precisely why an era-blind accuracy number is worth so little.

### How to quote the accuracy number

The arm competition measured **83.6%** class accuracy for `vision_1000`. That
is accuracy on a **uniform sample of 60 pages containing 0 G-1 pages and 2 W-2
pages**. It is not accuracy on the target classes and must never be presented
as such. Whenever the number appears, that sentence appears with it.

### R9 resolved

Parse failures after the prompt correction are 15 of 3,689, **0.4%**, down from
2.9%. That is below any threshold that would justify structured outputs, so
they stay off and R4 keeps the out-of-vocabulary signal. R9's deferred decision
is closed.

## Open finding: page grouping

`other_form` is **157 pages across 83 records, 4.3%** of the census, against
13% in the uniform labelled sample. The gap is most likely the prompt
correction, which told the model how to handle an unidentifiable form back.

These are form pages carrying no form number: W-2/W-3 back text, numbered
continuation fields, third-party affidavits from Halliburton and Sperry-Sun.
Add the 137 non-face completion-report pages and the shape is clear: **a
substantial minority of form pages cannot be identified in isolation, and a
single-page classifier cannot fix that by getting better.**

Recommendation for extraction, not implemented here: pair a section to its face
within a file by proximity and by agreement on the identity fields both carry
(operator, lease, well number, completion date), rather than by classifying the
section page harder. Record 1493495 is the worked example: page 9 is a W-2 face
and page 10 its Section II, and they agree on operator, completion date and
total depth. The cut order has no step for this; it belongs before or inside
extraction.

## RETIRED

Nothing yet. R1, R2 and R3 are already enforced by the `PageLabel` constructor
rather than by review, so they move here once the constructor is the only way
a label can be built anywhere in the pipeline.
