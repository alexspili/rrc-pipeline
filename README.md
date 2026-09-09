# rrc-pipeline

An extraction pipeline over the Texas Railroad Commission's imaged well records, and a record of
the workflow used to build it with an AI coding agent.

Two things are on offer here and both are measured. The pipeline has extracted its full corpus,
225 documents for $10.42 in model spend, locates 5,271 extracted values on the page images at a
tagged confidence tier, reports accuracy per form era because a single figure would hide a
gradient across the decades of paper, and runs validation rules that fire on errors the archive
actually contains. The workflow layer is the part most repositories leave out: the context file,
the per-module rules, the defect log, and the test tiers that make agent-generated code
reviewable.

One habit runs through both. Most numbers below are quoted next to what they do not cover, some
are reported as provisional, and one finding is not quoted as a number at all because the
measurement behind it will not carry one. Knowing which of your numbers you are allowed to say
out loud is what this repository is for.

## What the pipeline does

The Railroad Commission of Texas keeps an archive of scanned well files: microfilmed paper filed
from the 1950s onward, fetched here through the archive's own JSON API. The pipeline classifies
every page with a small vision model, reassembles multi-page filings whose sheets were scanned
apart, and extracts the two completion report forms, the G-1 (gas) and W-2 (oil), into structured
JSON where every value carries a pointer to the place on the page it was read from. Deterministic
rules then check what a completion report lets you check: API numbers against the county prefix,
dates against each other, depths against the total. The output is browsable in a static
TypeScript viewer that shows each value on the page image at its stated confidence tier. Of those
stages, reassembly is the least settled, and it is reported below with what it cannot reach. The
corpus behind every number below is 202 records, 249 files and 3,689 pages from district 03,
fetched once and cached.

Texas completion data can be licensed from a vendor, so the public archive is not the version of
this problem worth solving. An operator's own file room is: the same microfilm, the same two
forms, the same unreadable mastheads and the same fields repeating across filings for one well,
on documents nobody outside the company has indexed. This repository works that problem on a
public corpus, where the same failure modes show up and every claim can be checked by a reader.

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

**The full corpus has been extracted: 225 of 225 documents, $10.42 in model spend.** The
extractor, asked only to extract, also acted as a second opinion on the classifier: 35 of the
predicted G-1/W-2 faces came back as something else. Three are Form 2 "Well Record"
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
| Rev. 4/1/83 | 108 | 99.1% | 86.3% |
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

**Every extracted value carries a highlight, at a tagged honesty tier, and the tiers were each
graded against a pre-registered bar.** Three tiers ship, strongest first. A word box measured
off the page's own text layer, where the value's text matches uniquely: graded 14 of 15 hits.
A per-revision form template, built once from Textract word geometry pooled across 27 to 40
sample pages per revision and committed as a static artifact, locating the field's printed cell
on any page that registers: the stack it anchors graded 30 and then 32 of 35 boxes located on
the worst-measured 1966 document, against 19 for the stack without it, McNemar p = 0.0017 and
0.0001. And the model's own box as a fallback band, which lands 60.9% of the time overall and
11.4% on 1966 paper, tagged as the weakest thing shown. Over the full corpus the text layer
locates 1,792 of 5,271 extracted values, the templates 744, and the band carries the remaining
2,735. The same template mechanism failed its first gate outright, at 18 of 35 coverage from a
single sample page, and was closed; it reopened only when new product-level evidence met the
closure's own clause, with fresh pre-registered bars, and passed. Both verdicts are in
`docs/modules/extract.md` with the thresholds that were written before the numbers existed.

What that looks like in the viewer. A 2008 W-2 reverse, with the casing record's measured row
regions, every value's tier tag in the sidebar, and a struck-through correction carried rather
than lost:

![The viewer on a 2008 W-2 Section II: casing record rows located by committed template
geometry, tier tags on every value, a struck-through correction preserved](docs/viewer-2008-section-ii.png)

And a 1966 G-1, the worst-measured paper in the corpus, with the click-to-zoom card captioned
by the printed field label and tagged with the tier that located it:

![The viewer on a 1966 G-1: the zoom card shows the operator address located by the text
layer, with the field's printed label as the caption](docs/viewer-1966-g1.png)

You can browse all of this yourself: `make demo` downloads the full viewer bundle, 225
documents, from the repository's release, and it runs with no API keys and no fetch. The pages
are public regulatory filings from the Commission's own freely accessible archive, republished
as the public record prints them; the archive imposes no restriction on them at the source, and
the call to republish rather than gate them is deliberate.

**The validation rules fire on real errors, with no labels involved.** Run over all 225
documents: 157 come back clean and 68 carry at least one finding, 40 errors and 90 warnings
across twelve rules. The commonest error is a depth recorded below the well's own total depth,
18 times. One API number fails its county prefix check, which is the class of error the archive
itself contains: the demo document's G-5 carries an API number with two digits transposed, and
the check catches it.

**Reassembly is the least settled stage and is not carrying a current number.** Pages of one
filing that were scanned apart are attached on identity agreement, and the first verification
sitting judged eight of eighteen attachments against the paper and found five wrong. The reason
is structural rather than a threshold: identity fields describe the *well*, and one file holds
several filings for one well, so two filings agree on operator, lease, well number, district and
completion date because they must. The last full measurement was 25 of 32 multi-page documents
clean, with the wrong ones all same-form, same-well, different-filing. A structural change since
then, that a face holds at most one back and a paper confirmation names which page that is,
regrouped the corpus into 225 documents and corrected three of them; the clean count has not been
re-measured on the new grouping and is not quoted as if it had been. The ceiling is a fact about
the paper: 20 of the 57 candidate pages carry no identity fields at all and can never attach on
any rule. Full working: `docs/modules/reassemble.md`.

## Roads not taken

- **Reading the form number instead of abstaining on it.** A targeted OCR or vision read of the
  top-right corner would recover the illegible slice rather than abstaining on it. Partly
  superseded from the other direction: a page whose masthead cannot be read can now be routed by
  its printed layout instead, registered against the committed templates by residual, and the
  classifier-side abstention fix remains deferred.
- **AWS Textract at runtime.** Textract does run in this project, but only on the developer's
  machine, at build time, to pool template geometry that is then committed to the repository;
  a user of the pipeline still needs exactly one API key. The runtime road stays untaken. The
  history of that line is the most instructive thing in the geometry story: the escalation's
  trigger fired once and a second pre-committed gate refused it by one box; the closure clause
  said reopening required a new measurement and a new gate; five days later it got both and
  passed twice. The clause worked in both directions.
- **An LLM to clean the OCR's garbled words.** Measured before deciding: recovering garbles
  registered 4 additional pages, against a 99-page residue that only template coverage can
  reach, so the inference, the cost and the unmeasured failure mode were declined for the small
  half of the problem.
- **A hosted backend for the viewer.** Rejected on cost, prompt-injection surface and uptime; the
  viewer is static and does no inference.

## How it was built

I wrote this with an AI agent doing most of the typing. That is now common. What follows is the
structure I use to keep the output reviewable, which is less common, and which is the substance
of what I am showing you.

The artifact worth reading is not the code, it is `DEFECTS.md`, because the failures recorded in
it are the ones this way of working produces and ordinary review does not see: an API echoing my
own parameters back and being read as proof it had applied them, provenance boxes that were well
formed and pointed nowhere, abstention rates that looked like integrity and were bugs, and a
value read from the wrong field that scored correct because two boxes happened to agree. Each of
those surfaced because an instrument was built to catch it, and not otherwise.

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

There are 49 numbered rules across 4 module files. A test asserts that every module file carries
both sections and that every rule names its pin, because for a while two files carried neither.
`DEFECTS.md` is the append-only log the origins point back to: 81 entries, of which 5 predate
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
| 1 | Pure functions, no I/O | Save | 475 | 42s |
| 2 | Real boundaries, fixtures | Commit, via the hook | 282 + 28 TS | 52s |
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

This was built in eleven days, 2026-08-29 to 2026-09-08, in 250 commits, unsquashed and in
sequence, because the sequence is the evidence. Reviewing three or four consecutive fix commits
will show the loop running or will show that it does not.

## Measured

All from the repository. Nothing estimated.

- Extraction, shipping prompt, deployed batch path: 89.5% status, 82.4% value equivalent,
  on 405 hand-keyed fields over 15 documents
- Corpus extracted: 225 of 225 documents, $10.42 in model spend
- Highlight tiers over the corpus: 1,792 values on measured word boxes, 744 on committed
  template geometry, 2,735 on the model's band
- Build-time Textract, committed as static templates: 343 page reads, $7.50, zero runtime AWS
- `CLAUDE.md`: 145 lines, budget 145
- Numbered rules: 49 across 4 module files; retired so far: 0
- Logged defects: 81, of which 5 predate the first line of code
- Tests: 475 tier 1, 282 tier 2, 29 tier 3, 28 TypeScript

## What this is not

It is not a framework, and there is nothing here to install. The pattern is four files and a test
layout, and it is worth what it is worth only alongside a codebase that generated the defects.

It is one engineer's practice on one project. I have not tested whether it holds across a team,
and I would treat that as an open question in any conversation about applying it.

## Running it

The fastest path is seeing it. This downloads the viewer bundle from the release (124 MB) and
needs no keys of any kind:

```
make demo
cd viewer && npm install && npm run dev
```

Verifying and reproducing:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install poppler   # pdfimages and pdftotext
make test              # tiers 1 and 2
make eval              # tier 3
make score             # extraction against the hand-keyed truth
```

The raw corpus is not mirrored in the repository; it is fetched from the archive itself with
`fetch.py` against a `NEUBUS_TOKEN` (a public 24-hour token from the archive's own login page,
pasted into `.env`), so a reproduction runs against the same source a reader can check.
Extraction needs `ANTHROPIC_API_KEY`. Re-exporting the viewer bundle from a finished run:
`scripts/export_viewer.py`.

## Contact

Alex Spiliotopoulos
[linkedin.com/in/alexspiliotopoulos](https://www.linkedin.com/in/alexspiliotopoulos/) · [github.com/alexspili](https://github.com/alexspili)
