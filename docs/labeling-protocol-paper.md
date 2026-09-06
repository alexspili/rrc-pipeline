# Measurement protocol, matching two pages by the marks on the paper

Written 2026-09-06, **before any held-out pair was drawn and before any of them
was looked at**. Every number in the mechanism was frozen first; the freeze is
in the commit named below.

## What is being measured, and what is not

`pipeline/paper.py` claims that two page images are the front and back of **one
sheet**. That is narrower than "the same document", because a document can be
two separate sheets, and it is a sufficient condition: a confirmation settles
the document question, a refusal says nothing about it.

The mechanism only ever **confirms**. It has no way to assert that two pages
are different, and it must never be read as doing so.

**Not measured here:** whether reassembly gets better. The product number is 13
of 20 documents clean and neither part of this touches it. Passing both bars
and making that number worse is possible, and crediting this mechanism with an
accuracy improvement needs a document-level evaluation on records used in
neither part.

## What is frozen, and why the number alone would not be enough

A frozen threshold on an unfrozen statistic is not a firewall: the margin
definition, the harmonics removed, the sample count, the centroid estimator,
the area test and the minimum mark count are all levers that could be pulled
after seeing a result.

**Pinned: commit `4868fdd3f714a38f9117b81b2b1c5f57a7c2b642`.** That commit
contains `compare` and every constant it uses, and
`tests/tier1/test_paper.py::test_the_frozen_constants_are_the_ones_measured_under`
fails if any of them moves.

    MARGIN_THRESHOLD    0.30      MIN_MARKS_AGREEING  2
    MIN_MARK_AREA       0.02      MAX_ASPECT          3.0
    MIN_FILL            0.30      AREA_RATIO          1.6
    POSITION_TOLERANCE  0.02      MAX_OFFSET          0.06
    SAMPLES             720       STRIP               2

**The threshold is barely constrained by evidence and this must be said
plainly.** Across 517 hard negatives, after the ambiguity rule of DEFECTS #55,
**not one negative ever reached two agreeing marks**. No negative has ever been
excluded by this threshold. What excludes them is `MIN_MARKS_AGREEING` and the
ambiguity rule. The threshold's only empirical constraint is an upper bound
from a single true pair: 1495414 p6+p7 has a second margin of 0.359, so
anything above that confirms nothing at all.

## Development evidence, and what it is worth

All of it comes from records that hold **no** fresh pair, plus the two records
whose marks were inspected by eye. The held-out frame was never touched.

| | |
|---|---|
| Hard negatives scored | 517 across three strata |
| False confirmations | 0 |
| Negatives reaching two agreeing marks | 0 |
| Known same-sheet pairs confirmed | 1 of 2 |

Zero of 517 licenses a false-positive rate **below 0.58%** at 95%. It does not
license "no false positives" and that phrase is not to be used.

**One fix in the frozen mechanism was found by looking at a failure** — the
ambiguity rule, after a two-hole punch's symmetry confirmed two sheets from
different counties as one. It is justified by what a punch does, not by which
row it deleted, but it has **no held-out support whatever**. The run below is
its first test.

## Part A — false confirmations. No labelling.

Guaranteed-false pairs, drawn only from records never used in development, in
three strata reported separately:

1. **record** — two different records with different leases. 198 of 202
   records have a unique lease name, and no file name or `(bytes, pages)` pair
   occurs twice, so duplicate filings are closed off.
2. **file** — two files of one record: same well, same district office.
3. **stack** — two non-adjacent pages of one file, punched in one stroke.

Pairs are screened for scoreability exactly as the held-out positives are: a
pair the mechanism cannot score is not evidence about false positives, and
counting it as a pass inflates safety by dilution. Capped at 10 pairs per
record so the effective sample is records, not pairs.

**A confirmed guaranteed-false pair counts as a false positive** unless Alex
judges the two pages to be the same filing scanned twice. He adjudicates, not
me; the number of such adjudications is reported; and **more than two of them
invalidates the construction**, at which point Part A is inconclusive rather
than passed.

## Part B — confirmations. One sitting, judged blind.

**The frame.** 53 same-family adjacent pairs across 38 records — a G-1 or W-2
face immediately followed by a continuation or section page of the same form
family — excluding only 1493608, 1495414 and 1774674, whose marks have been
inspected. Screened for scoreability first; the count that survives is reported
to Alex **before** he judges anything.

Hard negatives on the same sheet: a face immediately followed by the printed
back of a *different* form, and faces paired with a back-ish page three or more
pages later. Adjacent, so proximity says pair and the paper says otherwise.

**Blinding, and it is not a detail.** Alex identified the punch rim as the
signal and has matched pages by eye using it. If he judges these pairs the same
way, the sitting measures whether an algorithm agrees with a human reading the
same pixels — a consistency check dressed as validation. So:

- the images he sees have **every detected mark masked out**
- rows are shuffled and page numbers stripped, so the stratum is invisible
- he records **which evidence drove each call**: ink show-through, torn edges,
  staple marks, fold lines, crop and skew geometry, missing corners
- the mechanism's verdicts are computed and hashed **before** the sheet goes out

**Optionally, and separately:** after judging blind he may look again unmasked
and record a second verdict. Only the blind verdict is graded. The unmasked one
measures how much of the sitting the masking cost, and is reported as that.

**`cannot-tell`** is excluded from both numerator and denominator and reported
as a coverage figure. Above 30% of the sheet, the labels are not trustworthy
and the sitting is inconclusive.

## DECISION RULE: both halves, or it does not ship

**DECISION RULE:** the mechanism ships if and only if **both** hold — Part A
returns **zero** false confirmations across all three strata on held-out
records, **and** Part B confirms **at least half** of the pairs Alex judges
same-sheet, with a denominator of at least **8**.

Fewer than 8 same-sheet pairs and the sitting is **inconclusive**: it does not
ship this cycle, and the next step is fetching about 110 more records and
re-screening, not reinterpreting the pairs in hand.

One clause, a conjunction. Neither half can rescue the other.

**Reachability, checked before the bar was written.** Part A's zero is
attainable: 517 development negatives produced none, and held-out negatives are
drawn the same way. Part B's half-of-eight is 4 confirmations; the one sheet
measured end to end clears the threshold on two marks with 0.059 and 0.178 of
headroom, so 8 of 8 is attainable and 4 is nowhere near a ceiling. **Neither
half sits above its maximum**, which is the check whose absence voided the
reassembly pre-registration of 2026-09-05.

**Vacuity, the mirror failure.** Zero false confirmations is free to a
threshold so high it confirms nothing, which is why the conjunction exists and
why the threshold is frozen before Part B's pairs are drawn. It cannot be
raised after seeing either result. If Part A fails, the mechanism does not ship
this cycle; any retune requires a fresh record split and a re-run of both parts.

## What a failure teaches, and what it may not do

A pair judged wrong may reveal a mechanism nobody has seen — a punch geometry,
a scanning habit, something else. **That gets a defect entry and a failing
test, and it does not change this sitting's arithmetic.** Origin: DEFECTS #31
and #35, where a pre-registration carried two decision clauses and the second
was available to rescue the first. One clause. It is above.

## What this cannot establish

**A confirmation rate with a narrow interval.** At 8 of 12 the 95% interval
runs from about 36% to 90%. The floor in the decision rule is a vacuity guard
first and an estimate second.

**Anything about pairs it cannot score.** The claim is conditional on both
pages carrying at least two usable marks. The reach that matters is the rate
among pairs where identity agreement is below the attachment threshold, which
is where this mechanism's whole value lies, and that figure is reported beside
any headline rather than folded into it.

**Anything about other punch machines, districts or decades.** The positive
evidence is two records deep.

**Anything about staples.** They sit below the mark area floor and cannot be
recovered by lowering it, because bold printed glyphs are the same size and
pass every other test. A real physical channel this mechanism cannot read.
