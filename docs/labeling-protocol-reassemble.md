# Measurement protocol, reassembly

Written 2026-09-03, before the identity reader exists and before any page has
been grouped. The threshold it fixes is already in the code as
`MIN_AGREEMENTS = 2`, and this file is what decides whether it stays there.

## What is being measured, and what is not

Not accuracy of extraction. Whether **the pages this module groups together
are the pages that belong together**, and whether the ones it declines to
group are ones a human agrees should be declined.

The anti-goal from docs/modules/reassemble.md governs the reading of every
number here: **it must not improve by attaching more pages.** A wrong
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

Fixed here before the identity reader is built.

The threshold `MIN_AGREEMENTS` stays at **2** unless one of these fires:

- **It attaches a page to the wrong face, anywhere in either set.** One wrong
  attachment is enough. This is the anti-goal and it is not traded against
  coverage.
- **It fails to attach two or more of the three DEFECTS #25 read-out cases.**
  Those three are the reason the module exists.

If either fires, the threshold moves to 3 and both sets are re-measured
**once**. That result is final either way, and a threshold of 3 that also
fails means the identity fields on section pages do not carry enough signal
and the module is reported as such rather than tuned further.

Coverage is reported and decides nothing. A run that attaches nothing and is
wrong about nothing is a legitimate outcome of this rule, and would be a real
finding about the paper rather than a failure of the code.

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
