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
    before it reaches a corpus run.
    Origin: DEFECTS #3, applied to our own vendor rather than Neubus.
    `output_config.format` is unproven on Haiku here, so the default path is
    plain JSON parsing and structured outputs are wired only after
    scripts/probe_haiku.py passes.
    Pinned by: pending, the probe result recorded below.

## Probe results

Not yet run. ANTHROPIC_API_KEY is absent from .env; CLAUDE.md's Environment
section says it belongs there.

| Probe | Result |
|---|---|
| `output_config.format` accepted on claude-haiku-4-5 | pending |
| Measured image tokens, 1568px long edge | pending |
| Measured image tokens, 1000px long edge | pending |
| Estimate (w*h/750) it replaces | 2,540 / 1,033 |

## RETIRED

Nothing yet. R1, R2 and R3 are already enforced by the `PageLabel` constructor
rather than by review, so they move here once the constructor is the only way
a label can be built anywhere in the pipeline.
