# DEFECTS.md

Append-only log of defects: things generated, assumed, or built that were
wrong, and what each one changed. Entries are never edited after the fact;
corrections get new entries. Each entry carries what happened, why it was
wrong, and its resolution: a rule in docs/modules/, a test that pins it, a
type or constructor invariant, or an explicit decision to accept it. "Pin:
pending" means the referenced test does not exist yet; it must be created
when the module is built, and the pending marker replaced with the test path
in the same commit.

Entries 1, 2, and 5 predate any pipeline code. They were found by reading
real corpus documents and API responses during recon (2026-08-28/29), which
is the cheapest place a defect can be found.

---

## #1 — 2026-08-28 — Oversized pages silently destroyed by long-edge downscale

**What happened:** A well-log record delivered a single-strip TIFF of
1010 x 15,167 px. The planned vision pipeline caps images at 1568 px on the
long edge; that page would downscale to a 104 px-wide sliver and classify as
garbage with no error raised.

**Why it was wrong:** The rendering plan assumed page-shaped pages. The
archive contains strips and fold-outs.

**Measured footprint (2026-08-30):** The closed 202-record corpus contains
zero log strips (max aspect ratio 3.71) but 23 pages over AR 2.0, topping
out at 11,264 x 3,040 (fold-out plats, record 1495350). At the 1568 cap that
page's short edge lands at 423 px. Same defect, different paper.

**Resolution:** Geometry guard before any model call. AR > 2.0 sets
`oversize=true`; classification proceeds on a squashed thumbnail (adequate
for "this is a plat"); extraction refuses oversize pages until tiling
exists, enforced as a constructor invariant, not a convention.
**Pin:** pending, tests/tier1 geometry guard, table-driven, including the
original 1010 x 15,167 page as a case even though no such page exists in
this corpus.

---

## #2 — 2026-08-28 — Amended filings double-count permits within one record

**What happened:** One record contained the same P-17 permit twice: the
original application and an amended version filed months later, as separate
near-duplicate documents differing in the fields that matter (signature
date, amended-permit checkbox, permit number placement).

**Why it was wrong:** Naive per-document aggregation counts one permit as
two. Nothing in file metadata distinguishes amendment from original.

**Resolution:** Census and any per-record aggregation must treat
document-level counts and entity-level counts as different numbers.
**Pin:** pending, census aggregation test case (amended-P-17 fixture).

---

## #3 — 2026-08-28/29 — strict:"false" silently disabled all server-side filtering

**What happened:** fetch.py sent `strict: "false"` to getSearchImages,
hoping it meant substring matching. No working client had ever been observed
sending that value; the UI hardwires `strict: "true"`. The server responded
by ignoring every filter in the payload, dates and district included, and
returning the full 1,907,311-record archive, while echoing the submitted
filters back correctly in the response's `p` block.

**Why it was wrong:** An unobserved parameter value was assumed to mean
"less strict matching." It actually selected a broken server code path that
fails open. The parameter echo was read as confirmation of binding; the echo
comes from the request parser, not the query executor, and confirms nothing.

**Cost:** Roughly a day. The unfiltered result was misattributed to session
state, and cookie/CSRF archaeology followed before controlled
single-variable isolation found the actual cause.

**Resolution:** Two standing rules (CLAUDE.md rules 2 and, in spirit, 5):
never send an external API a parameter value not observed from a working
client without a bounded test; an echo of your input is not evidence it was
applied. `--no-strict` survives in fetch.py as an explicitly labeled
experimental flag documenting the broken path.
**Pin:** behavioral, fetch.py defaults `strict="true"` with an inline
comment citing this entry; tripwire in #4 catches the symptom class.
**Amended 2026-08-30:** fetch.py's module docstring had said "we default to
non-strict", the inverse of what the code does and of this entry, for the
life of the file. Corrected; the docstring now cites this entry too. The
inline comment 150 lines below had been right the whole time, which is why
reading the code did not surface it.

---

## #4 — 2026-08-28 — Unbounded pagination in dry-run

**What happened:** `--dry-run` with no `--max-records` had no stop
condition. Combined with #3's unfiltered result, the script began politely
paging through 1.9M records, roughly nineteen thousand requests, and was
killed by hand.

**Why it was wrong:** The stop condition lived only in `--max-records`,
which dry runs plausibly omit. Nothing sanity-checked the match count
against expectations.

**Resolution:** Three guards in fetch.py: `--max-pages` hard ceiling;
dry-run defaults to max-pages 3 when no limit is given; tripwire aborts if
`num_images` exceeds 200,000 unless `--force`, since an archive-scale count
means the filters were ignored. The tripwire doubles as the stale-token
detector.
**Pin:** behavioral in fetch.py; unit coverage pending if fetch.py grows a
test suite (deliberately deferred, delivery layer is frozen).

---

## #5 — 2026-08-29 — Response echo mistaken for filter binding

**What happened:** During #3's investigation, the response `p` block
echoing the submitted dates and district was repeatedly read as proof the
server had received and applied them, which pointed the investigation at
session state instead of the payload.

**Why it was wrong:** The echo is produced by the request parser. Parsing
and execution are different subsystems; only the result set proves binding.

**Resolution:** Subsumed into #3's rules; kept as its own entry because the
misreading, not the parameter, is what spent the day. Generalization: any
"the API repeated my input back" observation carries zero evidentiary
weight about behavior.
**Pin:** none applicable; judgment rule, recorded here and in CLAUDE.md
rule 2's origin note.

---

## #6 — 2026-08-30 — Context docs drifted from data within 24 hours

**What happened:** HANDOFF.md and CLAUDE.md recorded the corpus as closed
at 198 records / 242 files / 3,640 pages. Four additional records were
fetched at 2026-08-30 01:20, after HANDOFF was written. Actual corpus:
202 / 249 / 3,689. Found by Claude Code measuring the manifest before
proposing the classifier, rather than trusting the docs.

**Why it was wrong:** "This file stays current" was a promise with no
enforcement. Doc-recorded facts about mutable data drift by default.

**Resolution:** Tier-2 consistency test asserting the counts stated in
CLAUDE.md and HANDOFF.md against data/manifest.jsonl, so corpus changes
break the build until the docs are updated in the same change. Docs
corrected to 202/249/3,689 in the same commit that adds the test.
**Pin:** tests/tier2/test_repo_consistency.py::test_docs_state_the_corpus_the_manifest_actually_holds

---

## #7 — 2026-08-30 — The secret tripwire blocked the document that teaches you to test it

**What happened:** The first attempt to commit SETUP.md was rejected by the
repo's own pre-commit hook: `BLOCKED: staged content contains a JWT-shaped
string.` SETUP.md step 5 instructs the reader to verify the tripwire fires by
staging a fake token, and demonstrated it with a literal
`eyJ`-prefixed string. The hook scans staged content without regard to which
file it came from, so the instruction made the file carrying it unstageable.

**Why it was wrong:** The example was written as documentation and read as
payload. A guardrail that pattern-matches content cannot distinguish a secret
from a description of a secret, and documentation about secret-handling is
exactly the place where literal examples get written.

**Note:** the string was a JWT header with no payload or signature
(`{"alg":"PS512","typ":"JWT"}`), not a credential. The block was correct
anyway; the hook cannot tell, and should not try.

**Resolution:** The example now names the shape (`eyJ<20+ base64 chars>`)
instead of spelling it, and the reader types a real-looking value at the shell
where nothing scans it. The hook is unchanged: adding a path exclusion for
SETUP.md would have put a hole in the guardrail to accommodate prose, which is
backwards. CLAUDE.md rule 3 says do not work around the hook, and an exception
list is a workaround.
**Pin:** the hook itself, `.githooks/pre-commit` rule 1. It is red on the
unfixed file by construction; this entry's commit is the demonstration.

---

## #8 — 2026-08-30 — Every make target has been broken since the skeleton commit

**What happened:** `make test` fails with `Makefile:7: *** missing separator.
Stop.` So do `make fetch` and `make eval`. The recipe lines carry no leading
tab; they begin at column 0. This has been true since 8902643, the skeleton
commit that created the file. Found while trying to run the first test.

**Why it was wrong:** SETUP.md step 3 writes the Makefile from a heredoc that
is itself indented four spaces inside the document. A plain `<<'EOF'` heredoc
does not strip leading whitespace (only `<<-` does, and only tabs), so the
written file inherited the document's indentation instead of make's required
tab. The generated file looked right in the document and was wrong on disk.

Nothing caught it because nothing ran make. `python3 -m pytest` was typed
directly during setup, and no test existed to run. A build entry point that is
never exercised is not a build entry point.

**Related:** commit f759f63 edited this same Makefile to fix the interpreter
path and did not notice the file was unparseable. Reading a file is not
running it.

**Resolution:** Recipe lines rewritten with literal tabs. SETUP.md step 3
gains a warning at the heredoc. Pinned by a tier-2 test that parses the
Makefile and asserts every recipe line begins with a tab, so the next
regeneration from a document cannot reintroduce it silently.
**Pin:** tests/tier2/test_repo_consistency.py::test_makefile_recipe_lines_begin_with_tab

---

## #9 — 2026-08-30 — A 400 about my own schema was read as a fact about the vendor

**What happened:** The bounded probe (scripts/probe_haiku.py, written to satisfy
CLAUDE.md rule 2 before wiring `output_config.format`) reported:

    REJECTED: BadRequestError: 400 output_config.format.schema: Invalid
    schema: Enum value 'face' does not match declared type '["string","null"]'
    Keep the plain-JSON parser. Do not wire structured outputs.

That conclusion was about to be written into docs/modules/classify.md as a
finding about claude-haiku-4-5. It is false. Structured outputs work on that
model. The 400 was about the schema *I* sent: a nullable enum spelled as
`{"type": ["string","null"], "enum": [...values..., null]}`, which is invalid
JSON Schema regardless of vendor. Respelled as an `anyOf` union of a string
enum and null, the same request is accepted and returns
`{"form_class": "g1", "part": "face", ...}` on the first try.

**Why it was wrong:** The probe had one branch for "accepted" and one for
"anything raised", so every failure mode collapsed into a single verdict about
the feature. A malformed request and an unsupported feature are different
findings and the probe could not tell them apart. The error message named the
cause in plain words and was skimmed for its status code.

**Relation to #3 and #5:** same shape, opposite direction. #3 read a response
echo as evidence that a parameter bound. This read an error about our input as
evidence about their behaviour. Both are conclusions drawn from a signal that
was never about the thing being concluded.

**Cost:** none. The probe is two calls and cost under a cent, which is the
entire argument for bounded probes: the error was caught by re-reading it, one
minute after it was produced, before anything depended on it.

**Resolution:** The probe now tries both valid spellings of a nullable enum
and reports which one the server accepts, so "rejected" can only mean every
well-formed variant was refused. Structured outputs are recorded as available
and verified, but are NOT wired for the arm competition: constrained decoding
cannot emit an out-of-vocabulary class, which is the signal R4 exists to
surface. The decision for the census run is deferred to the measured
parse-failure rate from the smoke run.
**Pin:** the probe itself, scripts/probe_haiku.py, which now distinguishes a
rejected schema from a rejected feature.

---

## #10 — 2026-08-30 — The taxonomy was written from eight documents and missed a sixth of the corpus

**What happened:** The page-class list was drawn from the handful of records
read during recon, agreed in chat, implemented, tested, and committed. Alex
then asked three questions about how to label a page whose form is not named on
it. Answering them meant scanning the OCR text of all 3,689 pages, which showed
five form families occurring as page headers with no class to put them in:

| Form | Pages | Records |
|---|---|---|
| W-1 drilling permit | 154 | 61 |
| P-5 organization report | 147 | 65 |
| L-1 | 46 | 36 |
| GT-1 | 35 | 30 |
| W-12 | 27 | 25 |

Roughly 400 pages across more than 100 of 202 records would have been labelled
`other_form`. That class exists to reveal a gap of a few pages, not to absorb a
sixth of the corpus, and it would have absorbed them silently: every label
valid, every test green, the classifier scored against a taxonomy known to be
incomplete only after the fact.

**Why it was wrong:** A vocabulary was derived from a sample of eight documents
and never checked against the population, although the population was sitting
on disk in a form that could be scanned in thirty seconds without a model. The
recon documents were selected for being interesting, which is the opposite of
representative.

**Caught by:** a question about labelling, not by any test. Nothing in the repo
could have failed, because nothing compared the class list to the corpus.

**Two things found while fixing it, both worth their own note:**

1. The first scan under-reported every count. Its cross-reference filter listed
   a bare `on` without a word boundary, so it also matched the tail of
   "DIVISION", and "OIL AND GAS DIVISION" is the standard header block printed
   immediately before the form number. Legitimate headers were discarded
   wholesale. Found by a tier-1 test written before the corpus scan was
   trusted; the numbers reported to Alex from the first scan (68 records with a
   completion report, G-5 on 29 pages) were wrong and are corrected below.
   Same lesson as #9: the instrument gets tested before its readings are
   believed.
2. `back_instructions` guidance in docs/labeling-protocol.md was wrong in both
   directions. The pointer phrases ("READ INSTRUCTIONS ON BACK", "- OVER -",
   "REVERSE SIDE HEREOF") are printed on the *face*, and real backs
   self-identify ("Side 2", "Instructions Form G-5:", "Continued from reverse
   side"). Further, a reverse carrying a data table is a `continuation`, not
   `back_instructions`; conflating them would have discarded real data. 251
   pages carry a self-identifying back marker, and only 107 of 486 pages that
   point to a reverse side are followed by one, so a sheet is not reliably two
   pages either.

**Corrected measurements (cross-references excluded, header region only):**
72 of 202 records carry a legible G-1 or W-2 header, 36% of the corpus, against
a sufficiency threshold of roughly 80 records. A floor, not a census: OCR reads
the one known G-1 face as "F(R)lC7lbP G(o)IL" and does not count it.

**Resolution:** W-1, P-5, L-1, GT-1 and W-12 added as identity-bearing classes;
they carry operator, lease and well identity and so feed the cross-form
disagreement detector, not just the census. A tier-2 test now scans the corpus
and fails if any form appearing as a header on more than 20 pages has no class,
so the next hole is a build failure rather than a conversation. The labelling
protocol is corrected and the label set regenerated before any page was
labelled.
**Pin:** tests/tier2/test_taxonomy_coverage.py::test_every_common_form_has_a_class
and tests/tier1/test_formscan.py for the cross-reference filter.

---

## #11 — 2026-08-30 — The form scanner invented fifteen forms out of survey abstract numbers

**What happened:** Alex asked whether Form P-12, Certificate of Pooling
Authority, exists in the corpus. It does, on 15 pages across 8 records. Looking
at the band of tokens below the taxonomy-coverage threshold to answer him
showed that band was mostly not forms at all:

    A-38   "L. McLaughlin A-38 C Robertson County, Texas"
    A-92   "ELIZA PEAKS A-92 WILLIAM H NEINAST and wife"
    A-55   "WM. ROBINSON - A-55 /07J Ac."
    A-15   "BURLESON COUNTY, TEXAS JOHN COX A-15"

In a Texas land description `A-nn` is the **abstract number** of an original
land survey. Plats are covered in them. `FORM_TOKEN` matches
`[A-Z]{1,2}-\d{1,2}[A-Z]?`, so every plat contributed phantom form families:
A-1, A-5, A-6, A-11, A-12, A-13, A-15, A-18, A-22, A-30, A-38, A-55, A-69,
A-74, A-92. Others in the band were OCR misreads of real forms: the `F-4`
sample is a W-15, `I-1` is a W-1, `F-17` is a P-15, `A-13` is a W-2.

**Why it was wrong:** The regex encoded the shape of a form number without any
notion of which prefixes the RRC actually uses, on a corpus whose defining
feature is that it is full of land descriptions.

**The part that matters more than the bug.** The tier-2 coverage threshold was
set at 20 pages and justified in the test as "the largest legitimately
unclassed token sits at 15". That number was P-12, a real form, and nothing had
established it was legitimately unclassed. The threshold was drawn just above
the largest thing it needed to exclude, and the noise it was really suppressing
was this bug. A threshold chosen to make the current data pass is not a
threshold; it is a fitted constant. It survived review because the test around
it was green.

**Caught by:** a question about one form, again, rather than by any test.

**Resolution:** `A-` is excluded outright, documented as a survey abstract
prefix and pinned with real plat text from the corpus. P-12 (certificate of
pooling authority), P-15 (statement of productivity of acreage assigned to
proration units) and G-6 (application for exception to statewide rules 28
and/or 32) are added as identity-bearing classes; all three are genuine RRC
forms carrying operator, lease and field identity. The coverage threshold drops
to 10 now that it is filtering forms rather than noise, and its docstring
states what it is for instead of restating the current data.
**Pin:** tests/tier1/test_formscan.py::test_survey_abstract_numbers_are_not_forms
and ::test_a_prefixed_token_is_rejected_even_beside_the_word_form

---

## #12 — 2026-08-30 — A commit claimed "100 tests green" while the suite was red

**What happened:** Commit f809730 ends with the line "100 tests green." The
suite at that commit was 99 passed, 1 failed. The commit was made by:

    make test 2>&1 | tail -2 && git add -A && git commit ...

A pipeline's exit status is that of its **last** command. `tail` succeeds
whether or not `make` did, so `&&` proceeded over a failing suite, and the
summary line was copied from the previous run's habit rather than from the
output on screen.

**Why it was wrong:** Two failures compounding. The mechanical one is that
`cmd | tail` cannot gate anything. The one that matters is that a commit
message asserted a measured number nobody measured, in a repository whose
entire argument is that every claim is backed by something. A false green is
worse than a red build: red is visible.

**Related:** the same shape as #5 (an echo of input read as evidence of
binding) and #9 (an error about our own schema read as evidence about the
vendor). A signal was trusted to mean something it did not mean.

**The gap underneath it.** CLAUDE.md rule 6 says tier-2 tests run "on commit".
Nothing made that true. `.githooks/pre-commit` checked for secrets, `data/`
and oversized files, and never ran a test. The rule was a description of
intent that no mechanism enforced, which is how a red commit was possible at
all.

**Not corrected in place.** f809730 is unpushed, and SETUP.md permits
rewording an unpushed message, but the following commit a1adaa2 already states
"The previous commit went in red" in its own message. The history is
self-correcting and honest as it stands, and CLAUDE.md rule 4 says dead ends
stay. Rewriting it would remove the evidence that this happened.

**Resolution:** the pre-commit hook now runs tiers 1 and 2 and refuses the
commit if they fail, making rule 6 true rather than aspirational. Test-gating
via a pipe is not a habit to fix by resolving to be careful.
**Pin:** .githooks/pre-commit, rule 5.

**Amended 2026-08-30, later the same day.** The paragraph above says the
commit was not corrected in place. It since was, at Alex's request. The false
"100 tests green" line is gone and the message now says nothing about the
suite at all, which is what an honest author would have written that evening
having not noticed the failure. Only the message changed: the trees before and
after are byte-identical, verified by comparing tree hashes across the
rewrite, and `git filter-branch` renumbered the commits from that point.

Rewriting was permitted here and is nowhere near a habit: the commits were
unpushed and private, SETUP.md allows rewording an unpushed span, and what was
removed was a false factual claim rather than an inconvenient true one.

The record of the failure is not thereby lost. It lives in this entry and in
the following commit's own message, "The previous commit went in red", which
is where it belongs. A commit message narrating its own editing would have
been a fourth copy and a strange thing to read in a log.

---

## #13 — 2026-08-30 — The arm competition reported the losing arm as the winner

**What happened:** The first real run of scripts/run_arms.py printed, in this
order:

    vision_1000 vs text: +16.1%
      5pp rule:  clears
      paired:    9 pages disagree (0 only text right, 9 only vision_1000
                 right), p=0.004
      distinguishable at n=60

    vision_1568 vs text: +13.0%
      ...  p=0.109   NOT distinguishable at n=60

    WINNER: text
    Cheapest by rule: no gap survived the paired test.

A gap had survived. vision_1000 beat the cheapest arm by 16 points at p=0.004,
which is exactly the case the rule was written to admit.

**Why it was wrong:** The contested loop ran after the winner had been chosen
and reset `winner = cheapest` for *any* costlier arm that failed the paired
test, without checking whether that arm was the one that had won. One
inconclusive comparison discarded a decisive result from a different arm.

The summary line then asserted "no gap survived the paired test" four lines
under a printed p of 0.004. Same failure as #12: a claim in the output that
the output itself contradicts.

**What it would have cost:** the census, roughly $4, is gated on this verdict
and runs once. It would have run on the arm that was 16 points worse, and the
verdict would have been quoted in the README as a measured decision.

**Why the flag existed at all.** The paired test and the loud flag were added
on Alex's instruction that a gap inside the n=60 error bar must not be
overridable on a hunch. The instruction was right and the implementation
inverted it: instead of stopping an unproven arm from winning, it stopped a
proven one.

**Resolution:** decision logic extracted from the reporting code into
`decide()`, a pure function taking ranked arms, scores and paired results and
returning the winner plus the contested list. Contested now means "clears 5pp
but is not distinguishable", which is a flag on that arm alone and never a
veto over another arm's proven win. A gap under 5pp is not contested, merely
unremarkable, or the flag would fire on every run.
**Pin:** tests/tier2/test_arms.py, four cases covering a distinguishable win
alongside a contested arm, cheapest winning when nothing is distinguishable,
a sub-5pp gap not being flagged, and the best distinguishable arm winning
rather than the first.

**Where the fix actually landed.** Not in a commit of its own. `git add -A`
swept the `decide()` implementation into 463b41e, whose message describes only
the failing test for DEFECTS #14. So a commit labelled "failing test" contains
a substantive fix for a different defect, and `git log --oneline` misdescribes
it. Recorded here rather than corrected, because the history had already been
rewritten twice this session and a third pass to tidy a message is exactly the
cleanup temptation SETUP.md warns about.

`git add -A` has now muddled two commits in one session: this one, and the
earlier one that swept in a stray second copy of the label set. SETUP.md's
commit-mistake list already says to prefer `git add -p` or explicit paths and
to glance at `git status` before every add. The rule was there; following it
was the missing part.

**Measured outcome of the fix.** The corrected run scores every arm on the 55
pages all three labelled, rather than on the 58, 59 and 57 each managed
separately, and reports parse-failure rates as their own number. vision_1000
wins at 83.6% against text at 67.3%, +16.4pp, p=0.004. vision_1568 reaches
78.2% and remains unsettled against text at this sample size (p=0.109). The
pre-registered rule therefore selects vision_1000, and the earlier run's
"WINNER: text" was wrong.

---

## #14 — 2026-08-30 — A cached result did not behave like a fresh one

**What happened:** The first arm run tolerated 9 unparseable model responses
out of 280 pages, recording each on its Attempt and carrying on, which is what
a 280-page run should do. Re-running to regenerate the report from cache, with
no new API calls, crashed on the first of them:

    ValueError: form_class='back_instructions' is not one of: g1, w2, ...

**Why it was wrong:** `classify_page` has two paths. The live path wraps
`parse_response` in try/except and puts the failure on the Attempt. The
cache-hit path, added at the same time and three lines above, called the same
parser bare. The cache therefore changed behaviour rather than only saving
time, and the change only appeared on the second run.

The point of the cache (CLAUDE.md rule 7) is that an unchanged pair is never
re-inferred. That is worth nothing if reading the cache is riskier than
calling the API. It also made the run unrepeatable: fixing a reporting bug and
re-printing the results was impossible without re-spending, which is exactly
when a cache should pay off.

**Resolution:** one parse, one guard, shared by both paths. Pinned by tests
asserting that a malformed cached response yields the same Attempt as a
malformed fresh one, and that the commonest real failure, the model answering
with a `part` value in the `form_class` field, does not raise on replay.
**Pin:** tests/tier2/test_classify.py::test_a_cached_malformed_response_behaves_like_a_fresh_one
and ::test_a_cached_out_of_vocabulary_class_does_not_raise

---

## #15 — 2026-08-31 — A form that names other forms in its own instructions

**What happened:** Sizing the stage-2 strata meant cross-tabulating the census
predictions against the OCR header scan. The scan put a `G-1` header on 80
pages. 35 of those are predicted `l1`, and the L-1 face carries this in its
top block:

    ELECTRIC LOG ... STATUS REPORT
    When the L-1 is NOT required
    • with Forms W-2, G-1, and GT-1 filed for injection wells,
    ...
    • with Form W-3 for plugging of other than a

Every form number after the first bullet is a reference. All of them counted
as headers.

**Why it was wrong:** `CROSS_REFERENCE` was built from the P-4 trap in
DEFECTS #11, where a form mentions one other form in one field, and it has two
holes that pattern never exposed.

1. The wording list has `filed with` but not bare `with`, and the trailing
   group is `(FORM\s+)?`, which does not match `Forms `. A plural reference is
   not a reference. Every phrase in the list leaks the moment a form names two.
2. Nothing carries the reference status along a list. Only `W-2` follows the
   cross-referencing words; `G-1` and `GT-1` are separated from it by a comma
   and an `and`, and were judged on their own as if they stood at the top of
   the page.

The deeper mistake is the same one as DEFECTS #10: the rule was written from a
document that mentions one other form, and the corpus contains a form whose
purpose is to list the forms it is filed alongside. A single example decided
the shape of the rule.

**Measured footprint:** across all 3,689 pages, 116 tokens were references
counted as headers.

| Token | Reported | Actual |
|---|---|---|
| G-1 | 80 | 51 |
| W-2 | 109 | 84 |
| W-3 | 88 | 51 |
| GT-1 | 35 | 10 |

No other token changed. The OCR floor that guards the census headline is
records carrying a legible G-1 or W-2 header: **72 reported, 68 actual**, over
four records (1493639, 2086531, 2306415, 2396691) whose only completion-report
evidence in OCR was an L-1 citing the forms.

**What it did not change:** nothing downstream. The census headline is 115
records with a completion report, verified 15 of 15 by hand; it clears 68 as
comfortably as it cleared 72, and the sufficiency threshold of 80 is unmoved.
`fetch.py` stays closed. This is a wrong number in a guard, found before the
guard was ever the thing standing between a decision and a mistake.

Two numbers in prose were wrong in a second, unrelated way: docs/modules/
classify.md quotes the floor as 71 where pipeline/census.py has always said
72. A transcription slip, corrected in the same commit as the real one.

**A hazard left standing:** `scan_corpus` caches to `data/form_headers.json`
keyed on nothing at all. A scanner change does not invalidate it, so the fixed
scanner returns the broken counts until somebody deletes the file by hand.
Deleted in the fix commit. Not solved: CLAUDE.md rule 7 keys the model cache on
(document hash, prompt hash) and this cache has no equivalent, which is a real
gap and not this defect.

**Resolution:** bare `with` added to the wording, `FORMS?` for the plural, and
a token separated from a cross-referenced token by nothing but list punctuation
inherits its status. Header counts, `OCR_FLOOR_RECORDS` and the classify.md
figure corrected to the measured values.
**Pin:** tests/tier1/test_formscan.py::test_a_plural_reference_is_still_a_reference,
::test_with_form_is_a_reference, ::test_the_rest_of_a_list_inherits_the_reference,
and ::test_the_l_1_face_reports_only_its_own_number, which is the real OCR of
the page the leak was found on.

---

## #16 — 2026-08-31 — The same leak, one OCR space wide. Open.

**What happened:** #15's fix was measured and the measurement was reported as
the truth: G-1 on 51 pages, W-2 on 84. Cross-tabulating the fixed scanner
against the census immediately afterwards found 18 pages the census calls `l1`
still carrying a G-1 or W-2 header. The counts in #15 labelled "Actual" are
still over.

**Why it was wrong:** the same L-1 instruction block, imaged a little worse:

    When to file the L-1
    • with Forms G- 1, W-2, and GT- 1 for new an

`FORM_TOKEN` requires `G-1` with no space, so `G- 1` never matches. The list
inheritance added in #15 chains a token to the *previous matched token*, and
here the previous token is one the pattern could not see. `W-2` therefore looks
like the head of its own list rather than the middle of someone else's, and the
lookback window sees `• with Forms G- 1, `, which ends in a comma and matches
no cross-reference wording. One space in a scan defeats the fix.

The general lesson is the one worth keeping: a rule that reasons about the
relationship between two tokens fails silently whenever the tokenizer misses
one of them. #15's fix assumed the tokenizer was complete on a corpus whose
own docstring says the OCR is bad enough to read "FORM G-1" as "F(R)lC7lbP
G(o)IL".

**Measured footprint:** 18 pages, all but one predicted `l1`. Records reaching
the OCR floor: the scanner says 68, and 66 survive dropping every page the
census calls `l1`, so the floor is over by at most two records.

**Why it is not fixed here.** The obvious fix is to let the token pattern
tolerate a space around the hyphen. Measured across all 3,689 pages, that is
not a small change: P-12 goes 15 -> 39, W-3 51 -> 72, G-1 51 -> 69, W-15
87 -> 93, and fifteen tokens appear that are not forms at all (E-0, X-0, I-3,
J-11L). It moves counts in both directions and needs a validation of its own,
which is a different piece of work from the milestone in hand. Recorded and
left open rather than half-done under time pressure.

**What it costs while open:** `OCR_FLOOR_RECORDS` is 68 where the true figure
is 66 or 67. The guard fires when the census comes in *below* the floor, so an
inflated floor is conservative in the safe direction: it can raise a false
alarm, it cannot hide an under-count. The census headline of 115 is unaffected.

For stage-2 labelling, the OCR header token is a design variable on the
`g1`/`w2` face strata only, and the leak's mechanism is a page listing the
forms it is filed alongside. Checked directly: of the 75 completion faces whose
OCR header agrees with the model, **0** carry "status report", "when to file",
"where to file" or "instructions" in their header region. The variable is safe
where it is used, which is a measurement rather than an assumption.

**Resolution:** none. Open, with its footprint measured and its blast radius
bounded.
**Pin:** pending. The case is real OCR from page 1506991-0-7: header_tokens on
"When to file the L-1 • with Forms G- 1, W-2, and GT- 1 for new an" must
return {"L-1"} and currently returns {"L-1", "W-2"}.

---

## #17 — 2026-08-31 — Completion reports that predate the form numbering

**What happened:** stage-2 labelling put 7 of 105 scored pages in `other_form`
with a note rather than a class. Alex's wording, verbatim from the sheet:

    Form 3, a precursor of the named forms.
    Form 2, a precursor of the named forms.
    Form GWT-1, a precursor of the G-1 form.

All 7 are pages the census called a G-1 or W-2 face. All 7 carry a **legible**
printed form number. The model read a number that has no class, and mapped it
to the nearest one that does.

**Why it was wrong:** the taxonomy was built from forms that carry a modern
RRC number. This corpus reaches back far enough to contain the completion
report before it was called G-1 or W-2, and nothing in the class list can
express that. Third time in this project: DEFECTS #10 missed five families
because the list came from recon documents, #11 missed three more under a
threshold fitted to the data, and this one misses a whole era.

R4 exists to make an unknown class surface rather than hide, and it did not
fire, because the model never emitted an unknown class. It emitted `g1`, which
is in the vocabulary and wrong. **A guard on the parser cannot catch a
taxonomy gap the model papers over on its own.**

`pipeline/formscan.py` cannot see these pages either, and not by accident:
`FORM_TOKEN` is `[A-Z]{1,2}-\d{1,2}[A-Z]?`, so `FORM 3` has no hyphen and
`GWT-1` has three letters. Both return the empty set. The header scan that
exists to check the taxonomy against the corpus is structurally blind to the
family it most needed to report. Verified directly against `header_tokens`.

**Measured footprint:** 5 of 22 in stratum A and 2 of 25 in stratum C, which
weights to **7.9% +/- 2.6pp of the 238 predicted completion faces, about 19
pages**. None in the OCR-corroborated strata B and E, where the printed number
is one the scanner recognises, which is consistent with the mechanism rather
than a separate result.

**What it does and does not change.** It does not damage the census headline.
"115 of 202 records contain a completion report" is a claim about records
holding a completion report, and a Form 3 gas well record is one; the 15-of-15
hand verification already accepted such a page, on record 1494409, where Alex
wrote "it seems this is before the time where these forms had their current
names". It does damage the per-form split further, and in a way the stage-2
precision numbers already absorb: these pages count as errors there, correctly,
because the page is not a G-1.

**Resolution:** none yet. Deliberately: the prompt correction is a gated step
and this changes what that correction has to do. The choice is a new class for
the pre-numbering completion family against a broader `completion_report`
class with the form number as a field, and that is a schema decision for the
extraction milestone, not a patch.
**Pin:** the scanner half is pinned, 2026-08-31:
tests/tier1/test_formscan.py::test_a_bare_numbered_form_is_a_form,
::test_a_lowercased_form_word_still_carries_its_number,
::test_a_three_letter_form_prefix_is_a_form, with
::test_a_three_letter_prefix_standing_alone_is_not_a_form and
::test_a_bare_number_does_not_swallow_a_hyphenated_one as the guards. The
taxonomy half closed the same day: `completion_face_legacy` owns FORM 2,
FORM 3 and GWT-1, pinned by
tests/tier1/test_abstention.py::test_the_pre_numbering_forms_now_have_a_class.
Record 1493455 page 16 remains the fixture, and its text layer cannot be used.

---

## #18 — 2026-08-31 — A protocol promised a number its own allocation cannot produce

**What happened:** docs/labeling-protocol-stage2.md lists five things stage 2
would compute. The fifth is "accuracy per self-reported confidence bucket,
which R6 requires before any threshold is put on that value". The draw returned
119 `high` pages, 9 `medium`, and **0 `low`**, out of 66 low-confidence pages
in the corpus.

**Why it was wrong:** the metric was written into the protocol, and the
allocation that had to feed it was designed separately. A low-confidence
stratum was considered while sizing the strata and dropped, on the correct
ground that it buys nothing for the G-1 versus W-2 question: the 53
low-confidence pages outside the completion strata are mostly `other_nonform`.
What was not done was to go back and strike the metric it fed. The two halves
of the same document were allowed to disagree.

Every predicted G-1 face in the corpus is `high` confidence with no alternative
class offered, so the confidence signal was never going to explain these
errors. That is worth knowing and is not what the protocol claimed to deliver.

**Measured footprint:** the R6 table gains `high` 61/119 and `medium` 0/9 from
this sample and no `low` row at all. R6 stays unretired, and no threshold may
be put on a self-reported confidence, which is what it says anyway.

**Resolution:** recorded, not patched. Filling the low bucket needs pages drawn
for that purpose; that is a stratum in a future sheet, not a reinterpretation
of this one. The protocol's metric 5 is answered "partly, and here is the part
that is missing" rather than quietly reported as if complete.
**Pin:** none possible. This is a claim in a document, and the tier-2 test that
would catch it does not exist; the honest pin is this entry.

---

## #19 — 2026-08-31 — The guard turned a wrong answer into no answer

**What happened:** the abstention re-run put parse failures at **13 of 143
pages, 9.1%**, against 0.4% on the census. Seven of the thirteen are one new
message:

    w2 claims a specific form number on a page where no form number can be
    read. Use completion_face_unknown_form instead.

The model answered `w2` while reporting `form_number_legible: false`. R13's
constructor invariant refused the label, `classify_page` recorded a parse
failure, and the page produced nothing at all.

**Why it was wrong:** the design intent, written into
docs/modules/classify.md the same day, was that such a page becomes an
abstention. What it actually becomes is absent. An abstention is a page the
census still counts, in a class that still joins the record-level union. A
parse failure leaves the corpus, and the union is the thing the whole
abstention design exists to protect.

The invariant is right and the routing is missing. R13 says where the page
belongs; nothing carries it there.

**Measured, on the seven pages:** all seven are `other_form` by Alex's labels,
and on all seven Alex independently answered that the form number is illegible.
So the model's legibility answer was correct every time and only its class was
wrong, which is exactly the case `completion_face_unknown_form` was created
for. Routing rather than refusing would have produced the right label 7 times
out of 7.

An eighth failure is the same shape from the other new invariant:
`completion_face_legacy is a face; part must be face, got back_instructions`.

**Why this is not R4 being violated.** R4 exists so that an out-of-vocabulary
class surfaces as a prompt or model problem instead of being silently bucketed.
Nothing here is out of vocabulary. Both values the model returned are legal;
they contradict each other, and the contradiction has exactly one resolution,
which the taxonomy already names. Resolving a contradiction between two valid
answers is not the same act as inventing a class for an invalid one. The
distinction is worth keeping sharp, because "we already coerce in one place" is
how R4 would eventually be lost.

**Resolution:** none yet. Proposed and awaiting a decision: `parse_response`
resolves the contradiction to `completion_face_unknown_form`, records that it
did so on the Attempt, and the coercion rate becomes a reported metric rather
than a silent repair. Deliberately not written before the decision, because it
changes the meaning of a rule and rule 5 covers that.
**Pin:** pending. The case is real: a response of `form_class: "w2"` with
`form_number_legible: false` must produce a label, not an exception, and must
carry a flag saying it was resolved.

---

## #20 — 2026-08-31 — The P-4 trap was fixed by how much it removed, not by what was left

**What happened:** validating the W-15 header rule against the stage-2 labels
turned up two hand-labelled G-1 faces, records 1760703 page 6 and 1495392
page 6, whose OCR header carries a `P-5` token. A general "the header token
wins" rule would have overturned both, so the rule was scoped to W-15 alone.

Measuring the token that caused that gave a worse answer than the two pages
suggested. Across the corpus, 147 pages carry a `P-5` header token, and the
census classifies them:

    76 p4    31 w1    16 w15    7 p12    4 w2    3 g1    3 other_form
     3 letter_memo

**Zero** of the 147 are classified `p5`. Meanwhile the census finds 21 `p5`
pages, and `formscan` gives a `P-5` token to none of them. The two sets are
disjoint.

**Why it was wrong:** DEFECTS #11 named this exact sentence as the cause. Field
3 of a completion report, and the equivalent field on a P-4, W-1 and W-15,
reads "OPERATOR'S NAME (Exactly as shown on Form P-5, Organization Report)".
`CROSS_REFERENCE` was extended to catch it and the count fell from 373 pages to
147, which was recorded as the fix.

147 was never checked against anything. It is not the number of P-5 headers in
this corpus; on the evidence above it is approximately all of the remaining
leak. The OCR is what defeats the filter: on record 1760703 the phrase reads
"as shown n..Form P-5", and on 1495392 the line break leaves only
"P-5. Organization Report)" with no cross-referencing words in front of it at
all. The lookback window has nothing to find.

The lesson is the one the fix itself should have applied. A filter was
validated by the size of the drop, and nobody asked what the residue was. That
is the same shape as DEFECTS #16, where a fix was measured and reported as
"actual" while a second mechanism kept 18 pages leaking, and as DEFECTS #15
before it. Three entries in one day for the same habit: measure what the fix
removed, do not measure what it left.

**Consequences, and what they are not.** Nothing above it changes. The W-15
rule was already scoped away from this, `p5` is not an extraction target, and
the tier-2 coverage threshold is unaffected because P-5 has a class either way.
What is wrong is a committed number: `data/form_headers.json` reports P-5 on
147 pages, and `docs/labeling-protocol.md` repeats it in prose as "P-5 on 373
pages when it is on 147".

**Resolution:** logged now, fix deferred by agreement. The fix is not another
phrase in `CROSS_REFERENCE`, since the OCR breaks the phrase itself; it needs a
different signal, most likely that a token appearing in a field label rather
than in the top-right corner is not a header, which is a geometry question the
text layer cannot answer.
**Pin:** pending. Two real cases: `header_tokens` on the OCR of record 1760703
page 6 and record 1495392 page 6 must not return `P-5`.
