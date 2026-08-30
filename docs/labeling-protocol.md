# Labelling protocol, stage-1 page set

Written 2026-08-30, before any page was labelled and before any model
prediction existed. 60 pages, drawn uniformly at random from all 3,689 pages
in the closed corpus, seed 20260830.

These labels are the ground truth the classifier is scored against. Everything
below exists to make them reproducible by someone else and defensible in an
interview.

## Why the labels are made by hand and not by a model

The classifier being measured is Claude. Ground truth produced by Claude would
measure agreement between two runs of the same model, not accuracy, and the
resulting number would be worthless the moment anyone asked how it was made.

For the same reason, Claude Code did not pre-fill any row, and no model
prediction exists yet for these pages. The labels come first. A handful of
thumbnails were opened while writing this document, to ground the descriptions
below in what the corpus actually contains; no page-specific answers were
recorded here.

## Setup

    open data/labelset/thumbs                  # select all, open in Preview
    open tests/fixtures/labels_stage1.csv

Thumbnails are named `01_...` through `60_...` and the CSV column `seq` runs
1 to 60 in the same order. Arrow through Preview and move down the sheet in
lockstep.

**The alignment is the thing to protect.** A one-row slip corrupts every label
after it, and nothing downstream can catch it: the labels stay internally
valid and are simply wrong. Check the `page_id` in the sheet against the one
in the filename every ten rows or so.

If you open the CSV in Numbers or Excel, save back as CSV to the same path,
and check that `page_id` survived: spreadsheet apps sometimes read
`1493418-0-12` as a formula or a date. A plain text editor avoids this
entirely and the rows are short.

## What to fill in

Three columns: `form_class`, `part`, `orientation`. A fourth, `note`, is free
text. Everything else is pre-filled and should not be touched.

## The one rule that overrides every other

**Label only from what is visible on the page in front of you.** Do not open
the neighbouring pages to work out which form a page belongs to, even when you
already know, and even when it is obvious.

The classifier is given one page and no neighbours. A label derived from
context it cannot see is a label it can never produce, and an accuracy figure
measured against such labels is a ceiling no model could reach. The number
stops meaning anything.

So: a page that does not identify its own form is `other_form` with
`part: unknown`, however certain you are that it is the second sheet of the G-1
three pages back. If you want that on the record, write it in `note`, which is
not scored.

This costs some accuracy on paper and buys the only thing that matters, which
is that the measurement is real. It also tells us something worth knowing: how
many pages in this corpus are unidentifiable in isolation is itself a result,
and it decides whether page grouping needs to be a separate pass.

## Procedure, per page

**1. Find the form number.** Top right of the page, almost always, with a
revision date beneath it: `FORM P-4  5/90`, `Form W-15 (Rev. 11-1-69)`,
`FORM WS-1 Rev. 6/1/59`. That number is the answer to `form_class` whenever it
is present and in the list below.

**2. If there is no form number, read the centred title.** `CEMENTING REPORT`,
`WELL STATUS REPORT`, `PRODUCER'S TRANSPORTATION AUTHORITY`. Scans are heavily
speckled and a form number is often partly blotted out; the title usually
survives.

**3. If it is not a form at all,** it is correspondence, a drawing, a card, a
blank, or something else. See the census-only classes.

**4. If it is plainly a form but names no number and no title you recognise,**
that is `other_form`, `part: unknown`. See the rule above: do not go looking in
the neighbouring pages.

**5. Then set `part`,** and **6. then `orientation`.**

## form_class

### Extraction targets

| Value | What it is | How you know |
|---|---|---|
| `g1` | Gas well completion report | `FORM G-1`. Title mentions Back Pressure Test, Completion or Recompletion Report, Potential |
| `w2` | Oil well completion report | `FORM W-2`. Same shape as G-1, oil wells |

### Identity-bearing forms

These carry operator, lease and well identity, so they feed the cross-form
disagreement checker as well as the census.

| Value | What it is | How you know |
|---|---|---|
| `w1` | Application for permit to drill | `FORM W-1`, `W-1A`, `W-1C` |
| `w3` | Plugging record | `FORM W-3`. Plugging, perforation intervals |
| `p4` | Producer's transportation authority | `FORM P-4`. Gatherer / purchaser / nominator table |
| `p5` | Operator organization report | `FORM P-5`. **See the P-4 trap below** |
| `g5` | Gas well classification report | `FORM G-5`. Not a G-1, see hard cases |
| `gt1` | Gas gatherer or tax report | `FORM GT-1` |
| `l1` | Gas gathering and load report | `FORM L-1` |
| `w12` | Directional survey, record of inclination | `FORM W-12`. Depth / course-length tables |
| `w15` | Cementing report | `FORM W-15`. Sacks of cement, slurry volume |
| `p17` | Permit application | `FORM P-17`. Typed applicant half, handwritten RRC block |
| `w4_family` | W-4, W-4A, W-5, W-6 | Any of those four numbers |
| `ws1_sw1` | Pre-1970 families: WS-1 well status, SW-1 | `FORM WS-1` / `FORM SW-1`, 1950s-60s revision dates, often notarised |

**The P-4 trap.** A P-4 face carries, in its third field, "Operator name
exactly as shown on Form P-5 Organization Report". That is a P-4 mentioning a
P-5, not a P-5. The form number that counts is the one printed alone in the
top-right corner, not one embedded in a field label. This single sentence
caused a scan of the whole corpus to report P-5 on 373 pages when it is on 147.

### Census only

| Value | What it is |
|---|---|
| `letter_memo` | Any correspondence: a typed 1960s letter, an internal RRC memo, a printed email thread |
| `plat_map` | A survey plat or map. Tract boundaries, a north arrow, bearings and distances |
| `schematic` | A wellbore diagram. Vertical section, casing strings, depths down the side |
| `card_handwritten` | A small handwritten card: separator, ID, or X-reference. These three are merged deliberately |
| `blank_or_artifact` | A blank page, or a scan with no content. Expect white paper inside a heavy black scanner border, sometimes with hole punches |
| `other_form` | A recognisable RRC form whose number is not in the list above |
| `other_nonform` | Not a form and not any of the above |

**`other_form` matters.** It means an RRC form whose number is not in the list
above, or a form page that does not identify itself. Write the number in `note`
if you can read one.

The list above was itself corrected before you started: five families (W-1,
P-5, L-1, GT-1, W-12) occurring on roughly 400 pages were missing from it, and
would have landed here. See DEFECTS #10. So if one number keeps recurring in
`other_form`, the class list is still wrong and that is exactly what this class
is for. Say so rather than forcing pages into a neighbouring class.

## part

Fill this for every form class. Leave it **empty** for every census-only
class: a plat has no Section III, and the validator rejects a part on one.

| Value | When |
|---|---|
| `face` | The first page: form number, title, identity fields. Most single-page forms (P-4, W-15, WS-1) are just this |
| `sec_ii` | Explicitly Section II |
| `sec_iii` | Explicitly Section III |
| `continuation` | A later page of the same form that is not a numbered section |
| `back_instructions` | The pre-printed reverse. See below, this one is easy to get wrong |
| `unknown` | Plainly part of a form, but which page is not decidable |

### back_instructions, read this carefully

My first version of this section was wrong in both directions. Corrected from
a scan of the OCR text of all 3,689 pages (DEFECTS #10).

**A back announces itself.** Real reverses in this corpus say so, in words:

    Side 2 ... Form W-4A ... SKETCH OF MULTIPLE COMPLETION
    Instructions Form G-5: Gas Well Classification Report. This report shall...
    RECORD OF INCLINATION (Continued from reverse side)

251 pages, 6.8% of the corpus, carry a marker in that family. If a page does
not say something of that kind, it is very probably not a back.

**The pointer phrases are printed on the FACE.** "READ INSTRUCTIONS ON BACK",
"- OVER -", "MUST COMPLY WITH THE INSTRUCTIONS ON REVERSE SIDE HEREOF". Seeing
one of these means you are looking at the front. 486 pages carry such a
pointer, and they are faces.

**Instructions and continuations are different.** Only prose telling you how to
file the form is `back_instructions`. A reverse carrying a data table, like
`RECORD OF INCLINATION (Continued from reverse side)` with depths and course
lengths filled in, is a `continuation`. Calling that one `back_instructions`
would mark real data as not worth extracting.

**A sheet is not reliably two pages.** Of the 486 pages that point to a reverse
side, only 107 (22%) are actually followed by one in the scan. Imaging was
inconsistent and mostly front-only. Never assume page N+1 belongs to page N.

## orientation

How the page **sits**, not how it should sit. Report it, do not correct it.

| Value | When |
|---|---|
| `up` | Text reads normally |
| `cw90` | Rotate the page 90 degrees clockwise to read it |
| `ccw90` | Rotate 90 degrees anticlockwise to read it |
| `down` | Upside down |

A landscape-shaped page is not automatically rotated. Plats and wide tables are
genuinely landscape and read `up`. Nine of the 60 pages are landscape-shaped;
that tells you nothing about their orientation on its own.

For a blank page, use `up`.

## Hard cases

**`g1` vs `g5`.** Both are gas forms with similar layouts. G-1 is the
completion report; G-5 is the Gas Well Classification Report. Record 1501720
contains both, and the G-5 is where the transposed API digit lives that the
cross-form checker is meant to catch. Read the form number twice here.

**`g1` vs `w2`.** Gas well against oil well completion. Same family, different
number in the header.

**A form covered in handwriting is still that form.** Many faces are filled in
entirely by hand. Handwriting does not make a page `card_handwritten`; that
class is for small cards with no form structure at all.

**Heavy black borders and speckle are normal.** These are microfilm scans. A
page is not `blank_or_artifact` because it is dirty, only because it carries
no content.

**A printed email thread is `letter_memo`.** Even a 2015 one that looks nothing
like the rest of the corpus.

## When you cannot tell

There is no "unsure" class, on purpose. Make your best call, then write
`unsure` in the `note` column, plus what you were torn between if it is quick.

Accuracy will be reported twice, with and without the noted rows, so an
ambiguous page cannot quietly inflate or deflate an arm's score.

If you write `unsure` more than about eight times in 60, stop and say so. At
that rate the taxonomy is wrong, and the fix is the class list, not more
staring.

## Before handing it back

    make test

The validator sleeps while the file is blank and wakes on the first filled
row. It checks that all 60 rows are labelled, that every value is in the same
vocabulary the classifier is scored against, that `part` is present for form
classes and absent for census-only ones, and that each `page_id` still matches
its own coordinates.

A typo fails there. Uncaught, it would score a correct prediction as wrong.

## What this sample can and cannot measure

It is uniform, so it gives an unbiased estimate of overall accuracy and of the
true class prior. At n=60 the error bar on overall accuracy is roughly +/-6
percentage points at 90% confidence.

It contains **no oversize page**, which is correct: 23 of 3,689 pages exceed
aspect ratio 2.0, so a 60-page uniform sample would rarely include one. Stage 1
therefore cannot measure oversize handling at all, and stage 2 has to include
those pages deliberately.

Rare classes will appear once or not at all. Per-class recall is not
estimable from this sample and will not be reported from it.
