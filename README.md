# rrc-pipeline

An extraction pipeline over the Texas Railroad Commission's imaged well records, and a record of
the workflow used to build it with an AI coding agent.

Two things are on offer here. The pipeline is real software with measured accuracy numbers and
a merge gate. The workflow layer is the part most repositories leave out: the context file, the
per-module rules, the defect log, and the test tiers that make agent-generated code reviewable.

If you are evaluating me for work on AI-assisted engineering practice, the second half is the
part to read.

## What the pipeline does

The Railroad Commission of Texas keeps an archive of scanned well files: microfilmed paper filed
from the 1950s onward, fetched here through the archive's own JSON API. The pipeline classifies
every page with a small vision model, reassembles multi-page filings whose sheets were scanned
apart, and extracts the two completion report forms, the G-1 (gas) and W-2 (oil), into structured
JSON where every value carries a pointer to the place on the page it was read from. Deterministic
rules then check what a completion report lets you check: API numbers against the county prefix,
dates against each other, depths against the total. The output is browsable in a static
TypeScript viewer that shows each value on the page image at its stated confidence tier. The
corpus behind every number below is 202 records, 249 files and 3,689 pages from district 03,
fetched once and cached.

The accuracy numbers come from 405 hand-keyed fields over 15 documents, are reproducible with
`make score`, and are quoted below next to what they do and do not cover.

## Findings so far

Two findings, at two different confidence levels. They are not quoted as if they carried the same
weight, and the weaker one is not quoted as a number at all.

**Verified, record level.** **115 of the 202 records in district 03 (57%) contain a completion
report.** Measured by classifying all 3,689 of that district's pages, above an independent OCR
floor of 68 records, and hand-checked on a seeded random sample of 15 of the 115: 15 of 15
confirmed, no over-counting. This is the number the corpus decision rested on and it is
reportable as it stands.

**Provisional, per form.** The split of those records into G-1 (gas) and W-2 (oil) completion
reports is **not reportable as a count**, and the mechanism is identified rather than guessed at.
A stratified sample of 143 hand-labelled pages puts precision at 64.7% +/- 4.5pp on predicted G-1
faces and 44.0% +/- 5.2pp on predicted W-2 faces. The cause is legibility, not reasoning: all 20
drawn faces whose printed form number could not be read were misclassified, while on pages whose
number the OCR text layer also recovers the classifier was right 16 out of 16. The decided fix is
to abstain on an unreadable page rather than guess, which leaves the verified record-level number
above unchanged. Full working: `docs/modules/classify.md`.

The distance between those two paragraphs is most of what this repository is for.

**The full corpus has been extracted: 223 of 223 documents, $10.17 in model spend.** The
extractor, asked only to extract, also acted as a second opinion on the classifier: 35 of the
223 predicted G-1/W-2 faces came back as something else. Three are Form 2 "Well Record"
filings, the completion report family that predates both forms, classed and kept. The other 32
are other forms, among them 12 cementing reports, 5 plugging records, a transporter
authorization, and 14 documents whose mastheads were rendered and read one by one before any
class was assigned: potential test forms, back pressure tests and similar filings that resemble
completion reports and are not, and the pipeline says so rather than extracting them as if they
were.

**Extraction accuracy is measured on the same request path the corpus run uses.** Scored
against 405 hand-keyed fields over 15 documents, on the prompt that ships, sent through the
Batch API exactly as the full run sends its documents, because a score taken on any other path
describes an instrument rather than the product:

| Status correct | Value equivalent | Recovered |
|---|---|---|
| **89.5%** | 82.4% | 80.1% |

"Recovered" is the strictest of the three: a value exists on the paper and the model has it,
equivalently written.

By form era, spelled as the paper spells them:

| Form era | Fields | Status correct | Value equivalent |
|---|---|---|---|
| Rev. 4/ 1/ 83 | 27 | 100.0% | 87.5% |
| Rev. 4/1/83 | 81 | 98.8% | 86.0% |
| Rev. 6/30/75 | 54 | 72.2% | 89.5% |
| Rev. 7/5/66 | 108 | 85.2% | 85.5% |
| Revision unreadable | 63 | 95.2% | 69.4% |

A single blended figure would hide the thing that matters: the pipeline is close to perfect on
1983 paper and materially worse on the older and less legible paper, and the archive spans those
decades, so an era-blind number describes a corpus nobody has.

The comparison is stated rather than tuned. "Status correct" is agreement on whether a value is
present and, when it is not, on why. "Value equivalent" counts dates as dates and depths as
numbers, so "4-23-75" and "1975-04-23" agree.

**The held-out document is still worth its points.** One of the 15 documents was the one the
schema was designed against, and it was excluded from the headline before the labelling started,
on a rule written down in advance. It scores 96.3% on status against the headline above.
Pre-registration is not a ceremony here; the difference between those numbers is what it bought.

**Era coverage is recovered by the model, not by the text layer.** These are microfilm scans of
paper filed from the 1950s onward, and the form revision printed beside the form number is what
dates a document. The embedded OCR recovers that revision on 62 of 238 completion faces, and every
year it finds is 1983 or later, so sampling on it would systematically over-sample the newest
paper. Reading the page image instead recovers revisions the text layer cannot: on a 20-document
sample, 14 carried a readable revision, including 7 of the 12 documents whose text layer yields no
form number at all, and the years span **1966, 1975 and 1983**. Accuracy is reported per era
bucket rather than blended, and the buckets come from the paper.

**A highlight can be shown for 77.3% of extracted values, and the era gradient is steeper than
the accuracy gradient.** Measured over 562 values in a 20-document run, at two tiers a viewer
renders differently: a word box measured off the page's own text layer, and an approximate band
from the model. On 1983 forms it is 100%; on 1966 forms it is 54.3%. The remaining 22.7% get the
page and the raw text and nothing finer, and that is reported rather than filled in with a guess.
Three mechanisms were measured against this and two were killed by thresholds written before the
numbers existed: the model's own boxes land on the field 60.9% of the time overall and 11.4% on
1966 paper, and per-revision form templates failed a coverage gate at 18 of 35 and a landing gate
at 13 of 18. Over the full corpus, the strict text-layer tier alone locates 1,761 of 5,259
extracted values; the rest carry the model's band at the rates above.

**The validation rules fire on real errors, with no labels involved.** Run over all 223
documents: 173 come back clean and 50 carry at least one finding, 41 errors and 88 warnings
across twelve rules. The commonest error is a depth recorded below the well's own total depth,
19 times. One API number fails its county prefix check, which is the class of error the archive
itself contains: the demo document's G-5 carries an API number with two digits transposed, and
the check catches it.

## Roads not taken

- **Reading the form number instead of abstaining on it.** A targeted OCR or vision read of the
  top-right corner would recover the illegible slice rather than abstaining on it. Deferred: it
  reopens an AWS Textract dependency the pipeline does not currently need, for a gain bounded by
  the illegible share of completion faces, and abstention already handles that slice honestly.
- **AWS Textract for word-level geometry.** It would supply the word
  inventory the form templates lacked. Its trigger condition was written down
  before the measurement that would fire it: open only on anchor poverty or
  garbled labels, never on a layout-assumption failure, which better OCR
  cannot repair. The measurement fired it exactly. A second gate, also
  pre-committed, then refused it by one box. The escalation had a real
  opening and was still not taken, and reopening it now needs a new
  measurement rather than an appeal to that one.
- **A hosted backend for the viewer.** Rejected on cost, prompt-injection surface and uptime; the
  viewer is static and does no inference.

## How it was built

I wrote this with an AI agent doing most of the typing. That is now common. What follows is the
structure I use to keep the output reviewable, which is less common, and which is the substance
of what I am showing you.

### CLAUDE.md is an index, not a manual

`CLAUDE.md` holds a stated budget of 145 lines and sits at exactly 145. The budget started at
120; it was raised once, and the file itself records when, by whom and for what, because the
standing rule is to move content out rather than raise the ceiling, and an exception with no
recorded reason is how ceilings die. It carries the project description, the current state at a
few lines per milestone, the standing rules, and pointers into `docs/modules/` where the detail
lives. The budget exists because a context file that grows with the codebase stops being read,
by the agent and by people.

### Rules come from defects, and carry their origin

Each file in `docs/modules/` carries a numbered rule section and a `RETIRED` section. A rule
names the defect that produced it and the test that pins it, verbatim from the repository:

```
R1. A page whose aspect ratio exceeds 2.0 is never extraction-eligible.
    Origin: DEFECTS #1. A long-edge downscale crushes the short edge of a
    fold-out; the widest page in the corpus (11,264 x 3,040, record 1495350)
    lands at a 423px short edge under the 1568 cap. Classification still runs
    on a squashed thumbnail, which is adequate for "this is a plat".
    Pinned by: tests/tier1/test_pageclass.py::test_oversize_page_is_never_extraction_eligible
```

There are 48 numbered rules across 4 module files. A test asserts that every module file carries
both sections and that every rule names its pin, because for a while two files carried neither.
`DEFECTS.md` is the append-only log the origins point back to: 74 entries, of which 5 predate
the first line of code, and several record the same mistake being made twice by the same author
on the same day, which is what the log is for.

### Rules are retired by making them unrepresentable

A rule is a weaker fix than a type. Each module file has a `RETIRED` section for rules removed
because the invariant moved into a constructor or a type signature, with the commit that did it.
The count today is zero, and that is reported rather than rounded up: six rules are already
enforced by constructors and move to `RETIRED` once no other code path can build the object any
other way. The mechanism, not the count, is the claim.

### Three test tiers, each with a trigger and a measured cost

| Tier | Scope | Runs on | Tests | Measured |
|---|---|---|---|---|
| 1 | Pure functions, no I/O | Save | 419 | 42s |
| 2 | Real boundaries, fixtures | Commit, via the hook | 262 + 23 TS | 54s |
| 3 | Eval harness on labeled data | Merge, `make eval` | 29 | under 1s |

The split exists so the agent has a fast signal to iterate against and a slow one it cannot
iterate against. Tier 3 gates the merge and is the only tier that reads the labelled data.

The working rule is that a bug fix opens with a failing regression test, committed red with the
override flag and the reason in the message, then the fix. The commit history shows this in
order, which is the only way to check it.

### The commit habit turned out to be the backup

A generator in this repo rewrites a labelling template at the end of every run. The run was
repeated after the sheet had been keyed by hand, and it replaced 405 hand-keyed rows with blanks.

They came back with one `git checkout`, because the labels had been committed as their own change
the moment they validated, before anything else was touched. Nothing else was tangled up in that
commit, so recovery was one command rather than an afternoon.

The habit exists for reviewability: small commits in sequence are how somebody checks that the
failing test really did come before the fix. That it also functions as a backup is not why it is
there, and is the sort of thing you only find out once. The defect log records it, and the
generator now refuses to overwrite a sheet that has any filled row rather than warning about it.

### A pre-registration with two rules in it has already failed

I wrote a decision rule before a measurement: a mechanism passes at 14 of 18
graded boxes. Later the same day, while writing up a caveat about how to read
one of the numbers, I wrote a sentence saying a different figure was the one
that decided. I did not notice I had written a second decision rule. Both
went in before any grading happened.

The grades split them. On the rule with a threshold the mechanism scored 13
and failed. On the sentence in the caveat it scored 10 of 12 and passed, and
passing would have opened a cloud dependency I had spent two sessions
arguing against adding.

The numbered rule governs, so the answer is the failing one. Not because it
is the better metric, which I do not know, but because it was the only one of
the two with a number attached, so it was the only one that could produce a
verdict rather than a preference. Picking the other one after seeing which
way each fell is the whole of what pre-registration exists to stop.

The offending paragraph is still in the protocol, verbatim, with a correction
under it. Deleting it would have made the record tidier and worth less. The
part that is now enforced rather than intended: each grading stage carries
exactly one clause marked as its decision rule, and a test counts them, so
the next second rule is a build failure instead of a discovery made at the
worst possible moment.

## What the history shows

This was built in ten days, 2026-08-29 to 2026-09-07, in 217 commits, unsquashed and in
sequence, because the sequence is the evidence. Reviewing three or four consecutive fix commits
will show the loop running or will show that it does not.

## Measured

All from the repository. Nothing estimated.

- Extraction, shipping prompt, deployed batch path: 89.5% status, 82.4% value equivalent,
  on 405 hand-keyed fields over 15 documents
- Corpus extracted: 223 of 223 documents, $10.17 in model spend
- `CLAUDE.md`: 145 lines, budget 145
- Numbered rules: 48 across 4 module files; retired so far: 0
- Logged defects: 74, of which 5 predate the first line of code
- Tests: 419 tier 1, 262 tier 2, 29 tier 3, 23 TypeScript

## What this is not

It is not a framework, and there is nothing here to install. The pattern is four files and a test
layout, and it is worth what it is worth only alongside a codebase that generated the defects.

It is one engineer's practice on one project. I have not tested whether it holds across a team,
and I would treat that as an open question in any conversation about applying it.

## Running it

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install poppler   # pdfimages and pdftotext
make test              # tiers 1 and 2
make eval              # tier 3
make score             # extraction against the hand-keyed truth
```

The corpus is not in the repository: the raw records carry personal information and are fetched
with `fetch.py` against a `NEUBUS_TOKEN` (a public 24-hour token from the archive's own login
page, pasted into `.env`). Extraction needs `ANTHROPIC_API_KEY`. The viewer runs on the exported
bundle: `scripts/export_viewer.py`, then `cd viewer && npm install && npm run dev`.

## Contact

Alex Spiliotopoulos
[email] · [linkedin.com/in/alexspiliotopoulos] · github.com/alexspili
