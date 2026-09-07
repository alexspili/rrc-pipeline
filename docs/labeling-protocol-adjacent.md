# Measurement protocol, adjacent pairs in district 02

Written 2026-09-07, **before any pair was drawn and before Alex saw an image**.
The mechanism and every constant were frozen first, in commit
`1a0182976062931bdcf416f3a104975f91d3cac6`.

## The gap this exists to close

`pipeline/paper.compare_small` has a measured false-confirmation rate on pairs
drawn from **two different records**: 1 of 400, a 95% upper bound of 1.18%. It
has **no measured rate at all on adjacent pairs that are not one sheet**, and
that is the only regime reassembly would ever put to it.

No such measurement exists because no trustworthy label exists. The eight
negatives Alex judged on 2026-09-06 are all three or more pages apart. DEFECTS
#62 records what happened when the census `form_class` was asked to supply the
label instead: six of its seven rows were pairs he had judged **same**-sheet.

DEFECTS #63 and #64 say why the gap matters most here. Two pages of a true
adjacent pair share a file, a scanner and a filing, so their marks sit in the
same bands and the same regions far more often than two pages from different
records do.

## The frame

District 02, 155 records fetched 2026-09-07, recorded as `sitting_frame` in
`tests/fixtures/paper_record_split.csv` and never tuned on. Alex has seen no
page of any of them.

Screened first, and the count reported to him before anything was drawn:

| | |
|---|---|
| Adjacent page pairs examined | 2,009 |
| Scoreable, both pages carrying 2 or more small marks | **1,872 (93.2%)** |
| Records holding at least one scoreable pair | **143 of 155** |
| Small marks on the thinner page of a pair | median 10, quartiles 6 and 15 |

Files longer than 60 pages are excluded: the frame holds one of 288 pages
against a median of 11, and a bound volume's adjacent pairs are not the thing
being measured.

**No classifier is used.** The paper channels do not need to know what form a
page is, and asking `form_class` which pairs are not one sheet is the trap of
DEFECTS #62. The frame is therefore plain adjacent pairs, and most adjacent
pairs in a file are two different sheets. That is the point: it is what
produces adjacent negatives with a human label.

## The draw

**40 pairs**, Alex's choice of size on 2026-09-07, taken as 40 records drawn
uniformly at random from the 143, then one scoreable pair drawn uniformly at
random within each. One pair per record, so the effective sample is records.

**Nothing is stratified and nothing is enriched.** In particular the parity
prior below is *not* used to select pairs: it was discovered through the
mechanism's own confirmations, so enriching on it would inflate measured reach.

## Blinding: there is none, and that is stated rather than hidden

The rule was to mask every mark the mechanism reads. That rule was written when
the mechanism read punch rims and blots. It now reads small specks near the
paper's edge, which is the same evidence Alex reads, and masking them would
blank the page edges and leave nothing to judge. Measured on the 2026-09-06
sitting, removing the channel the human reads left about one usable same-sheet
call in thirty.

So the pages go out **as scanned**, and the limitation is stated here in
advance: **on this sheet the human and the machine read the same evidence.**
This measures agreement on a shared channel, not independent validation.

What guards the failure mode that actually matters is not masking but the
label. Alex records one of:

    same-sheet          front and back of one sheet of paper
    same-bundle         one filing or one stapled bundle, but NOT one sheet
    different           neither
    cannot-tell

The middle value exists because a staple or a punch goes through every sheet in
a bundle at the same place, so the machine's one predicted failure is confirming
a bundle-mate. Asking Alex to separate those two is what makes the sitting able
to detect it. He also records **which evidence drove each call**: ink
show-through, torn edges, staple marks, fold lines, crop and skew geometry,
missing corners, speckle.

Rows are shuffled, page numbers stripped, and the mechanism's verdicts computed
and hashed before the sheet goes out.

## DECISION RULE

**The channel is wired into `pipeline/reassemble.py` if and only if both hold:**

**(a)** it confirms **at most one** pair Alex judges `same-bundle` or
`different`, and

**(b)** it confirms **at least two** pairs he judges `same-sheet`, with that
denominator at least **8**.

One clause, a conjunction. Neither half can rescue the other.

**Reachability, checked before the bar was written.**

- (a) If the adjacent rate matched the measured cross-record rate of 0.25%,
  about 28 negatives would produce **0.07** false confirmations, so zero or one
  is comfortably attainable. It is not vacuous either: the mechanism fires on
  **7.8%** of all 1,872 scoreable pairs in this frame, so a channel that fired
  indiscriminately would breach it.
- (b) At the 25% reach measured on district 03 and roughly 12 same-sheet pairs
  expected, the expected count is **3.0**. A bar of two sits below the
  expectation rather than at or above it, which is the check whose absence
  voided the reassembly pre-registration of 2026-09-05 (DEFECTS #51).

**Fewer than 8 `same-sheet` labels and half (b) is inconclusive**: the channel
does not ship this cycle, and the next step is more records, not a reread of
these.

**`cannot-tell` is excluded from both numerator and denominator** and reported
as a coverage figure. Above 30% of the sheet the labels cannot carry a result
and the sitting is inconclusive.

## What this sitting cannot establish, stated before the result

**Adjacent safety to the standard the cross-record stratum reached.** With
about 28 negatives, even a perfect zero licenses only a 95% upper bound of
**10.1%**, against **1.18%** from the 400 held-out cross-record pairs. This
sheet can detect a gross difference between the two regimes. It cannot show
they are similar, and no arithmetic on 40 pairs can.

**A reach figure with a narrow interval.** At 3 of 12 the 95% interval runs
from about 9% to 61%.

**Anything about district 03.** These are district 02 records and the
population is a confound written down in advance: a difference here has two
possible causes, the mechanism and the district, and this sitting cannot
separate them.

## Secondary analyses, pre-registered and not decision-bearing

**Parity.** Across the frame the mechanism confirms 9.73% of pairs starting on
an even page against 5.91% of pairs starting on an odd page, a ratio of 1.65
with z = 3.08 and p = 0.002. That is what would be seen if these files open
with a separator or ID card, shifting every sheet boundary by one. Alex's
labels test it independently of the mechanism. It decides nothing here.

**The `same-bundle` rate itself**, which is the first direct measurement of how
often the confusion DEFECTS #63 predicts is even available to be made.

## What a failure teaches, and what it may not do

A confirmed pair may reveal a mechanism nobody has seen. **That gets a defect
entry and a failing test, and it does not change this sitting's arithmetic.**
Origin: DEFECTS #31 and #35, where a pre-registration carried two decision
clauses and the second was available to rescue the first. One clause. It is
above.
