# Labelling protocol, extraction ground truth

Written 2026-08-31, before any field was keyed. 15 documents, 27 fields each,
405 rows.

These labels are the ground truth extraction accuracy is measured against.
Everything below exists to make them reproducible by someone else and
defensible in an interview.

## Setup

    open data/labelset/thumbs_extract          # select all, open in Preview
    open data/labelset/extract_truth.xlsx      # or the CSV, see below

Thumbnails are named `NN_record_pNNN.png`, so sorting by filename walks the
sheet in order: document 1's pages first, then document 2's. The sheet's
`pages` column lists the same pages for the same document.

The workbook has a dropdown on `status` and a live `check` column. The CSV at
`tests/fixtures/extract_truth.csv` is the committed source of truth; export the
workbook back over it when you are done.

## What you are filling in

Two columns per row, `value` and `status`, and a free-text `note` that is not
scored. Everything else is prefilled and should not be touched.

A row is one field of one document. The document is all of its pages together:
where a field appears on any page of the document, it is present.

## status is the column that matters most

| Value | When |
|---|---|
| `present` | Something is written in this field and you can read it |
| `blank` | The field exists on this form and nobody filled it in |
| `illegible` | Something is written and you cannot make it out |
| `not_on_this_form` | This form revision has no such field at all |
| `page_not_in_document` | The form has this field, on a page you were not given |

These are four different facts about a field that has no value, and mixing any
two of them measures nothing. This is the reason the schema has a status enum
at all.

**The two absent-for-a-reason statuses, defined precisely.** `not_on_this_form`
means the form family and revision does not print this field anywhere: an era
fact about the paper. `page_not_in_document` means the family does print it,
on a page that is absent from this document: a completeness fact about the
scan.

"This form" means the **form family**, not the page in front of you. A W-2
Section II does not print a lease name box, but Form W-2 does, so on a section
page separated from its face the lease name is `page_not_in_document`.

Added 2026-09-01 after the first scoring run found that reading rule 32 of 333
times, in both directions (DEFECTS #27). It governs runs from here on; nothing
already keyed was changed.

**`blank` against `not_on_this_form`.** A 1975 Form W-2 has no API number field
anywhere on it, which is `not_on_this_form`. A 1983 Form G-1 has an API number
box that somebody left empty, which is `blank`. The test is simple: **is there
a printed box or label for this field on the paper?** If there is no label it
is `not_on_this_form`, whatever you know about wells.

**`page_not_in_document`.** Most of this archive was imaged front only: of the
486 corpus pages that print a "reverse side" pointer, 107 are actually followed
by one. So a W-2 face often arrives with no reverse, and the reverse is where
every completion and casing field lives.

When that happens, those fields are `page_not_in_document`. Not `blank`, since
nobody left them empty. Not `not_on_this_form`, since the form plainly has
them: the face itself prints "if well is newly completed or recompleted, fill
in reverse side also".

**Nine of your fifteen documents are face-only**, so this is about 90 of the
405 rows. Check the `pages` column: one page number means one page, and the
thumbnails are the whole document.

**It runs the other way too.** Three documents are the opposite case: the page
you have is a section or a continuation, and the face carrying the identity
block is not in the document. Documents 6, 8 and 9, records 1495193 page 8 and
1495195 pages 6 and 38, each sit immediately after another completion face,
which is almost certainly the face they belong to (DEFECTS #25).

Same rule, mirrored: the identity fields are `page_not_in_document`. The form
has a field 2 for the lease name; this document just does not contain the page
it is printed on. Key whatever the page you do have carries, in the normal way.

**Do not go and look at the neighbouring page.** It is not part of the document,
the model was not given it, and a value read from it would be one no correct
output could produce.

The rule in one line: **`not_on_this_form` is about the form, and
`page_not_in_document` is about the scan.**

`illegible` is for ink you cannot read, not for a field you find confusing.
These are microfilm scans and some of them are bad; say so rather than
guessing.

**When you cannot read the printed label.** Some scans are degraded enough that
the field labels are gone even though you know from the form which field sits
where. `illegible` is about the **value**, not the label: reading the label is
how you find the field, and failing to read it does not change what is or is
not written in it.

- You can see the field's area and it is plainly empty: `blank`.
- The scan is degraded enough that faint pencil or a thin typewriter strike
  would not have survived either: `illegible`. You cannot tell an empty field
  from a lost one, and saying so claims less than guessing.

And if the label is unreadable **and** you are unsure which revision this is,
prefer `illegible` over `blank`: you may be pointing at a field this revision
does not have, which would be `not_on_this_form`.

Whichever you choose, write `label illegible` in the note. A blank against
illegible disagreement between your label and the model's is a distinct
failure class rather than a plain error, and the note is what separates them
at scoring time.

## value: exactly what is written

Key what is on the paper, not what it means. `9/22/77`, not `1977-09-22`.
`9200'` with the foot mark if the foot mark is there. `2-3/8`, not `2.375`.

The model returns both a normalised value and the raw text, and scoring
compares against the raw. Normalising by hand would make your labels
disagree with correct output.

Leave `value` empty for any status other than `present`.

**A struck-through value.** These forms are full of them: a printed or typed
entry crossed out and replaced by hand. Key **the replacement** in `value`,
and put the struck-through original in `note`. Both documents read while
designing this schema carry one, so expect them.

**A field that appears twice with different values.** Key the one on the face
and write the other in `note`. A disagreement inside one document is a real
finding and the note is where it survives.

## The 27 fields, and where they live

Field numbers below are the numbers printed on the form. They differ between
the G-1 and the W-2, and between revisions of each, so **read the printed
label rather than counting boxes**.

### document

| Field | Where |
|---|---|
| `form_revision` | Beside the form number, top right: `Rev. 4/1/83`, `Rev. 6/30/75`. Key it as printed |

### identity

| Field | Where |
|---|---|
| `field_name` | Field 1, "FIELD NAME (as per RRC Records or Wildcat)" |
| `lease_name` | Field 2 |
| `well_number` | Field 9, "Well No." or "Well Number" |
| `operator_name` | Field 3, "OPERATOR'S NAME (Exactly as shown on Form P-5...)" |
| `operator_address` | Field 4 |
| `county` | Field 10, "County of well site" |
| `rrc_district` | Field 7, "RRC District No." |
| `location_survey` | "Location (Section, Block, and Survey)". Field 5 on the G-1, 6a on the 1975 W-2 |
| `distance_to_town` | "Distance and direction to nearest town in this county" |
| `api_number` | Top of the G-1 face, beside the district. **The 1975 W-2 has none** |
| `rrc_well_id` | Field 8. "RRC Gas ID No." on a G-1, "RRC Lease Number" on a W-2. Whichever that slot holds |
| `purpose_of_filing` | Field 11, a set of checkboxes: Initial Potential, Retest, Reclass, Well record only. Key the box that is ticked |
| `completion_date` | Field 14, "Completion or recompletion date" |
| `pipeline_connection` | Field 13 on the G-1, "Pipe Line Connection". Check whether the W-2 in front of you has one |
| `logs_run` | "Type of Electric or other Log Run". Field 16 on the G-1, 13 on the 1975 W-2 |

### completion

These live in the completion-and-casing section, which on the 1975 W-2 is
**Section II on the reverse**, headed "DATA ON WELL COMPLETION AND LOG".

**Read this before keying a G-1.** The 1983 G-1's Section I is gas measurement
and its Section II is pressure calculations. Neither carries depths or casing.

So for a G-1 the ten fields below are usually `not_on_this_form`, because the
form has no such section, while for a W-2 whose reverse was not imaged they
are `page_not_in_document`, because it does. Judge it from the paper in front
of you rather than from this paragraph: read the form's own section headings
and its own pointers to a reverse.

| Field | Where |
|---|---|
| `type_of_completion` | "Type of Completion" checkboxes: New Well, Deepening, Plug Back, Other |
| `date_permit_issued` | "Date Permit Issued" |
| `drilling_commenced` | "Date Plug Back, Deepening, Work Over or Drilling Operations ... Commenced" |
| `drilling_completed` | The "Completed" half of the same field |
| `total_depth` | "Total Depth" |
| `plug_back_depth` | "P.B. Depth" |
| `top_of_pay` | "Top of Pay" |
| `elevation` | "Elevation (DF, RKB, RT, GR, ETC)" |
| `directional_survey` | "Was Directional Survey Made", Yes or No. Key the box that is ticked |
| `drilling_contractor` | "Name of Drilling Contractor" |

### test

| Field | Where |
|---|---|
| `date_of_test` | "Date of Test", the first field of Section I on both forms |

**Only this one field from the test sections.** The production figures, choke
sizes and pressure calculations are v2 and are not in this sheet.

## What is not in this sheet

The casing, liner, tubing, perforation, treatment and formation tables. They
are extracted and they will be scored, later, on a smaller subset. Keying
three casing rows times eight columns times fifteen documents by hand is not
where the first measurement should spend your time.

## Suggested order

Sitting one: `document.form_revision`, the fifteen `identity` fields, and
`total_depth`, `plug_back_depth`, `top_of_pay` from `completion`. That is the
identity and depth core, and it covers every field the validation rules
actually consume.

Sitting two: the rest of `completion`, and `test.date_of_test`.

## When you cannot tell

There is no "unsure" status, on purpose. Make your best call and write
`unsure` in `note`, plus what you were torn between if it is quick.

Accuracy will be reported twice, with and without the noted rows, so an
ambiguous field cannot quietly inflate or deflate the score.

If you write `unsure` more than about twenty times in 405, stop and say so. At
that rate the field list or the page images are the problem, not the keying.

## One document you should know about

Document 1, record 1493495, is the document I read page by page while designing
this schema, and the anchor the extraction probe measured. Your labels for it
are blind and fine; my side is not, so accuracy will be reported with and
without it and the public number is the one without. See DEFECTS #23. Key it
exactly like the others.

## Before handing it back

    make test

The validator sleeps while the sheet is blank and wakes on the first filled
row. It checks that every row carries a status from the vocabulary, that
`present` rows carry a value and non-`present` rows do not, and that the
document and field identifiers still match the extraction schema.

A typo fails there. Uncaught, it would score a correct extraction as wrong.

## Box grading, stage two of this sheet's work

Written 2026-09-01, before any box was graded. Origin: DEFECTS #29, the
provenance boxes do not reliably land on the field they name, and the crop
check that was supposed to show it cropped to the model's own box.

### Setup

    open data/labelset/overlay          # the GRADED_ files are yours
    open data/labelset/extract_grades.xlsx   # or the CSV below

The overlay pages show every extracted value's box drawn in red with a number
beside it; the sidecar `.txt` beside each image lists number, field and the
value the model read. The sheet at `tests/fixtures/box_grades.csv` has one row
per numbered box, in the same numbering, which is generated by the same code
and cannot diverge.

### The four documents

One per era bucket, about 110 boxes, fixed here before grading: record
1493608 (1966, two pages), 1495195 page 15 (1975), 1912687 (1983, the G-1),
and 1495193 page 8 (era unreadable, and a section page). They are ground-truth
documents 3, 7, 14 and 6.

### What to put in each row

`grade`, one of three:

| Value | When |
|---|---|
| `hit` | The box overlaps the written value or its printed field label |
| `near` | It misses, but sits within about one field-row, close enough that your eye finds the value immediately from the box |
| `miss` | Anywhere else |

`handwritten`, `y` or `n`: is the **value** handwritten rather than typed or
printed? This is the split the text-layer analysis needs and cannot produce
for itself.

`note` is free text and not scored.

### The decision rule, fixed before you grade

**DECISION RULE:**

- If `hit + near` is at least **90% overall** and at least **80% in every
  era bucket**, the widened-band presentation is acceptable as the fallback
  tier and region provenance survives, with the measured figure replacing the
  withdrawn sufficiency claim.
- If `miss` exceeds **20% in any bucket**, model boxes are unusable as
  locators in that bucket, and the decision memo weighs snap, label-anchor
  and page-level provenance for it.
- `hit` alone governs nothing, because the band presentation compensates
  `near`.

Rates are reported overall and by era, scalar against table cell, face
against section page, and top against bottom half of the page.

### Same sitting, two leftover disputes

While the whole pages are open: document 2's completion date, which you
called illegible and the model read as `4-19-68`, and document 1's type of
completion, the same shape. Say what the paper shows; the crops could not,
because they showed the wrong region.

## Box grading, stage three: the template probe

Written 2026-09-03, before the template was built and before any box was
drawn. Origin: the mechanism decision left open by the stage-two grading.
Model boxes are not field locators on this paper, and the question is whether
a per-revision template is.

### Why this needs a new sitting rather than a re-score

The 110 grades of stage two record whether **the model's** box landed on the
field it named. They do not record where the field is. On the 1966 document
they are 0 hit, 4 near, 31 miss, so 31 of the 35 carry only the information
that the field is not at that box. A template box cannot be marked correct
against that sheet. The old grades supply the comparator and can falsify a
new box; they cannot confirm one.

### The document, and why only one

Record 1493608, pages 5 and 6, the 1966 bucket. It is the worst bucket
measured and the one the decision turns on. Its 35 boxes are the population.

### The sheet is blinded and shuffled

`tests/fixtures/box_grades_probe.csv`, one row per numbered box, in the same
numbering as the overlay images, generated by the same code so the two cannot
diverge. The stage-two sheet at `tests/fixtures/box_grades.csv` is never
opened or rewritten.

Three sources are mixed into one shuffled sheet and the sheet does not say
which is which:

1. Boxes the template asserts.
2. The 15 boxes the layered join counts as snapped on this document. These
   were never graded by eye: the join assumed they were right because the
   text match was unique. Grading them removes an asymmetry that would
   otherwise flatter the comparator.
3. A held-back handful of already-graded model boxes, as a consistency check
   on the sitting itself.

Grades are unchanged: `hit`, `near`, `miss`, same definitions, `near` still
counts. `handwritten` and `note` unchanged.

### The bar, fixed before the template was built

**DECISION RULE:**

**Population:** the same 35 boxes on record 1493608 that the layered join
scores. Table cells included, so failing to place one counts against the
template exactly as it counts against the join.

**Unit of success:** the template asserts a region for that field on that
page, **and** the grade is `hit` or `near`.

**Comparator:** the layered join at 19 of 35, 54.3%.

**Both conditions must hold.**

1. **At least 26 of 35, that is 74.3%.** Wilson 95% interval
   [57.9%, 85.8%], whose lower bound clears the comparator. The smallest
   count that clears it at all is 25 of 35; the bar asks one box more.
2. **McNemar exact, one-sided, p at or below 0.05.** With b the boxes the
   template gets and the join misses and c the reverse, b is tested against
   Binomial(b + c, 0.5). One-sided because the hypothesis is directional: a
   template that loses is dead either way.

Paired, because at n = 35 the unpaired Wilson interval is about plus or minus
16 points and would call almost nothing. Condition 2 is what forbids a
template that merely swaps which boxes are right: at b - c = 7 it passes with
c of 0 or 1 and fails at c of 2 or more.

### The three zones, and the escape, both elected in advance

| Outcome | Verdict |
|---|---|
| 26 or more of 35, and McNemar p at or below 0.05 | PASS. Templates become the geometry mechanism. |
| 21 or fewer of 35 | DEAD. Recorded in extract.md with its number. No further template work. |
| 22 to 25, or 26 or more without the paired condition | INCONCLUSIVE at this n. The escape below fires. |

**The escape was elected on 2026-09-03, before any number existed:** the
middle zone extends the same blinded grading to the 1975 document's 14 boxes,
for 49 paired boxes, and re-tests **once**. That result is final either way.
Electing it in advance is what stops it becoming a search for a friendlier n.

### Secondary numbers, reported, governing nothing

Registration residual median and p90; matched anchor count; abstention rate;
the scalar-only rate over 24 boxes and the table-only rate over 11; the count
of template regions that coincide with a `miss`-graded model box, which is a
free falsification check; and the re-graded verdict on the join's 15 assumed
snaps.

### Same sitting, the two disputes, on their own sheet

Document 2's completion date and document 1's type of completion stay open
and close in this hour, on a separate sheet. They are a reading question and
this sheet is blinded; folding them together would break the blind.

## Box grading, stage four: does a region land when it is asserted

Written 2026-09-03, before any box was drawn, after the template probe was
already decided DEAD on coverage. This sitting does not reopen that verdict.
It answers the one question the coverage gate could not: **when a mechanism
does assert a region, is the region on the field?**

Two mechanisms are graded and they are judged by different rules, because
they claim different things.

### The 33 boxes

Record 1493608, pages 5 and 6, the same document as stage two.

- **18 template regions**, every box the Rev. 7/5/66 template asserts. 12
  scalars and 6 table cells.
- **15 snap boxes**, the ones the layered join counts as located on this
  document. These have never been graded. The join's 54.3% has rested on the
  assumption that a unique text match is a correct one, and this is the first
  time that assumption is checked by eye.

    make probebox                       # ceiling, and the abstention list
    make probebox ARGS=--sheet          # draw the sheet and the overlays
    open data/labelset/overlay_probe    # the PROBE_ files are yours
    make probebox ARGS=--score          # both rules, after you have graded

Sheet at `tests/fixtures/box_grades_probe.csv`, overlays under
`data/labelset/overlay_probe/`. The answer key sits beside the overlays, is
git-ignored, and is read by the scorer and not by you. Grades unchanged: `hit`, `near`, `miss`,
same definitions as stage two, and `handwritten` and `note` as before.

### How to grade this sitting

Written 2026-09-03, before any grade exists. Stage two's definitions still
govern and are not restated; this covers what stage two does not.

**The loop.** Open both overlay PNGs. Each has a `.txt` sidecar listing
`number  field  value`, and the sheet's `box_num` is that same number. Work
page by page off the image, find the row with that number, fill `grade`.
Order does not matter and the sheet is shuffled on purpose, so do not try to
read a pattern out of the sequence.

**The three grades are stage two's, unchanged:** `hit` if the box overlaps
the written value **or its printed field label**, `near` if it misses but
sits within about one field-row, `miss` anywhere else. Do not apply a
different standard to a big box than to a small one. Some of these regions
are much larger than a stage-two box and the difference is measured and
handled in the reporting below, not by you tightening your eye.

**Grade each box on its own.** Seven fields appear twice, once per mechanism.
They are two independent judgements about two different rectangles. Do not
reconcile them and do not carry your first answer to the second.

**A box that lands on the printed label rather than on the value is still a
`hit`,** because that is what stage two's definition says and the threshold
was pre-registered against that definition. But **write `on label` in the
note** when it happens. For one of the two mechanisms that distinction
matters a great deal and for the other it does not, and the note is what lets
the scorer report it without the threshold having been moved after the fact.
The rule is not being changed here; a second number is being collected
alongside it.

**Checkboxes.** `type_of_completion` and `purpose_of_filing` are option rows.
`hit` if the box covers the ticked option or the option labels. If the region
covers the options but the X itself falls outside it, that is still a `hit`
by the definition, and write `X outside` in the note. Stage two saw one
missed X and it was recorded rather than fixed at n=1; this is how the second
instance would be visible.

**`handwritten`.** Every value on this document is typed, so expect `n`
throughout. Put `y` if you find otherwise; it would be a finding, since the
whole era gradient has been argued on typed print.

**If you cannot tell,** grade your best call and write `unsure` in the note.
Accuracy gets reported with and without noted rows, same as everywhere else
in this protocol.

**Finish the sheet or leave it empty.** The scorer refuses a partly graded
sheet and a tier-2 test fails on one, because a rule applied to 20 of 33
boxes is not the rule that was pre-registered.

### The blinding, and exactly how far it goes

Rows are shuffled and the sheet does not name the mechanism. The field name
and the extracted value are shown, because "does this box land on its field"
is unanswerable without them.

**Two things leak the source and are stated rather than hidden.** A snap box
is a single word box and a template region is a form cell, so they differ in
size systematically. And 7 of the 33 fields appear twice, once from each
mechanism, so a repeated field is visibly a pair. What the blind still buys
is that within a pair, and across the sheet, the grader cannot tell which of
two boxes is the template's. That is the bias the shuffle is for.

### Rule one, the template: hit + near, over 18

**DECISION RULE:**

`near` counts, as it did in stage two, because the region is a locator for a
viewer that zooms to it.

| Outcome | Verdict |
|---|---|
| 14 or more of 18 | The cell rule lands. The template's failure is anchor inventory only, which is the Textract escalation's trigger signature, and the escalation opens for decision. |
| 10 or fewer of 18 | The layout assumption fails too. Textract stays shut permanently on this argument and the template direction is closed rather than parked. |
| 11 to 13 | Inconclusive at this n. Stays shut. No escape. |

14 of 18 is 77.8%, Wilson 95% [54.8%, 91.0%]. At n = 18 the interval is wide
and the instrument is coarse on purpose: it has to separate "mostly lands"
from "mostly misses", not measure a rate.

**Reported beside the pooled verdict, and fixed here before grading: the
scalar rate over 12 and the table-cell rate over 6, separately.** The even-row
band is the one declared guess in the mechanism. Scalars landing while cells
miss is a different finding from a uniform miss, and pooling the two would
hide which of them happened.

### Rule two, the snap tier: hit alone, over 15

**DECISION RULE:**

**`near` is failure for a snap.** The other tiers offer an approximate
locator and say so. A snapped box claims a measured word position, so a box
that sits near the value is a box on the wrong word, and grading it the same
way as a region locator would credit it for the thing it claims not to need.

- **12 or more hits of 15**: the snap tier stands as measured geometry.
- **Fewer than 12**: snap demotes to a disambiguation prior only, it stops
  being a source of asserted geometry pending diagnosis, and the 54.3%
  comparator on this document is restated with the snapped boxes counted at
  their measured hit rate rather than at 100%.

That second branch would move a number this repo has been quoting, which is
why the restatement is written down before the grades exist rather than
argued about afterwards.

### Measured before grading: the six cell bands are too big to be informative

The scalar region rule is capped, at 0.45 of the page in width and 0.075 in
height, specifically so that a mechanism cannot score `hit` by drawing large.
**That cap was never applied to the table-row tier.** Measured on the sheet as
drawn:

| source | n | median area | max |
|---|---|---|---|
| snap word box | 15 | 0.00041 | 0.00067 |
| template scalar | 12 | 0.00466 | 0.01343 |
| template row band | 6 | **0.07505** | **0.14468** |

A row band is 180 times the area of a snap box and 16 times a template
scalar. One of them covers 14% of the page. A `hit` on a region that size is
close to unearned, and pooling those six with the twelve scalars would carry
that into the headline.

This is standing rule 9 arriving on my own work: the residue of the cap was
never characterised, and the tier the cap does not cover is exactly the tier
that needed it.

**SUPERSEDED by the correction below (DEFECTS #31). Kept verbatim, because a
pre-registration that edits out the clause it failed to honour is worth
nothing.**

**The consequence for reading the result, fixed here before grading:** the
twelve-scalar rate is the number that decides the Textract question. The
six-cell rate is reported beside it and is weak evidence in the `hit`
direction whatever it says. The pooled 18 is reported because it was
pre-registered, and it is read with this table beside it.

> **Correction appended 2026-09-03, after grading, DEFECTS #31.** The
> paragraph above is left exactly as it was written. It should not have been
> written. "The twelve-scalar rate is the number that decides" is a second
> decision rule, in a section that was meant to record a measurement caveat,
> and it disagreed with the rule table above when the grades came in: pooled
> 13 of 18 fails, scalars 10 of 12 passes.
>
> **The numbered clause governs. The verdict is the failing one.** The clause
> discarded here is the one that would have opened the AWS escalation. The
> reason for discarding it is not that pooled is the better metric; it is
> that only one of the two ever had a threshold attached, so only one could
> produce a verdict rather than a preference.
>
> Its second claim was also wrong. The six cell bands were predicted to be
> biased toward `hit`. They graded 3 hit, 0 near, 3 miss: worse than the
> scalars and with no middle, because a band covering a seventh of a page
> either contains the value or is nowhere near it. The pooled 13 was not
> inflated by them.
>
> Stages two and three were audited for the same flaw and are clean. Stage
> two goes further and explicitly disclaims a second metric: "`hit` alone
> governs nothing". That is the discipline this stage dropped.
