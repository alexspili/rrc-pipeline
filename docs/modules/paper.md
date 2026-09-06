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

## Not yet a rule, because nothing enforces it

If this module passes its pre-registered bar, `pipeline/reassemble.py` attaches
a pair on `(identity agreement >= MIN_AGREEMENTS or paper confirms) and not
contradicted` — Alex's ruling of 2026-09-05, which deliberately keeps the
identity veto over a paper confirmation.

That is written here as an intention and not as a numbered rule, because no
test pins it and nothing in the code does it. **The module changes no output
today.** It becomes R7 in the commit that wires it in, with the test that
enforces it, and not before.

## RETIRED

Nothing yet.
