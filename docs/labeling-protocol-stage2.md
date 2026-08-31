# Labelling protocol, stage-2 page set

Written 2026-08-31, before the sample was drawn and before any page was
labelled. 143 pages: 105 scored, plus two severable add-ons of 23 and 15.

Stage 1 is a uniform sample of 60 pages and owns two numbers: the true class
prior and overall accuracy. It contains 0 G-1 pages and 2 W-2 pages, which is
what a uniform sample of a corpus with 112 predicted G-1 pages in 3,689 looks
like. Stage 2 is stratified over the census predictions and owns the per-class
numbers. **The two sets are never blended.** A stratified sample gives a biased
estimate of overall accuracy by construction, and a uniform one cannot see the
target classes at all.

## What stage 2 is for

To make the G-1 versus W-2 distinction measurable. `docs/modules/classify.md`
carries the census finding that the per-form split is provisional and not
reportable: the hand-check contradicted the composition on 6 of the 9 sampled
records where the census claimed both forms. There is currently no instrument
that could tell whether a change to the prompt helped.

**Stage 2 does not fix anything.** The prompt correction is a separate step,
gated on these labels existing, with its own before-and-after run against them.
Changing the prompt first would spend the one iteration the labelled set can
absorb on a blind change.

## The frame

The 3,674 census rows that parsed, in `data/census/vision_1000.jsonl`, plus the
15 that did not. Strata are disjoint, and every page's stratum is decided by
census fields and the OCR header token before the draw, never afterwards.

### The OCR header token as a design variable

`pipeline/formscan.py` reads the embedded text layer and reports the form
number printed in the page's own header, ignoring mentions of other forms.
Cross-tabulated against the census on the 238 predicted completion faces:

| Predicted | n | OCR reads its own number | OCR reads a different one | OCR reads none |
|---|---|---|---|---|
| `g1` face | 72 | 29 | 1 (P-5) | 42 |
| `w2` face | 166 | 46 | 11, of which 7 are W-15 | 109 |

Zero contradictions: on all 75 pages where OCR resolves a completion form
number, it is the one the model chose. Two consequences for the allocation.
Those 75 pages carry corroboration from a signal that never saw the model, so
they get fewer labels than the 163 where the printed number did not survive
imaging. And the 7 whose OCR reads W-15 are the confusion Alex hit twice while
verifying the census, pre-identified and small enough to label exhaustively.

The corroboration is weaker than it looks and the protocol says so rather than
leaning on it. OCR and the model read the same scan, so the corroborated
subset is really "pages whose form number is legible", which is the easy half.
That is a reason to sample it thinly, not to skip it: DEFECTS #15 and #16 are
both cases of this scanner calling a mention a header. Its known failure is a
page that lists the forms it is filed alongside, so: of the 75 corroborated
faces, **0** carry "status report", "when to file", "where to file" or
"instructions" in their header region. Measured, not assumed.

## Allocation

| | Stratum | N | n | What it buys |
|---|---|---|---|---|
| A | `g1` face, OCR reads no G-1 | 43 | 22 | the contested half of G-1 precision |
| B | `g1` face, OCR reads G-1 | 29 | 8 | checks the corroboration itself |
| C | `w2` face, OCR reads no W-2 and no W-15 | 113 | 25 | the contested half of W-2 precision |
| D | `w2` face, OCR reads W-15 | 7 | 7 | exhaustive; the confusion seen in verify.csv |
| E | `w2` face, OCR reads W-2 | 46 | 8 | as B |
| F | `g1`/`w2` with part other than face | 137 | 15 | how often attribution is invented |
| G | confusable pages not predicted completion | 361 | 20 | the only recall instrument |
| | **scored** | **736** | **105** | |
| H | aspect ratio over 2.0 | 23 | 23 | R1 has never been measured |
| I | census parse failures | 15 | 15 | not scoreable; a triage list |

G is `w15` face 165, `other_form` face 65, `g5` face 50, `l1` face 46,
`ws1_sw1` face 16, and `other_form` with part unknown, continuation or absent,
19. L-1 is in there because it is the one form in this corpus whose printed
instructions name both extraction targets, which is how DEFECTS #15 was found.

Strata A to G contain no oversize page and no parse failure, so H and I do not
overlap them and all 143 rows are distinct pages.

### What the sizes are worth

Precision is conditional on the prediction, and a stratum is a prediction cell,
so per-class precision needs no reweighting across classes: A and B combine to
G-1 face precision, C, D and E to W-2 face precision, each weighted by frame
size. `pipeline/estimate.py` does this, with the finite-population correction
that matters here because some strata sample half their frame.

At the precisions the census verification suggests, roughly 0.75 in the
uncorroborated strata and 0.95 in the corroborated ones, this allocation gives
a standard error of about **4.8 percentage points on each of the two face
precisions**. That number is computed from assumed proportions and is what the
design is worth; the realized error bar comes from the labels and may differ.

F is small on purpose. A page with no printed form number must be labelled
`other_form` / `unknown` under the rule below, so F does not measure G-1 versus
W-2 at all. It measures how often the model asserts a form the page does not
name, which is the mechanism behind the unreportable split, to about +/-11pp.

**G is a bound, not an estimate, and will be reported as one.** 20 pages over
a 361-page frame supports "0 of 20 drawn were completion faces" and nothing
stronger. It is deliberately thin because record-level presence is the claim
that was already verified, 15 of 15, so a missed page costs less here than a
misattributed one. If recall becomes a headline number, this stratum has to
roughly triple first.

## Drawing the sample

Simple random sample without replacement inside each stratum. Draw seed
20260831. Both seeds are recorded here before the draw.

**Clustering is real and this design does not correct for it.** Three records
carry 12 predicted `w2` faces each, and pages inside one record share a form
era, an operator and a scanning batch, so they are not 25 independent draws.
The effective sample size is below the nominal one and the 4.8pp above is
therefore a floor on the error bar rather than the error bar. A per-record cap
was considered and rejected: it would make the sample non-self-weighting and
put a bias into the estimator to remove a variance we can instead report. The
realized spread of records per stratum is printed by the sampler and belongs in
the write-up.

## Blinding

The sheet is stratified over predictions, so the prediction must not be
visible while labelling.

- No predicted class, confidence or OCR token appears in the workbook.
- Rows are shuffled across all strata under order seed 20260901, so position
  carries no information about which stratum a row came from.
- Thumbnails are named by `seq` and page id only, in shuffled order.
- The stratum assignment lives in `tests/fixtures/stage2_strata.csv`. It is
  committed for reproducibility and for the tier-2 integrity check. **Do not
  open it while labelling.**

Knowing the sample is enriched for completion forms is unavoidable and
harmless. Knowing what the model said about the page in front of you is not.

### Pages already seen

30 of the 238 faces sit in the 15 records Alex rendered while verifying the
census, and those judgements were made with the whole record visible, which the
labelling rule forbids. They stay in the frame: dropping them would bias it
toward records nobody has looked at. They are flagged in the strata file, and
accuracy gets reported with and without them, the same way stage 1 handles
rows noted `unsure`.

## Labelling rules

Identical to `docs/labeling-protocol.md`, which stays the reference for the
class list, the `part` values, the orientation values, the P-4 trap, the
`back_instructions` distinction and the hard cases. In particular:

**Label only from what is visible on the page in front of you.** Do not open
neighbouring pages. A page that does not identify its own form is `other_form`
with `part: unknown`, however obvious its parent is. Stage 2 leans on this
harder than stage 1 did, because stratum F is 137 pages that mostly carry no
form number, and the whole point of F is to count them honestly.

Read the `g1` vs `g5` and `g1` vs `w2` hard cases again before starting. This
sample is enriched for exactly those.

### One new column

`form_number_legible`, `y` or `n`. Can you read a printed form number on this
page, whatever it says. It is the human counterpart to the OCR header variable
and makes "errors concentrate where the number cannot be read" a measurement
rather than a story. Answer it for every row, including census-only classes,
where the answer is nearly always `n`.

Columns are otherwise the stage-1 set: `form_class`, `part`, `orientation`,
`note`. The same validator rules apply, so `part` is required for form classes
and must be empty for census-only ones.

### The add-ons

**H, the 23 oversize pages.** Rendered with a floor on the short edge rather
than at the flat 1400px long-edge cap, since a 11,264 x 3,040 fold-out at that
cap has a 378px short edge and ground truth should be the best view available,
not the model's view. Label them like any other page. Most are plats.

**I, the 15 parse failures.** These have no prediction, so they cannot be
scored for accuracy and sit outside every denominator. Label them anyway: two
of them made the model answer `p6`, which is the signature of DEFECTS #10 and
#11, a form family the taxonomy may still be missing. If a real form number
appears here that is not in the class list, that is a finding.

## What gets computed, defined before the labels exist

1. Precision of `g1` face and of `w2` face, stratified, with the finite
   population correction, reported with the standard error and with the
   realized record spread beside it.
2. The rate at which a page carrying no form number is assigned one, from F.
3. A confusion matrix restricted to the completion neighbourhood: the true
   class of everything drawn from A to E, and how many completion faces appear
   in G.
4. The record-level claim re-derived from labels: of the 25 records the census
   says hold both a G-1 and a W-2, how many do the drawn labels support. About
   26 of the 105 scored pages are expected to land in those records, covering
   perhaps 18 of the 25, so this is a check on the claim rather than a
   replacement for it.
5. Accuracy per self-reported confidence bucket, which R6 requires before any
   threshold is put on that value.

Each of these is reported with and without rows the labeller noted `unsure`.

## What stage 2 cannot measure

Recall over the 2,938 pages outside strata A to G. Per-class numbers for any
class other than `g1` and `w2`. Overall accuracy or the class prior, which
belong to stage 1 and are not recoverable from a stratified sample. Anything
about the 15 parse failures as accuracy, since they have no prediction to be
right or wrong.

## Before handing it back

    make test

The validator wakes on the first filled row and checks the same things it
checks for stage 1, plus that every drawn page id still exists in the census
and that the strata sizes still match a recount of `data/census/vision_1000.jsonl`.
A census file that changed under the labels would otherwise score them against
a frame that no longer exists.
