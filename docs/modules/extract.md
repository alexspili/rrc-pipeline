# Module: extraction

Reads the completion-report pages the classifier found and returns structured
values, each carrying where on the page it came from.

Not yet built. This file currently records the decisions taken before any code
exists, so that they are not silently revisited later.

## Provenance is region-level, from the model, from v1

**Settled 2026-08-31, before any extraction code.**

Every extracted value carries a coordinate region that the vision model returns
alongside the value itself. The schema has the field from v1 and the prompt
asks for it from v1, so that provenance is never something the pipeline has to
be re-run to acquire.

These regions are **approximate region locators, not pixel-precise boxes**.
That is what they are for: a reviewer opening the span viewer needs to be shown
where on the page to look, and a highlight that lands on the right field is
sufficient for that. Anything asserting more precision than the model actually
has would be a claim the repo cannot defend.

Coordinates are fractions of page width and height rather than pixels. The
image sent to the model is downscaled from the source scan, and the viewer
renders at a third size again; fractions survive both, pixels do not.

## Cost is output, not pixels

**Measured 2026-08-31, `scripts/probe_sonnet.py`, one two-page completion
report on `claude-sonnet-5` at $2/$10 per 1M tokens.**

| | Tokens | Share of cost |
|---|---|---|
| Input, both page images plus prompt | 5,975 | 15% |
| Output, 56 value objects | 6,559 | 85% |

$0.0775 standard, $0.0388 batched.

Sending the same document at a 1000px cap instead of 1568px costs 2,947 input
tokens rather than 5,975: a difference of about **$0.006 per document**.

**So resolution is effectively free and must not be optimised.** Extraction
reads handwriting, struck-through corrections and small figures off degraded
microfilm, and the accuracy that buys is worth far more than six tenths of a
cent. Anyone reaching for a smaller image to save money is trading the thing
that matters for the thing that does not.

If cost ever needs to come down, the lever is output compactness, because that
is where 85% of it is. Nothing in the schema is currently worth removing for
that reason.

This reverses two earlier estimates, one of them 2.2x high and one 2x low, in
opposite directions. See DEFECTS #21.

## What the smoke set caught that the probe could not

**Recorded 2026-08-31, after the first 20-document run failed completely.**

The probe measured one document, reported it as a clean success, and it was one
on its own terms. It could not have caught either of the two defects that
stopped the first smoke run.

The probe was a single document whose page numbering I had supplied by hand, so
it could not have caught the page-index defect. And its output at 6,559 tokens
sat close enough to the 8,000-token cap that it could not have caught the
truncation either. A 20-document smoke set found both in one pass for a dollar.
That is the argument for the tiered eval rather than for probing harder.

The four defects, all now pinned by tier-1 tests built from the real response
bodies:

1. **Page indices.** The model is shown "Page 1 of 2" and answers with that
   index; the document knows those pages are 9 and 10 of the file.
   `parse_report` compared the two directly, so every value cited a page its
   document did not have.
2. **`max_tokens` at 8,000** truncated 4 of 14 documents mid-string, and each
   surfaced as "malformed JSON" rather than as truncation. Completed documents
   average 5,114 output tokens; the largest in the finished run reached 11,535.
3. **An empty table arrives as a value object**, not as `[]`. The prompt said
   every value is an object and also that tables are arrays, and an empty table
   satisfies the first rule.
4. **`form_class` came back bare on four documents and wrapped on six**,
   because the prompt asked for both shapes in one block.

Three and four were ambiguities in the prompt rather than model failures.

### A cache key covers everything that shapes a response, or the cache refuses it

`max_tokens` is a request parameter and not part of the cache key, which is
(document hash, prompt hash) under CLAUDE.md rule 7. A truncated response
stored under that key would have been served back unchanged forever, with the
cap already raised and the bug already fixed.

So a truncated response is now its own error and is never cached. The general
rule, worth more than the instance: **a cache key must cover everything that
shapes a response, or the cache must refuse to store that response.** Anything
that changes an answer without changing its key is a way for a fixed bug to
keep returning. DEFECTS #14 is the same family from the other direction, where
the cached path and the fresh path disagreed about how to handle a failure.

### The vocabulary is the taxonomy's, not the prompt's

DEFECTS #22: `form_class` arrived as `g1` on two documents and `g-1` on two
others, which are two classes to every count downstream. It is now normalised
and validated against the whole `PageClass` vocabulary rather than against the
two values the prompt asks for. The same run answered `w15` on a page the
census called a W-2 face and the stage-2 labels confirm is a W-15 cementing
report. Narrowing the check to `g1` and `w2` would have discarded that.

## Extraction disagreeing with the classifier is output, not an override

The first finished smoke run disagreed with the census on three documents:
`w15` where the census said `w2` face, on a page the stage-2 labels confirm is
a W-15, and `w2` twice where the census said `g1`.

That is reported and not acted on. The bar is the one the W-15 header rule had
to clear: measure the rule against labels before wiring it, and the general
form of that rule failed exactly that test. Three data points, two of them
still unresolved until the ground truth is keyed, is a signal worth watching
and not a mechanism.

## Validation rules, and why they carry two severities

`pipeline/validate.py`, pure, cut order step 4. It reads a `CompletionReport`
and returns findings. No corpus, no model, no I/O.

**ERROR** means structurally impossible on any form of any era: a plug-back
below the well's own total depth, a perforation interval that ends above where
it starts, a packer below the tubing shoe, drilling that finishes before it
starts, a Texas API number whose county code is not the county the form names.

**WARNING** means suspicious with an unmeasured false-positive rate. Casing
strings out of depth order, and a test dated before the completion date, are
both real signals and both have plausible innocent explanations that nobody has
counted yet. They are surfaced for review and must not be reported as defects
until somebody measures how often they fire on documents that are correct.

The split is DEFECTS #10 and #11 turned into a habit. Rules written from the
handful of documents somebody happened to read do not survive a corpus spanning
1950s to 2008 paper, so every rule names the documents it was checked against,
and a rule checked against two documents is a warning.

Two things the rules deliberately do not do. A field that is `blank`,
`illegible` or `not_on_this_form` produces no finding: a 1975 Form W-2 has no
API number, and manufacturing a defect out of a form revision is the failure
the status enum exists to prevent. And a county missing from the county-code
map produces no finding either, because that is a gap in the map rather than a
defect in the document.

The county-prefix rule is the one that makes the demo document machine-checkable.
Record 1501720 carries 42-039-31674 on its G-1 face and 42-309-31674 on the G-5
in the same file. Brazoria is 039, so the transposition is caught from the
single page that carries it, without needing the other form to compare against.

## Road not taken: AWS Textract word-level geometry

Textract `DetectDocumentText` returns word-level bounding boxes, which would be
tighter than what a vision model reports about its own output.

It stays off, and it stays documented rather than queued. The reasons are the
ones that also kept it out of the classifier:

- It reopens an AWS dependency. The pipeline currently runs on a laptop with
  one API key and no cloud account, and that property is worth more than
  tighter boxes.
- Region highlights are sufficient for the task the provenance exists to
  serve, which is human review of an extracted value against the page.
- The gain is bounded and measurable, so it does not need to be guessed at.

Same posture as the classifier's three-arm competition: the cheap default runs,
the expensive alternative is a measured comparison arm, and it is turned on only
if a measurement says the gain justifies the dependency. Not a backlog item. A
choice, recorded with its reason so that reversing it has to be argued.
