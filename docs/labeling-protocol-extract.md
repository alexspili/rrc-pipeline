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
