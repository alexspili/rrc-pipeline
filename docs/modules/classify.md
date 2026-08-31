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
measurable.**

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
