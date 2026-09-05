# Measurement protocol, reassembly

Written 2026-09-03, before the identity reader exists and before any page has
been grouped. The threshold it fixes is already in the code as
`MIN_AGREEMENTS = 2`. Whether it stays there is settled by the rule below
and by nothing else in this file.

## What is being measured, and what is not

Not accuracy of extraction. Whether **the pages this module groups together
are the pages that belong together**, and whether the ones it declines to
group are ones a human agrees should be declined.

The anti-goal from docs/modules/reassemble.md is the frame for every number
here: **it must not improve by attaching more pages.** A wrong
attachment puts one well's casing record under another well's identity, and
every downstream check would then validate a document that never existed. So
the count of unattached pages is reported output and is never a number to
drive down.

## The evidence

Two sets, and they answer different questions. They are never blended.

**The fifteen ground-truth documents.** Their page composition is known,
including the three that DEFECTS #25 found are sections separated from their
faces: documents 6, 8 and 9, records 1495193 page 8 and 1495195 pages 6 and
38. Those three are the read-out cases. A forward-only heuristic put each of
them with the wrong face, so they are the specific thing this module exists
to get right, and they are graded individually and named in the result.

**The five worked cases** in docs/modules/reassemble.md: records 1493495,
1495193, 1760703, 1511465 and 1495195. They were chosen while the design was
written, from the paper, for the shapes they carry: a clean positive, a
section preceding its face, three reports in one file, three faces with a
section between two of them, and one file supplying three documents.

## DECISION RULE:

**Amended 2026-09-03, before any measurement ran.** The amendment is recorded
as DEFECTS #35 and the superseded text is kept below rather than deleted.

The rule is **two-sided**. Precision alone cannot choose a threshold, because
a module that attaches nothing is wrong about nothing and passes at any
strictness. So the measurement names the pairings that must be made as well
as the ones that must not.

### Must-attach: pages known to belong together

Each is graded individually and named in the result. Evidence grade is stated
because it changes what a failure means.

| Case | Pairing | Evidence |
|---|---|---|
| A | record 1493495, page 10 attaches to page 9 | **Confirmed.** The worked case: a W-2 face and its Section II agreeing on operator (Sun Oil Company), lease (State Tract 130) and completion date (9-22-77) |
| B | record 1495193, page 8 attaches to page 7 | **Confirmed, and re-confirmed off the paper 2026-09-03:** page 8 is headed SECTION II, carries no form number in the top right, and is the second page of the W-2 on page 7. The census called it a `g1` face |
| C | record 1495195, page 6 attaches to the face before it | **Probable.** Recorded in the labelling protocol as "almost certainly", not read off the paper as a pairing |
| D | record 1495195, page 38 attaches to the face before it | **Probable.** Same |

### Must-not-attach

| Case | Requirement |
|---|---|
| E | record 1495193, page 8 must **not** attach to page 9. **VACUOUS, annotated 2026-09-03, DEFECTS #41:** page 9 is a W-12, which this module treats as neither a face nor a candidate, so it was never in the running and this case cannot fail. It passed twice and carried no information. Kept rather than deleted, and no longer counted as evidence. A replacement needs two pages the module genuinely could join that are known not to belong together, and finding one needs the paper |
| F | no page anywhere in either set attaches to a face it does not belong to |

### What each failure means, and it is not the same response

**A wrong attachment (E or F fails).** One is enough; it is the module's
anti-goal and is never traded against coverage. Response: the threshold
tightens to 3 and both sets are re-measured **once**.

**A confirmed must-attach fails (A or B).** Tightening cannot fix this and
would make it worse, so the threshold does not move. Response: the identity
fields on that page are inspected, and the outcome is one of two findings,
both reported rather than tuned around. Either the identity reader did not
read fields that are on the page, which is a reader problem, or the page
genuinely does not carry two agreeing fields, which means **the identity
fields on section pages do not carry enough signal and the module is reported
as such**.

> **Recorded 2026-09-03, after the first measurement: the list above was
> wrong.** Case B failed, and the cause was neither of the two explanations
> this rule names. The module was never offering the page as a candidate,
> because the classifier had labelled it a face and the module took that as
> fact (DEFECTS #37). Nothing about the reader, and nothing about how many
> fields the page carries.
>
> Kept rather than corrected, because the failure is instructive: **a rule
> that enumerates the explanations it expects can be wrong about the list**,
> and the response to that is to inspect rather than to pick the nearest
> listed option. Had the two options been treated as exhaustive, the real
> cause would have been recorded as one of them.

**A probable must-attach fails (C or D).** This decides nothing on its own.
It is a prompt to read the paper for that record, because the pairing was
recorded as "almost certainly" and has never been confirmed. A failure here
is as likely to be a wrong assumption in the protocol as a wrong answer from
the module.

**Both a wrong attachment and a missed confirmed pairing.** The threshold is
not the problem. Reported as such, and neither number is quoted without the
other.

Coverage on the rest of the corpus is reported and decides nothing. That is
about the pages with no known answer, and it is the only thing that sentence
was ever entitled to mean.

> **SUPERSEDED 2026-09-03, before any measurement, DEFECTS #35. Kept verbatim
> because a pre-registration that edits out the clause it failed to honour is
> worth nothing.**
>
> The original rule read: the threshold stays at 2 unless it attaches a page
> to the wrong face, or it fails to attach two or more of the three DEFECTS
> #25 read-out cases; if either fires, the threshold moves to 3.
>
> It then said: "Coverage is reported and decides nothing. A run that
> attaches nothing and is wrong about nothing is a legitimate outcome of this
> rule, and would be a real finding about the paper rather than a failure of
> the code."
>
> Those two cannot both hold. A run that attaches nothing fails the second
> bullet. And the single response of tightening to 3 was written for two
> failures pointing in opposite directions: tightening answers a wrong
> attachment and makes a missed pairing worse.

## The contradicted-but-agreeing list

**Required output, read before the semantics are called settled.**

`pipeline.reassemble.contradicted_but_agreeing` returns every pair the veto
rejected while two or more other fields agreed. Each row is one of two
things, and they look identical from inside the code:

- the veto doing its job, two genuinely different wells that happen to share
  a lease name and a district; or
- **one document split apart** because a typist wrote "Sun Oil Company" on
  the face and "Sun Oil Co" on the section.

Only the paper separates them. So the list is printed in full, with the
disagreeing field named, and read by eye before exact-after-normalising is
called settled.

The approved reasoning for exact matching is a physical claim: a face and its
section were typed by the same person in one sitting, so variance within a
document should be rare. **This list is the test of that claim.** If it is
long and mostly abbreviation variance, the claim is wrong and the veto
semantics need revisiting. If it is short, the claim holds.

Whatever it shows, fuzzy matching stays out. Cross-document name drift is the
disagreement detector's job, and it is a separate cut-order step with its own
evidence.

## What gets reported

Both sets separately, never blended:

- pages attached, and of those, how many to the right face
- pages unattached, split by reason: `no_face`, `below_threshold`, `tie`,
  `contradicted`
- the three DEFECTS #25 read-out cases, named individually with their outcome
- the contradicted-but-agreeing list in full
- the evidence behind each attachment, which fields agreed

## Cost, and what is gated

The identity reader is a model call over roughly 274 candidate pages. That
run is **gated** and does not happen under this protocol. It lands together
with the full extraction run as one spend decision, after reassembly has
passed the measurement above on the ground-truth set.

A probe of two or three pages, approved 2026-09-03, exists only to replace an
estimated per-page cost with a measured one.

## Predictions for run 3, committed before it ran

The prompt changed twice: it now tells the reader that a Section II prints the
lease name inside field 32, and it asks for `found_in` on every present value
(DEFECTS #40, #42). Both invalidate the cache, so all 123 pages are read
again.

Written down first so the run tests a prediction rather than producing one.
**All four are reported afterwards, including the ones that miss.**

1. Record 1493495 page 10 returns `lease_name` as `State Tract 130`.
2. **Case A attaches to page 9 again**, this time on two fields that are what
   they claim to be rather than on a date taken from the wrong box.
3. Case B still passes.
4. **Attachments rise from 14.**

Prediction 4 is the one most likely to miss and is written that way on
purpose. The last run's numbers moved in two directions at once, and a
prompt that is stricter about provenance can easily cost more values than the
one new field recovers.

### What `found_in` is for, and what it is not

It records the printed label the reader says it took each value from. It makes
a wrong-field read **checkable**. It does not make it checked, and it is a
claim by the model about its own reading, exactly as the provenance boxes
were. It is never evidence on its own.

A handful get spot-checked against the paper in the next eyeball sitting.
Deterministic impossible-source flags are welcome later if they turn out to be
free; no infrastructure is being built for them now.

## The verification sitting, and it gates the corpus spend

Written 2026-09-03, before the sample was drawn. One sitting, three parts, one
decision rule.

### Why this sitting exists

Reassembly made 18 attachments on the ground-truth records. **Only 2 of them
can be checked against anything.** The other 16 are on records with no ground
truth, so the strongest claim available is "no known wrong attachment", and
that claim rests on a sample of two.

The module's stated anti-goal is that it must not improve by attaching more
pages, because a wrong attachment puts one well's casing record under another
well's identity and every downstream check would then validate a document
that never existed. A run over the whole corpus would multiply that by
roughly five. So the corpus spend waits on somebody looking at the paper.

### Part A: eight attachments, verified as pairs

**The sample, fixed here before it was drawn.** Eight of the eighteen:

- the **2 that ground truth covers**, so the sitting can be compared against
  something already known;
- the **2 flagged as highest risk** in the run-2 write-up, record 1495195
  pages 52 and 87, and pages 89 and 114, which agree on all five fields while
  sitting 35 and 25 pages apart;
- **4 drawn at random** from the remaining 14, seed 20260903.

The two risk picks are deliberate over-sampling of the cases most likely to
fail. That biases the sitting **against** the module, which is the safe
direction for a check that unlocks a spend.

**What you decide for each pair:** are these two pages part of the same
completion report? Yes, no, or cannot tell from the paper.

### Part B: found_in spot-checks

For the pages in Part A, the reader states which printed box each value came
from. Check a handful against the page.

`found_in` is a claim by the model about its own reading, exactly as the
provenance boxes were, and it is no more self-verifying than they were. It is
not evidence on its own and its rate is not a gate. It is here because a value
taken from the wrong box is invisible whenever the two boxes agree, and this
is the only way to find out whether that is still happening.

### Part C: the contradicted-but-agreeing list

Eight pairs, plus the Crawford/Triolo pair from record 1493399, which is not
in the ground-truth set and is carried here because it was the first case
ever flagged and has never been resolved.

Each row is either the veto working, two genuinely different wells that share
a lease, or one document split by an abbreviation. They look identical from
inside the code. This part decides nothing on its own; it is what tells us
whether exact-after-normalising is holding up before it meets 274 pages.

## DECISION RULE:

**All eight Part A pairs must verify.**

A pair fails if you judge the two pages are not one report, **or** if a
`found_in` check shows a value the attachment depended on came from the wrong
box. Those are two ways to be wrong about the same thing: the attachment was
made on evidence that was not what it claimed.

- **Eight of eight verify:** the full identity run and the full extraction run
  unlock together, as one batched spend decision, and reassembly is closed at
  ground-truth scale.
- **Any pair fails:** no corpus spend. The failure pattern is analysed and
  brought back before anything is run.

"Cannot tell from the paper" is not a pass. It is recorded as its own outcome
and counted as a failure for the purpose of this gate, because the gate exists
to convert an unchecked claim into a checked one, and a pair nobody can read
stays unchecked.

Parts B and C are reported and inform what happens next. **Neither is a
second decision clause.** That distinction is written down explicitly because
this protocol has already been amended once for containing two rules that
could disagree (DEFECTS #35), and again because a caveat section elsewhere
grew a verdict nobody meant to write (DEFECTS #31).

## The extension, and the third sitting. Written 2026-09-04 before reading

**Why this exists.** After two sittings the module makes seven attachments and
Alex has judged all seven. Its score of 13 of 15 across both sittings is
**entirely development data**: the rule that produces it was derived from the
second sitting. There is no held-out pair left to test it on, and the sample
that would test it needs reading records nobody has read, which is the spend
this gate exists to authorise. That is circular, and the circle is broken by
enlarging the measurement set rather than by running the corpus.

**This is not the corpus run.** It is 20 records, 56 pages, $0.41. The corpus
run remains gated behind this sitting.

### The draw, fixed before the pages were read

89 records hold a completion face and have not been read. **20 were drawn at
random under seed 20260904**, before any of them was looked at:

    1493450 1493524 1493639 1494015 1494023 1494028 1494058 1494408
    1494459 1494722 1494811 1496799 1501720 1509403 1512952 1513275
    1774674 1865660 2306415 2345595

They contain 36 completion faces over 56 readable pages.

**Every attachment on these records is fresh by construction.** No page of any
of them has been judged, so nothing here can be contaminated by a rule derived
from the earlier sittings.

### DECISION RULE:

Every attachment the module makes on these 20 records is judged, up to **10**.
If it makes more than 10, ten are drawn at random under seed 20260904 and the
total is reported. If it makes none, that is reported as the result: a module
that attaches nothing on twenty fresh records is a finding about the paper.

**All judged pairs must verify** — the two pages are one completion report,
and no value the attachment depended on came from the wrong box.
`cannot-tell` counts as a failure.

Two regression conditions travel with it, reported and not traded: the five
pairs judged correct across the first two sittings must still attach, and
pre-registered cases A and B must still pass.

**All verify, and both regressions hold:** the full identity run and the full
extraction run unlock together as one batched spend decision.
**Anything else:** no corpus spend, and the failure pattern comes back first.

### What this cannot fix

The known limitation stays known. A W-2 section attaching to a G-1 face is not
closed and is not expected to be: closing it needs a form-family rule keyed to
a classifier label that is wrong on the very pin this module exists for
(DEFECTS #46). If the same shape appears among these twenty it is counted as a
failure like any other, because a limitation being documented does not make an
attachment right.

---

## The fourth sitting: the whole held-out population. Written 2026-09-05
## before any of the twenty-one was looked at

**Why this exists, and why it could not have existed before.** After three
sittings the module made seven attachments and Alex had judged all seven. The
pool was empty. DEFECTS #46 is the reason that mattered: the rules scored 7 of
8 on the pairs they were built from and 2 of 7 on fresh pairs, so a number from
already-judged data tells us nothing about a corpus run.

The corpus identity read changed that. Run over 141 records instead of 19, the
module builds 218 documents, of which **32 have more than one page**. Eleven of
those 32 have been judged in the earlier sittings. **Twenty-one have not, and
twenty of the twenty-one are in records that were never used to build any rule
in this module.** That is a real held-out population, and it is the first one
available.

### The draw: there is no draw

**All 21 unjudged attachments are judged.** No sample, no seed, no exclusion.

This is deliberate and it is cheaper than it sounds. The whole population of
multi-page documents is 32. Judging the remaining 21 makes the module's
attachment precision on this corpus a **counted fact rather than an estimate**:
no sampling error, no interval, nothing to argue about in an interview. A
sample of eight out of twenty-one would buy a wider uncertainty for less of
Alex's time, and the time saved is not the scarce thing here.

The population does not grow unless the module changes. This is the cheap
moment and it does not come again.

### What counts as verified

A pair verifies when **both** hold:

- the two pages are one completion report, judged from the paper; and
- no value the attachment depended on came from the wrong printed box.

Both are on the sheet, as in the third sitting: each row carries the fields
that agreed, the printed box the reader says each value came from, and the
received stamps of both pages.

`cannot-tell` counts as a failure. That biases the sitting against the module,
which is the safe direction.

### DECISION RULE: nineteen or more of the twenty-one must verify

There is one clause and it is this one. Nothing else in this section can
change the outcome.

**19, 20 or 21 verified** — the corpus extraction run goes ahead with the
documents grouped as the module grouped them.

**18 or fewer** — the corpus extraction run goes ahead **face-only**: 218
one-page documents, no attachments, and the attachment mechanism does not ship
until it has been diagnosed and re-verified against evidence that does not
exist yet. **This escape is elected now**, so nothing is chosen after the
numbers are seen.

**Why nineteen.** 19 of 21 is 90.5%. At 90% precision, with 32 multi-page
documents in the corpus, roughly three documents put one well's casing record
under another well's identity — and a corrupted document is worse than a
missing page, because it looks complete and every downstream check then
validates a document that never existed. The last fresh-data reading, after the
three fixes, was 6 of 6.

**Why the escape is face-only and not a stricter threshold.** The obvious
middle path is to keep only attachments resting on three or more agreeing
fields. Checked before writing this rule: **37 of the 39 attached pages rest on
exactly two fields**, so that path removes 37 of 39 and is face-only wearing a
disguise. Writing it in as a distinct outcome would have been DEFECTS #41
again, a pre-registered branch that cannot do anything. There is no graded
middle here, so this rule does not pretend there is one.

**The escape is not "no spend".** Face-only extraction is 218 one-page
documents and still runs. What it gives up is the casing, depth and completion
tables that live on the reverse side, on the 32 documents that have one.

### Regression conditions: reported, never traded

- The eleven attachments already judged must still be as judged.
- The pre-registered pins hold: A (1493495 p10 to p9) and B (1495193 p8 to p7)
  attach; E (1495193 p8 must not attach to p9) does not.

These are reported alongside the count. They do not enter the arithmetic and
they cannot rescue a failing count.

### What a failure teaches, and what it may not do

A pair judged wrong may reveal a mechanism nobody has seen — a form-family
crossing, a new box-label pattern, something else. **That gets a defect entry
and a failing test, and it does not change this sitting's arithmetic.** Origin:
DEFECTS #31 and #35, where a pre-registration carried two decision clauses and
the second one was available to rescue the first. One clause. It is above.

### What this sitting cannot establish

It measures **precision**: of the attachments made, how many are right. It says
nothing about **recall**: how many real face-and-back pairs the module never
attached. 271 pages went unattached, 114 of them because no face was available
in the file at all. Whether those are correct abstentions is a separate
question needing a separate sample, and it is not asked here.

### CORRECTION, 2026-09-05, before the sheet was keyed and before any verdict

**The unit was wrong and the count with it.** The rule above says twenty-one,
counted from the 32 multi-page documents of which 11 were already judged. But
the thing a person actually judges is a **pair**: one face and one page
attached to it. A document with six pages holds five such pairs, and each is a
separate judgement.

Counted as pairs: **39 attached pages corpus-wide, 13 already judged in the
earlier sittings, 26 on this sheet.**

**What changes and what does not.** The standard does not move. The rule above
sets it as a rate and gives the reasoning: below about 90% precision, roughly
three documents in the corpus put one well's casing record under another
well's identity. Translated to 26 pairs, the smallest count meeting that rate
is **24 of 26** (92.3%); 23 of 26 is 88.5% and falls below it.

**DECISION RULE, restated in the right unit and superseding the count above:
twenty-four or more of the twenty-six pairs must verify.** Everything else
stands unchanged: one clause, `cannot-tell` is a failure, and the escape at 23
or fewer is face-only extraction, elected in advance.

**This correction was made before a single verdict was read.** What changed is
arithmetic that was wrong when written, not a bar adjusted to fit an outcome.
The original wording is left above rather than edited, on the same reasoning as
the SUPERSEDED block in the extraction protocol: the mistake is part of the
record.

### Two predictions, committed before the sitting

Building the sheet made two structural facts visible. Neither is a verdict, and
neither may change the rule, but writing down what I expect before Alex reads
the paper is the only way these can count as evidence afterwards.

1. **Record 1493451, file 0: five pages attach to one face, p10**, every one of
   them joined on `operator_name` and `total_depth` rather than on the lease
   name. That is the shape of the DEFECTS #43 failure — one well, several
   filings — and a total depth agreeing is a weak signal because a well has one.
   **I expect most of these five to be wrong.** If they are, they are 5 of the
   26 on their own and the sitting fails on this record alone.

2. **Record 1493399, file 0: two pages, p13 and p42, attach to the same face
   p41**, twenty-nine pages apart in the same file. **I expect at least one of
   those two to be wrong**, because a file this large holds several filings and
   physical distance is not something the module looks at.

If both predictions hold, the module fails this sitting at 20 or 21 of 26 and
the elected escape fires. If they do not hold, that is a stronger result than
the count alone, because it was called in advance.
