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
