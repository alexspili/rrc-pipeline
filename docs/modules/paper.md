# Module: matching two pages by the marks on the paper

Answers one question: are these two page images the front and back of **one
sheet**? That is narrower than "the same document" — a document can be two
separate sheets — and it is a sufficient condition, so a confirmation settles
the document question and a refusal says nothing about it.

Built 2026-09-05 and 2026-09-06. Pure module `pipeline/paper.py`, its I/O half
`pipeline/papermatch.py`. No model calls; the whole thing costs nothing to run
and nothing to re-run.

## Why it has to exist

`pipeline/reassemble.py` pairs pages by comparing identity fields — operator
name, lease name, well number, completion date, district. Held out, it is 65%
clean: 13 of 20 documents. The cause is settled and is not a bug. **Those
fields describe the well.** A file holds several filings for one well, and
those filings agree on every one of them because it is one well.

So identity fields can only **exclude**. A contradiction proves two pages are
not a pair. Agreement proves nothing, because agreement is guaranteed.

Only the paper itself identifies a sheet. A punch through old paper tears a
particular rim, and the back of that sheet carries the same rim, mirrored.

## What is compared, and the three things that had to be got right

**The outline of every solid mark, by angle.** Distance from the mark's centre
to its edge, sampled 720 times around, with harmonics 0, 1 and 2 removed. What
is left is the tear.

**1. The statistic is the margin, never the raw score.** A district office
punches a *stack* of sheets in one stroke, and every sheet in that stack
carries the same die signature at the same position. Measured on file
1495414-0, page 6's hole against the same hole on nine other sheets:

| Pair | Plain | Mirrored | Margin |
|---|---|---|---|
| p6 + p7, **the same sheet** | 0.155 | **0.614** | **+0.459** |
| p6 + p8, same stack | **0.565** | 0.473 | −0.092 |
| p6 + p9, same stack | **0.533** | 0.136 | −0.397 |
| p6 + p12, same stack | **0.566** | 0.223 | −0.343 |

Three unrelated sheets score as high as a true pair on the raw correlation. A
threshold on it would have confirmed all three. What separates them is *which
transform wins*: a true pair matches mirrored, a stack-mate matches plain.

**2. The transform is predicted, never searched.** Allowing a rotation offset
search lifts a true pair from +0.618 to +0.633 and the controls from about
zero to +0.42 and +0.49. The separation is destroyed by the search, not
improved by it.

**3. Harmonics 0, 1 and 2 come out first.** A one-pixel error in the estimated
centre injects a pure cosine that survives mirroring. Removing it holds a true
pair at 0.619 and drops that same pair's *unmirrored* score from 0.295 to
0.164, widening the margin from 0.32 to 0.46.

## The transforms, and what a control is

Turning a sheet over is a reflection, and the operator may turn it about either
edge, so **both** of these are legitimate and both are tried:

    flip_v  (x, y) -> (x, 1 - y)      turned top over bottom
    flip_h  (x, y) -> (1 - x, y)      turned left over right

The transforms a turned-over sheet **cannot** produce are the
orientation-preserving ones, because turning paper over always reverses
orientation. They are the control:

    same    (x, y) -> (x, y)
    rot180  (x, y) -> (1 - x, 1 - y)

Two options on each side, so the real side is handed no freedom the control
lacks.

**An earlier probe used `flip_h` as its control and was wrong to.** The
paper-outline mechanism was closed on the finding that its two transforms
scored equally — but both were legitimate, so it never had a control at all.
That closure rests on nothing and re-running it properly is outstanding work.

## A punch hole is one kind of mark, and two marks are required

The corner blot on 1495414 matched front-to-back with a margin of **+1.162**,
against +0.459 for the punch hole on the same sheet. So the module reads every
solid mark and does not care which kind it is.

That matters for more than sensitivity. **A stack shares its punch holes and
shares no stain.** Requiring two agreeing marks is what makes stack punching
survivable, and it is not decoration: on 1495414 a stack-mate got one mark over
the threshold and the two-mark rule refused it.

**Measured, 2026-09-06**, against 86 hard negatives — all same-file pairs
punched in one stroke — and the two known same-sheet pairs:

| Rule | True pairs | False positives |
|---|---|---|
| **2 marks over 0.30** | 1 of 2 | **0 of 86** |
| 1 mark over 0.30 | 2 of 2 | 2 of 86 |
| 1 mark over 0.40 | 2 of 2 | 1 of 86 |
| 1 mark over 0.45 | 2 of 2 | 1 of 86 |
| 1 mark over 0.50 | 0 of 2 | 1 of 86 |
| 1 mark over 0.60 | 0 of 2 | 0 of 86 |

A one-mark rule leaks at every threshold that still confirms anything.

## What that costs, stated plainly

**It refuses 1493608 p5+p6**, a pair Alex identified from the paper by
comparing the punch-hole shape. Both holes are found and paired correctly under
`flip_v`:

| Mark pair | Correlation | Best control | Margin |
|---|---|---|---|
| (0.688, 0.071) ↔ (0.676, 0.922) | +0.677 | +0.206 | **+0.470** |
| (0.387, 0.069) ↔ (0.393, 0.922) | +0.320 | +0.333 | **−0.013** |

One hole carries the signal and the other carries none — and it is the
*cleaner* hole that fails. The mark that matched is the one the detector
classified as a blot, because ink made its edge irregular. **A tidy round punch
hole has almost no shape to compare.** So requiring two marks is really
requiring two *damaged* marks, and that sheet has one.

For a mechanism whose only job is to confirm, that is the right side to fail
on. It abstains; it does not deny. A missed confirmation costs coverage. A
wrong confirmation puts one well's casing record under another well's identity
and produces a document that looks complete.

## Printing is not damage to paper

`solid_marks` was reading printed text as marks. On page 6 of 1495414 the
operator's underlined address came through as a single component at **5,628 px,
larger than either punch hole** at 4,432 and 4,292, because the underline joins
the letters. No area threshold separates them.

Shape does. That line's bounding box is 465x38, an aspect of **12.2**, against
1.3 for the corner blot and 1.1 for the punch holes. `MAX_ASPECT = 3.0` removes
every text line and printed rule on both pages and removes no real mark: page 6
went from 33 marks to 3.

**Known cost:** staple holes are below the area floor and this module cannot
read them. Bold glyphs are the same size and pass every other test, so the
floor cannot be lowered to recover them. Staples were identified as a real
physical channel on 2026-09-05 and need a discriminator that does not exist.

## There are no page fixtures, and that is deliberate

Tier 2 reads the corpus and skips when `data/` is absent. The first attempt
built fixtures by blanking a page and pasting back only detected marks, and
called them redacted by construction. Rendered and inspected, the first carried
an operator's address; tightened, the next still carried a printed fragment and
a handwritten squiggle.

**Redaction by detection asks the component whose failure mode is mistaking ink
for paper to certify that it did not.** No threshold fixes that. DEFECTS #53.

## The area floor was never what kept printing out

Established by DEFECTS #61, which set out to fix something else. The detector
was reading every page at an assumed 300 dpi; 53 corpus pages are 200 dpi, and
on those the floor was therefore being applied at 0.045 in² instead of 0.02.

Reading them at their own resolution gains 19 components across 11 pages.
**All 19 were rendered and looked at, and all 19 are printing:** five fragments
of large bold sideways fax-header text, two pieces of a casing schematic's
hatching, part of a RECEIVED stamp, a piece of handwriting, and two pieces of
plat linework. Two of them are round and solid enough to be called `hole`.

So an honestly converted 0.02 in² floor admits ink. It always would have; the
300 dpi pages simply do not happen to carry fax headers. What excludes printing
is `MAX_ASPECT`, and the address line of DEFECTS #53 makes the same point from
the other side: at 0.0625 in² it was well over the floor and was caught by its
aspect of 12.2.

**This is why the staple channel cannot be built by lowering the floor**, and
it is a stronger reason than the original one. Below the floor there is no size
envelope left to lean on and `MAX_ASPECT` does not reach chunky printed
fragments, so a staple has to be recognised by structure: two marks, about
10 mm apart, near an edge or corner, with no neighbours on their baseline.

None of it changed a verdict. All 494 within-file pairs across the six affected
records were compared under both readings and none moved, which is the margin
doing the work the module was already relying on it for.

## Orientation, and why a half turn costs nothing

The census records an `orientation` for every page and nothing in this module
consults it. That is safe for half turns and not for quarter turns, and the
reason is closure rather than luck: `rot180` after `flip_v` is `flip_h`, and
`rot180` after `same` is `rot180`. A 180 degree difference in how two pages
were stored therefore permutes within the legitimate pair and within the
control pair, and never moves a page from one set into the other.

A quarter turn does break it, and the mechanism then finds nothing to pair and
abstains, which is R3 behaving correctly rather than a silent wrong answer.
Measured: **2.9% of adjacent corpus pairs differ by a quarter turn**, and 0 of
the 54 same-family adjacent pairs in the 2026-09-06 frame do, so that sitting
is unaffected. It is a cost in reach on any frame drawn from adjacent pairs
without a classifier, which is what the staple channel's frame will be.

Pinned by: tests/tier1/test_paper.py::test_a_half_turn_never_moves_a_page_between_the_two_sets

## A second channel, for the marks the floor throws away

Added 2026-09-07. `compare` confirmed 4 of the 16 pairs Alex judged same-sheet,
and 15 of those 16 calls rest on evidence under `MIN_MARK_AREA`. Going under
the floor means giving up the size envelope, so the marks down there have to be
told from printing another way.

**Printing comes in runs and damage does not.** Glyphs have neighbours on their
baseline, leader dots have neighbours along their line, a staple's two legs are
a pair and a nick has nobody. A mark with at most one comparable neighbour
within a character pitch is not part of a run, and on one measured page that
single test took 2,357 candidates to 37.

**The staple model this was built from is wrong, and the measurement is how
that was found.** The design said a staple leaves two marks about 10 mm apart
near a corner and that pitch and angle would be the signature. Of the 8
development pairs where a flip beat the control, **one** has any agreeing pair
at staple pitch; the rest sit 1.6, 3.4, 5.0, 8.7 and 9.2 inches apart.
Rendered and looked at, the marks are specks, nicks and show-through. Pitch
appears nowhere in the code because it earned no place in it. Same shape as
DEFECTS #59: a fact assembled from real observations, generalised in the wrong
direction, and repeated until repetition made it look established.

**Count replaces shape.** These marks are a few dozen pixels and have no rim to
sample, so position carries the whole claim, which R2 forbids it to do alone.
What stands in for the outline is several marks agreeing at once under one
transform, with the controls given exactly the same freedom, and the statistic
is still the margin (R4).

**No offset is searched, and that is measured rather than assumed:**

| | cross-record | same file | positives |
|---|---|---|---|
| Marks matched one at a time | **0 of 120** | 3 of 160 | 4 of 16 |
| A shared rigid offset searched | 2 of 120 | 11 of 160 | 5 of 16 |

An offset search hands the control the freedom it hands the real side. That is
R1's finding in a new place.

**The two channels partition at `MIN_MARK_AREA`** so neither can ever count the
other's marks. A speck must not be allowed to stand in for a rim: a shared
punch stroke is already the hazard R5 exists for.

**Known residue, asserted in a test rather than tuned away.** The two ends of a
run of printing survive the neighbour filter, because one neighbour is allowed
so that a pair does not delete itself. A row of eight leader dots contributes
two candidates. What stops them mattering is the two-agreement rule and the
control, not the filter.

**Standing.** Every constant was chosen on the 91 development records of
`tests/fixtures/paper_record_split.csv`, and the firing rule was chosen after
seeing both the positive and the negative results. Frozen at commit `1a01829`;
pre-registration in `docs/labeling-protocol-staple.md`.

### The held-out run, 2026-09-07: the rule passed and the failure taught more

| | |
|---|---|
| Held-out guaranteed-false pairs, two different records | **1 false confirmation of 400** |
| 95% upper bound | **1.180%** |
| Pre-registered bar | below 2% |

The bar was a bound rather than a zero because zero is not attainable at 400
pairs: the modelled expectation was 1.8, and a bar of zero would have been
DEFECTS #51 in the other direction.

**The one failure showed a hole and it is the reason this channel is wired
into nothing.** All four agreeing marks sat at x between 0.93 and 0.95, on the
sheet's right edge. `flip_v` leaves x alone, so marks sharing a vertical band
agree in x for free and only y is asked to line up:

| Candidates | P(two or more agree under flip_v) |
|---|---|
| Spread over the sheet | 0.62% |
| Confined to one edge band | **85.65%** |

`SMALL_EDGE_IN` is what puts them in the band, so the filter that makes the
channel possible is the filter that makes the hole. It is DEFECTS #55
generalised from a twin mark to a twin coordinate, and #55 was cited in this
design without being generalised. DEFECTS #63.

**Where it will hurt is the place with no measurement.** Two pages of a true
adjacent pair share a file, a scanner and a filing, so their candidates sit in
the same bands far more often than two pages from different records do. The
regime with no measured false-confirmation rate is the regime where this fires
most easily.

The fix is not made. It would be chosen by looking at a failure, it has no
held-out support, and the split it needs is the split just spent.

## Rules

R1. The transform is predicted, never searched. No rotation offset.
    Origin: searching rotations lifts every control to +0.42 and +0.49.
    Pinned by: tests/tier1/test_paper.py::test_a_rotated_copy_is_not_a_match_under_any_transform

R2. Position locates and pairs marks; the outline decides.
    Origin: punch pitch is a corpus-wide constant, 2.75 in across 19 unrelated
    pages, and unrelated pages collide 16.9% of the time. A matcher built on
    position alone had its controls match it pair for pair on all 26 judged
    pairs.
    Pinned by: tests/tier1/test_paper.py::test_marks_of_different_size_are_never_paired

R3. Abstain, never assert difference. Too few marks, an outline that could not
    be closed, or a profile with no variation returns a named reason.
    Origin: a mark the detector missed is not evidence of anything.
    Pinned by: tests/tier1/test_paper.py::test_a_page_with_no_marks_abstains_rather_than_denying

R4. The statistic is the margin, never the raw score.
    Origin: stack punching puts three unrelated sheets at 0.53 to 0.57 raw.
    Pinned by: tests/tier1/test_paper.py::test_the_margin_is_the_statistic_not_the_raw_score

R5. Two agreeing marks minimum, matched on area and paired one-to-one.
    Origin: a stack shares its punch holes and shares no stain; and measured,
    a one-mark rule leaks at every threshold that confirms anything.
    Pinned by: tests/tier1/test_paper.py::test_one_agreeing_mark_is_never_enough

R6. Printing is not a mark on the paper.
    Origin: DEFECTS #53, an underlined address larger than a punch hole.
    Pinned by: tests/tier1/test_paper.py::test_a_line_of_text_is_not_a_mark_on_the_paper

R7. A page is read at its own resolution, and no caller takes a default.
    Origin: DEFECTS #61. The size envelope is stated in square inches, so
    something has to convert it, and until then nothing did: 53 corpus pages
    are 200 dpi and were read as 300. The damaging half is not the floor but
    `area_in2`, which came out 2.25x small and so put one physical mark outside
    AREA_RATIO from itself, making the 11 adjacent pairs that straddle the
    change unconfirmable by construction.
    Pinned by: tests/tier2/test_papermatch.py::test_a_page_is_read_at_its_own_resolution

## Not yet a rule, because nothing enforces it

If this module passes its pre-registered bar, `pipeline/reassemble.py` attaches
a pair on `(identity agreement >= MIN_AGREEMENTS or paper confirms) and not
contradicted` — Alex's ruling of 2026-09-05, which deliberately keeps the
identity veto over a paper confirmation.

That is written here as an intention and not as a numbered rule, because no
test pins it and nothing in the code does it. **The module changes no output
today.** It becomes R8 in the commit that wires it in, with the test that
enforces it, and not before. It was written here as R7, and R7 was taken on
2026-09-06 by DEFECTS #61, which is a rule with a test behind it today.

## RETIRED

Nothing yet.

## The held-out sitting, 2026-09-06: safe, blind, does not ship

Rule fixed before the sheet was drawn, mechanism frozen in commit `4868fdd`,
verdicts sealed and hashed at `943d12256c7e20de` before Alex saw an image.

| | |
|---|---|
| Part A, held-out guaranteed-false pairs | **0 false confirmations of 325** |
| Part A, pairs Alex judged not-same-sheet | 0 of 8 |
| Part A, development negatives | 0 of 517 |
| Part B | **4 of 16 same-sheet pairs, 25%** |
| Rule needed | at least half of at least 8 |
| cannot-tell | 6 of 30, 20%, under the 30% trip |

**It does not ship**, and it changes no output. Part A passed; Part B did not.

**The evidence column explains it.** Of the 16 pairs judged same-sheet, **15
cite staple marks** — the one channel this module structurally cannot read,
because staples sit below `MIN_MARK_AREA` and bold printed glyphs are the same
size, so the floor cannot be lowered to reach them. The human and the machine
were reading different evidence, and the machine had the minority channel.

Three of the refused same-sheet pairs held a strong single margin — 0.944,
0.684, 0.456 — and failed on the two-mark rule alone. That rule is correct: a
one-mark rule leaked at every threshold that confirmed anything. It is also the
binding constraint on reach.

**What stands:** zero false confirmations across 850 negatives, development,
held-out and human-labelled. Zero of 325 held-out licenses a false-positive
rate below 0.92% at 95%. That is a real property and it is not the property
that was needed.

**What may not happen next:** these 30 pairs are spent. Lowering the floor,
relaxing the two-mark rule, or adding a staple channel and rescoring here would
be fitting to the test and quoting the test. A retune needs a fresh record
split and a re-run of both halves.
