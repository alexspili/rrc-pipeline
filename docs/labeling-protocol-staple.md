# Measurement protocol, the small-mark channel

Written 2026-09-07, **before any held-out record was scored**. The mechanism
and every constant it uses were frozen first, in the commit named below.

No labelling. No fetch. No money. This measures one thing, on records nobody
has tuned on, and the thing it measures is safety.

## What is being measured, and what is not

`pipeline/paper.compare_small` claims that two page images are the front and
back of one sheet, on the evidence of marks **under** `MIN_MARK_AREA`. It is a
second channel beside `compare`, not a replacement, and the two never see the
same mark: their area bands partition at `MIN_MARK_AREA` and a tier-1 test
asserts it on an array carrying both sizes.

It only ever **confirms**. It has no way to assert that two pages are
different, and it must never be read as doing so (R3).

**Not measured here:** reach. Every positive in existence has been judged and
is now development data, which is why the fetch exists. Nothing in this run may
be quoted as a confirmation rate.

**Not measured here either:** the rate on genuinely *adjacent* pairs that are
not one sheet. There are none with a trustworthy label. The eight negatives
Alex judged are all three or more pages apart, and DEFECTS #62 records what
happened when I tried to build an adjacent stratum out of the census
`form_class`: six of its seven rows were pairs he had judged same-sheet. That
gap is the fetch's job and it is not closed by this run.

## What is frozen

**Pinned: the commit that adds `compare_small` and its constants**, asserted by
`tests/tier1/test_paper.py::test_the_small_mark_constants_are_the_ones_measured_under`,
which fails if any of them moves.

    SMALL_AREA_IN2  (25/300², 0.02)   SMALL_MAX_ASPECT      2.5
    SMALL_EDGE_IN   0.8               SMALL_RUN_PITCH_IN    0.35
    SMALL_MAX_NEIGHBOURS  1           SMALL_INSET_IN        0.03
    SMALL_TOLERANCE 0.008             SMALL_AREA_RATIO      3.0
    MIN_SMALL_AGREEING    2

**Every one of these was chosen while looking at the 91 development records,
and the firing rule was chosen after seeing both the positive and the negative
results.** That is said here rather than discovered later. It is the same
standing as DEFECTS #55's ambiguity rule when it was written: justified by what
paper and printing do, with no held-out support of any kind. This run is its
first test.

## Development evidence, and what it is worth

| | |
|---|---|
| Pairs Alex judged same-sheet, fired on | 4 of 16, disjoint from `compare`'s 4 |
| Pairs Alex judged not-same-sheet, fired on | 0 of 8 |
| Guaranteed-false, two different records | 0 of 120 |
| Non-adjacent pages of one file | 3 of 160, for adjudication |

Zero of 120 licenses a false-positive rate below 3.0% at 95% and no better. It
does not license "no false positives" and that phrase is not to be used.

## The run

Guaranteed-false pairs drawn only from the **111 held-out records** of
`tests/fixtures/paper_record_split.csv`, in the stratum whose truth needs no
human: **two different records with different leases**. 198 of 202 records have
a unique lease name and no `(bytes, pages)` pair occurs twice, so duplicate
filings are closed off. Capped per record so the effective sample is records
rather than pairs.

Also reported, separately and not part of the decision: non-adjacent pages of
one held-out file. Those are **not** guaranteed false. The protocol's standing
rule is that Alex adjudicates a confirmed same-file pair and I do not.

## DECISION RULE

**The channel goes forward to a fetch if and only if the held-out cross-record
false-confirmation rate has a 95% upper bound below 2%.**

One clause. It is a bound rather than a count because a count of zero is not
attainable here and pretending otherwise is DEFECTS #51 exactly.

**Reachability, checked before the bar was written.** A mark's catchment at
`SMALL_TOLERANCE` is 0.000201 of the sheet. Across the development pairs'
candidate counts, the chance of two independent agreements arising and beating
the control is about **0.46% per pair**, so:

| Pairs scored | Expected false confirmations |
|---|---|
| 150 | 0.7 |
| 250 | 1.1 |
| 400 | 1.8 |

and the bound the rule asks for is met by 0 of 150 (1.98%), 1 of 250 (1.88%),
2 of 350 (1.79%) or 3 of 400 (1.93%). **The bar sits above the expected value
at every sample size**, so it is attainable, and it is not attainable by
accident: at twice the expected rate it fails. Neither half sits above its
maximum, which is the check whose absence voided the reassembly
pre-registration of 2026-09-05.

**Vacuity, the mirror failure.** A low false rate is free to a channel that
confirms nothing. This one fires on 4 of 16 development positives, measured
before the bar was written, so the bar is not being met by silence.

## What this cannot establish, stated before the result

**That the module is as safe as it was.** `compare` has 0 false confirmations
in 850 negatives, below 0.92% at 95%. A bound of 2% is **worse than that**.
Adding this channel trades some of the module's safety claim for roughly double
its reach, and that trade is Alex's to make, not the rule's. The rule decides
only whether the trade is worth putting to him.

**Anything about adjacent pairs**, per the second paragraph above.

**Anything about other districts.** The held-out records are district 03, like
every record in the corpus.

## What a failure teaches, and what it may not do

A confirmed pair may reveal a mechanism nobody has seen. **That gets a defect
entry and a failing test, and it does not change this run's arithmetic.** One
clause. It is above.
