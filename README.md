# rrc-pipeline

An extraction pipeline over the Texas Railroad Commission's imaged well records, and a record of
the workflow used to build it with an AI coding agent.

Two things are on offer here. The pipeline is real software with a measured accuracy number and
a merge gate. The workflow layer is the part most repositories leave out: the context file, the
per-module rules, the defect log, and the test tiers that make agent-generated code reviewable.

If you are evaluating me for work on AI-assisted engineering practice, the second half is the
part to read.

## What the pipeline does

[One paragraph. What goes in, what comes out, what it is for. Name the data source and the
record type. Keep it to five sentences.]

Current accuracy on the held-out set: **[N]%** per-field exact match across [N] labeled
documents. The number comes from `bench/`, is reproducible with `make eval`, and is printed on
every pull request.

## Findings so far

Two findings, at two different confidence levels. They are not quoted as if they carried the same
weight, and the weaker one is not quoted as a number at all.

**Verified, record level.** **115 of the 202 records in district 03 (57%) contain a completion
report.** Measured by classifying all 3,689 of that district's pages, above an independent OCR floor of 68 records, and hand-checked on a
seeded random sample of 15 of the 115: 15 of 15 confirmed, no over-counting. This is the number
the corpus decision rested on and it is reportable as it stands.

**Provisional, per form.** The split of those records into G-1 (gas) and W-2 (oil) completion
reports is **not reportable as a count**, and the mechanism is identified rather than guessed at.
A stratified sample of 143 hand-labelled pages puts precision at 64.7% +/- 4.5pp on predicted G-1
faces and 44.0% +/- 5.2pp on predicted W-2 faces. The cause is legibility, not reasoning: all 20
drawn faces whose printed form number could not be read were misclassified, while on pages whose
number the OCR text layer also recovers the classifier was right 16 out of 16. The decided fix is
to abstain on an unreadable page rather than guess, which leaves the verified record-level number
above unchanged. Full working: `docs/modules/classify.md`.

The distance between those two paragraphs is most of what this repository is for.

**Extraction accuracy is reported by form revision, never blended.** The first
measured run, scored against 405 hand-keyed fields over 15 documents:

| Form revision | Fields | Status correct | Value correct |
|---|---|---|---|
| Rev. 4/1/83 | 108 | 100% | 86% |
| Rev. 6/30/75 | 54 | 78% | 90% |
| Rev. 7/5/66 | 108 | 77% | 86% |
| Revision unreadable | 63 | 92% | 65% |

A single blended figure would read 87% and would hide the thing that matters: the
pipeline is close to perfect on 1983 paper and materially worse on 1966 and 1975
paper, and worse again on the documents too degraded to date. The archive spans
those decades, so an era-blind accuracy number describes a corpus nobody has.

The comparison is stated rather than tuned. "Status correct" is agreement on
whether a value is present and, when it is not, on why; on whether a value is
simply there, agreement is 98%. "Value correct" counts dates as dates and depths
as numbers.

**The held-out document was worth fifteen points.** One of the 15 documents was
the one the schema was designed against, and it was excluded from the headline
before the labelling started, on a rule written down in advance. It scores 96%
against the headline's 81%. Pre-registration is not a ceremony here; the
difference between those two numbers is what it bought.

**Era coverage is recovered by the model, not by the text layer.** These are microfilm scans of
paper filed from the 1950s onward, and the form revision printed beside the form number is what
dates a document. The embedded OCR recovers that revision on 62 of 238 completion faces, and every
year it finds is 1983 or later, so sampling on it would systematically over-sample the newest
paper. Reading the page image instead recovers revisions the text layer cannot: on a 20-document
sample, 14 carried a readable revision, including 7 of the 12 documents whose text layer yields no
form number at all, and the years span **1966, 1975 and 1983**. Accuracy is reported per era
bucket rather than blended, and the buckets come from the paper.

**A highlight can be shown for 77.3% of extracted values, and the era
gradient is steeper than the accuracy gradient.** Measured over 562 values in
a 20-document run, at two tiers a viewer renders differently: a word box
measured off the page's own text layer, and an approximate band from the
model. On 1983 forms it is 100%; on 1966 forms it is 54.3%. The remaining
22.7% get the page and the raw text and nothing finer, and that is reported
rather than filled in with a guess. Three mechanisms were measured against
this and two were killed by thresholds written before the numbers existed:
the model's own boxes land on the field 60.9% of the time overall and 11.4%
on 1966 paper, and per-revision form templates failed a coverage gate at 18
of 35 and a landing gate at 13 of 18.

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

### CONTEXT.md is an index, not a manual

`CONTEXT.md` holds a stated budget of [N] lines and has stayed within it since [date]. It carries
the system description, the module map at one line per module, the invariants that hold across
module boundaries, and pointers into `docs/modules/`.

Detail lives in the per-module files. The budget exists because a context file that grows with the
codebase stops being read, by the agent and by people. Line count over time is in
`docs/metrics/context-size.md`.

### Rules come from defects, and carry their origin

Each file in `docs/modules/` carries a numbered rule section and a `RETIRED` section. Every rule
names the defect that produced it and the test that pins it, and a test asserts that all three of
those claims are true of every module file, because for a while two of them were not:

```
R4. Never construct a FieldResult without a source span.
    Origin: 2026-09-14, the agent returned confidence 0.9 on a field it had
    fabricated. With no span there was no way to check the claim.
    Pinned by: tests/tier1/test_field_result.py::test_span_required
```

There are [N] active rules across [N] modules. Every one has a defect behind it. `DEFECTS.md` is
the append-only log those origins point back to, and it includes the cases that produced no rule.

### Rules are retired by making them unrepresentable

A rule is a weaker fix than a type. Each module file has a `RETIRED` section listing rules removed
because the invariant moved into a constructor or a type signature, with the commit that did it.
[N] of [N] rules written have been retired this way.

The retirements are the part I would most want to talk through in an interview.

### Three test tiers, each with a trigger and a time budget

| Tier | Scope | Runs on | Budget |
|---|---|---|---|
| 1 | Pure functions, no I/O | Save | [N]s |
| 2 | Real boundaries, fixtures | Commit | [N]s |
| 3 | Eval harness on labeled data | Pull request | [N]m |

The split exists so the agent has a fast signal to iterate against and a slow one it cannot
iterate against. Tier 3 gates the merge and is the only tier that sees the held-out set.

The working rule is that a bug fix opens with a failing regression test. The commit history shows
this in order, which is the only way to check it.

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

This was built over [N] weeks of intermittent work. The commits are unsquashed and in sequence
because the sequence is the evidence. Reviewing three or four consecutive fix commits will show
the loop running or will show that it does not.

## Measured

All from the repository. Nothing estimated.

- Per-field extraction accuracy: [N]%, on [N] held-out documents
- `CONTEXT.md`: [N] lines, budget [N]
- Active rules: [N] across [N] modules. Retired: [N]
- Logged AI-authored defects: [N]
- Tests: [N] across three tiers

## What this is not

It is not a framework, and there is nothing here to install. The pattern is four files and a test
layout, and it is worth what it is worth only alongside a codebase that generated the defects.

It is one engineer's practice on one project. I have not tested whether it holds across a team,
and I would treat that as an open question in any conversation about applying it.

## Running it

```
make install
make test        # tiers 1 and 2
make eval        # tier 3, prints the accuracy table
```

[Any credentials or data download step goes here.]

## Contact

Alex Spiliotopoulos
[email] · [linkedin.com/in/alexspiliotopoulos] · github.com/alexspili
