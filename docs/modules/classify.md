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
    Pinned by: pending, the calibration table produced by the smoke run.

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
    decision for the census is deferred to the measured parse-failure rate from
    the smoke run: near zero and the plain path keeps the diagnostic, material
    and structured outputs get wired.
    Pinned by: pending, parse-failure rate from the smoke run.

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

## RETIRED

Nothing yet. R1, R2 and R3 are already enforced by the `PageLabel` constructor
rather than by review, so they move here once the constructor is the only way
a label can be built anywhere in the pipeline.
