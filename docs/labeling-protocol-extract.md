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

**`blank` and `not_on_this_form` are different facts and must never be
mixed.** A 1975 Form W-2 has no API number field anywhere on it; that is
`not_on_this_form`. A 1983 Form G-1 has an API number box that somebody left
empty; that is `blank`. Scoring that conflates them measures nothing, and this
distinction is the reason the schema has a status enum at all.

The test is simple: **is there a printed box or label for this field on the
paper?** If there is no label, it is `not_on_this_form`, whatever you know
about wells.

`illegible` is for ink you cannot read, not for a field you find confusing.
These are microfilm scans and some of them are bad; say so rather than
guessing.

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
If a G-1 document in front of you has no completion-and-casing section on any
of its pages, these ten fields are `not_on_this_form`, not `blank`. Judge it
from the paper, not from this paragraph.

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
