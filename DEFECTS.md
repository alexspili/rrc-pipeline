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

---

## #21 — 2026-08-31 — A cost estimate priced against a different model

**What happened:** the Sonnet extraction probe measured one two-page
completion document at **$0.0775 standard, $0.0388 batched**. HANDOFF had
carried `~$0.17/doc at Sonnet standard $3/$15 (intro $2/$10 ended
2026-08-31)` since the recon session.

$3/$15 per 1M tokens is `claude-sonnet-4-6`. The model this pipeline uses is
`claude-sonnet-5`, which is **$2/$10**. The "intro price that ended" was never
an intro price; it is the current price of the current model. Two models'
rates were merged into one line and the wrong half was labelled standard.

**Why it was wrong:** the figure was written from memory during recon, before
any call had been made, and nothing checked it afterwards. CLAUDE.md rule 8
says numbers in prose are measured or absent; this one was neither, and the
`~` in front of it did not make it a smaller claim than it was.

**Measured footprint:** the estimate was 2.2x the measured cost. The error has
two parts and they point in the same direction: the price was 1.5x too high,
and the token counts behind the estimate were guessed.

Worth recording that a second estimate, made today in the extraction proposal
and explicitly labelled an estimate, was wrong the other way: it put the
document at $0.04 by assuming ~1,200 output tokens where the real answer is
6,559. Both estimates were wrong by about 2x in opposite directions, which is
the argument for probing rather than for estimating more carefully.

**What the measurement also showed:** output tokens are 85% of the cost, so
image resolution barely moves it. Input at a 1000px cap is 2,947 tokens and at
1568px is 5,975, a difference of about $0.006 per document. Extraction can
afford the resolution its accuracy needs.

**Resolution:** HANDOFF now carries the measured figure and names the model and
the rate it was priced at. `scripts/probe_sonnet.py` is the measurement, in the
same posture as `scripts/probe_haiku.py` for the classifier.
**Pin:** none available. A price is an external fact and no test can hold it.
The guard is procedural: a cost figure in prose names the model and the date it
was measured, or it does not appear.

---

## #22 — 2026-08-31 — One form, two spellings, two classes

**What happened:** the 20-document smoke run returned `form_class` as `g1` on
two documents and `g-1` on two others. The extraction schema took whatever
string arrived, so those are two different classes to every count, group and
join downstream, and nothing would have said so.

**Why it was wrong:** the classifier's `form_class` is a closed enum validated
by `_enum` against `PageClass`. The extraction schema was written the same day
and validated only that the field was a non-empty string. The prompt names the
values, which is a request, not a constraint, and DEFECTS #19 is the same
lesson from the same week: a prompt can be ignored and a constructor cannot.

**Measured footprint:** 4 of 20 smoke documents, 2 of them spelled the way the
taxonomy spells it and 2 not. No number has been published from this run, so
nothing downstream is wrong yet. It was found before the ground truth was keyed
rather than after, which is the only reason it is cheap.

**A second answer worth keeping.** The same run returned `w15` on record
1494847, which the census called a W-2 face and the stage-2 labels confirm is a
W-15 cementing report. That is out of the two values the prompt asked for and
it is correct: extraction is a second opinion on the classifier, and R4's
principle applies here too. So the fix normalises spelling and validates
against the whole `PageClass` vocabulary, rather than against the two classes
the prompt happens to request. Narrowing it to g1 and w2 would have thrown away
a true finding.

**Resolution:** `form_class` is normalised (case, surrounding space, hyphens)
and must be a `PageClass` value; anything else raises.
**Pin:** tests/tier1/test_extract.py::test_form_class_spelling_is_normalised
and ::test_a_form_class_outside_the_taxonomy_is_refused.

---

## #23 — 2026-08-31 — The regression anchor is also an eval document

**What happened:** record 1493495 is document 1 of the 15-document
ground-truth set, and it is also the document I read page by page while
designing the extraction schema, the document `scripts/probe_sonnet.py`
measured, and the anchor deliberately forced into the smoke draw so the coded
path could be compared against the probe.

Its true values are quoted in this repository: in commit messages, in
docs/modules/extract.md, and until this entry in
tests/tier1/test_validate.py, which used its Section II depths as a
"well-formed depths" fixture.

**Why it was wrong:** HANDOFF's eval design says dev fixtures are not the eval
set, hold the eval set out, and do not look at it while iterating. Document 1
fails all three from my side. Alex is keying it blind from page images, so his
labels are uncontaminated; the contamination is that I have read the document
in full, written its values down, and built a schema around what it contains.
An accuracy figure that includes it is measured partly against a document the
schema was fitted to.

The two decisions that produced this were each individually right. Reading a
real document before proposing a schema is what stopped the schema being
invented from HANDOFF's prose. Forcing the probe document into the smoke draw
is what proved the coded path reproduces the probe. Nobody checked what
happens when the same document is then drawn into the eval set, which is
standing rule 9's shape again: each step was validated, the interaction was not.

**Measured footprint:** 1 of 15 ground-truth documents. The other 14 are
documents I have never opened.

**Resolution:** the fixtures are scrubbed, so no true value for any eval
document sits in the repository. Document 1 stays in the sheet, because it is
the anchor and because dropping it mid-keying would waste work already done,
and **accuracy is reported with and without it**, exactly as stage 2 reports
accuracy with and without the pages already seen during census verification.
The number that goes anywhere public is the one computed without it.
**Pin:** none possible in code; this is a property of how a sample was drawn.
The procedural guard is the reporting rule above.

---

## #24 — 2026-08-31 — A protocol that could not express a fifth of its own sheet

**What happened:** Alex, part way through keying the extraction ground truth,
asked what to record when a W-2 has no second page and the completion data
lives on a reverse nobody imaged. Document 13, record 1511465.

The four statuses had no answer. `not_on_this_form` asserts the 1975 W-2 has no
total depth field, which is false. `blank` asserts an operator left it empty,
which is also false. The truth is a third fact: the field exists, on a page
this document does not contain.

**Measured footprint:** **9 of the 15 ground-truth documents are face-only, so
90 of the 405 rows.** Not an edge case; 22% of the sheet.

**Why it was wrong:** docs/labeling-protocol-extract.md says "the document is
all of its pages together: where a field appears on any page of the document,
it is present." That was written from the documents that have their second
page, and never asked what happens to the ones that do not. HANDOFF has said
since the recon session that only 107 of the 486 pages carrying a "reverse
side" pointer are actually followed by one, so this was knowable before a
single row was keyed.

Standing rule 9's shape, on the rule's own author: the multi-page case was
validated against documents that had a second page, and the residue was not
characterised.

**Resolution:** a fifth status, `page_not_in_document`. Both sides determine it
from the same evidence and neither guesses: the W-2 face prints "if well is
newly completed or recompleted, fill in reverse side also", and the reverse is
not among the pages given. It also buys a measurement worth having, which is
how often the model says a section is absent rather than inventing `blank`.

The extraction prompt changes with it, which invalidates the result cache, so
the 20-document smoke run has to be repeated at about $1.41 before scoring.
Deferred until the keying is finished rather than run under it.
**Pin:** tests/tier1/test_extract.py::test_a_field_on_a_page_nobody_imaged_has_its_own_status
and ::test_the_missing_page_status_is_not_the_missing_field_status. The
absent-status tests now parametrise over every non-present member so the next
addition cannot skip them.

---

## #25 — 2026-09-01 — The pairing heuristic only ever looked forward

**What happened:** Alex, keying the extraction ground truth, reported that
document 6 has no first page: record 1495193 page 8 is a section of a
completion report whose face is page 7, and only page 8 is in the document.

Checking the other fourteen the same way, **three of the fifteen documents sit
immediately after another completion face**: documents 6, 8 and 9, records
1495193 page 8 and 1495195 pages 6 and 38. All three are probably sections
separated from their faces.

**Why it was wrong:** `scripts/smoke_extract.py` builds a document as a
predicted face plus the next page when the census calls that page a
continuation. It never asks whether the predicted face is itself a
continuation whose face precedes it. The census's own numbers said this would
happen: stage 2 measured `w2` face precision at 44% before the corrections and
57% after, so roughly two in five predicted faces are not faces, and a
forward-only heuristic has no way to notice.

The heuristic was documented as a placeholder for the reassembly step, and it
was checked in the direction it looks. Standing rule 9 again: what it does not
look at was never characterised.

**What it costs.** Three of fifteen ground-truth documents are partial in the
opposite direction from the nine face-only ones. Their identity fields are
`page_not_in_document`, which is a real and gradeable answer, but it means
identity accuracy on those three measures absence detection rather than
extraction.

**Resolution for the sheet:** none. The frame is frozen and Alex is keying
against it; changing which pages a document contains mid-keying would discard
work and re-open a frame that was deliberately closed. Identity accuracy is
reported on the twelve documents that carry their own face, and the three are
reported separately as absence detection. That is the same shape as the
with-and-without reporting for DEFECTS #23.

**Resolution for the pipeline:** the reassembly step, which is not built, must
pair in both directions and settle candidates by agreement on the identity
fields both pages carry, not by position. This entry is evidence for that
design rather than an argument to patch the placeholder: record 1495195 alone
supplied three of the fifteen documents and two of them are suspect, and
record 1511465 has three W-2 faces in one file with a section between two of
them.
**Pin:** pending, on the reassembly module. The case is record 1495193: pages
7 and 8 must resolve to one document, and pages 7 and 9 must not.

---

## #26 — 2026-09-01 — A generator that destroys the work it generated for

**What happened:** the extraction prompt changed when `page_not_in_document`
was added, which invalidated the result cache, so the 20-document smoke run
was repeated. `scripts/smoke_extract.py` writes the ground-truth template at
the end of every run. The sheet had been keyed by hand in the meantime.

**405 hand-keyed rows were replaced with blanks.**

They came back with `git checkout` because they had been committed twenty
minutes earlier. That is the only reason this is a log entry rather than a day
of somebody's work gone.

**Why it was wrong:** the script does two things whose lifetimes are different.
Running extraction is repeatable and expected to be repeated. Writing the
template is a once-per-frame act. They were in one function because they
happened in one sitting, and nothing marked the second as unrepeatable.

The failure needed a specific sequence: draw the frame, key the sheet, change
the prompt, re-run. Every step was reasonable and the combination was
destructive. Standing rule 9's shape yet again, on a script rather than a rule:
each half was checked, the interaction was not.

**Why the commit discipline is the thing that saved it.** CLAUDE.md rule 4 says
commit small and in sequence. The labels were committed as their own change the
moment they validated, before anything else was touched, so recovery was one
command with nothing else to untangle. A habit that exists for reviewability
turned out to be the backup.

**Resolution:** `pipeline/guard.refuse_if_filled` raises rather than
overwriting a sheet with any filled row. One row is enough; a threshold would
be a judgement about whose work is worth keeping. A missing column is an error
rather than a free pass, because a guard that silently passes when it cannot
find what it checks reports safety it did not verify.

Not a warning and not an automatic backup. The generator simply cannot do it
any more, which is the same move as R13 in the classifier: a prompt or a flag
is a rule, and a raised exception is a constructor.
**Pin:** tests/tier1/test_template_guard.py, six cases including the
single-filled-row case and the missing-column case.

---

## #27 — 2026-09-01 — "This form" meant two things on a partial document

**What happened:** scoring the first extraction run, 32 of the 42 status
disagreements in the headline slice are between the two statuses that both mean
"no value here for a reason": `not_on_this_form` and `page_not_in_document`.
They run in both directions, 20 one way and 12 the other, which is the
signature of an ambiguous rule rather than of a model that is wrong.

The clearest case is documents 8 and 9, record 1495195 pages 38 and 6. Alex
labelled all 15 identity fields `not_on_this_form`; the model answered
`page_not_in_document` on 22 of the 30. Both readings follow the protocol.

**Why it was wrong:** docs/labeling-protocol-extract.md defines
`not_on_this_form` as "this form revision has no such field at all" and
`page_not_in_document` as "the form has this field, on a page you were not
given". On a complete document those are unambiguous. On a section page
separated from its face, **"this form" means either the form family, which is
a W-2 and does have a lease name field, or the page in front of you, which is
a Section II and does not.**

The protocol was written for whole documents and then applied to partial ones,
which is standing rule 9 in the place it keeps landing: the case that was
thought about was checked, the case that was not thought about was not.

**Measured footprint:** 32 of 333 headline fields, 9.6%. Collapsing the two
into one "absent" category takes status agreement from **87.4% to 97.9%**, so
the model and the labeller almost always agree on whether a value is there and
disagree about why roughly one time in ten.

**A second finding inside the first.** On documents 6, 8 and 9 the model
returned seven identity values as `present` where the sheet says the page is
absent, among them an operator name and two completion dates. A W-2 Section II
does carry the operator, in field 26, "Notice of Intention to Drill this Well
was filed in Name of". So the model may be right and the blanket instruction I
gave, that identity fields on a faceless document are all
`page_not_in_document`, may be too broad.

If it is right, it is also the premise the reassembly design rests on: a
section page carries enough identity to be matched to its face. That is worth
confirming by eye on two or three fields before it is treated as established.

**Resolution:** none applied to the numbers. Relabelling after seeing a score
is the thing this project exists not to do, so the run is reported as scored,
with the collapsed figure beside it and this entry naming the cause. The
protocol needs a sentence defining "this form" as the form family, and the
prompt needs the same sentence, before the next run.
**Pin:** none in code; this is a definition. The guard is that both numbers are
always reported together.

---

## #28 — 2026-09-01 — Two readers assumed a record has one file

**What happened:** wiring the validation rules over the extracted documents,
two of the twenty missed the result cache. Records 1494847 and 1510666 were
drawn from **file index 1**, and both `scripts/validate_extract.py` and
`scripts/score_extract.py` opened `files["files"][0]`.

The cache key is (document hash, prompt hash), so hashing the wrong PDF looks
under a key nothing was written to. The reader would then have demanded a fresh
paid run, or, with an API client in hand, quietly extracted and validated a
document nobody had scored.

**Why it was wrong:** the corpus has been documented since the recon session as
202 records over 249 files, with one record holding five. The page id format,
`record-file-page`, exists precisely because a record has files. Both scripts
parsed the record out of that id and dropped the field beside it.

**Measured footprint:** 2 of 20 documents in the validation pass. **Zero in the
scoring pass**, because none of the fifteen ground-truth documents happens to
come from a second file. That is luck, not design, and it is the kind of luck
that turns into a wrong headline number the first time a redraw goes
differently.

**A related gap it exposed:** the ground-truth sheet carries a record id and
page numbers and no file index, so the sheet alone does not identify its own
documents. Page 9 of one file has nothing to do with page 9 of another.
Recovering it meant joining the sheet back to the run that produced it.

**Resolution:** both readers take the file index from the page id. The template
generator now writes a `file_index` column, so the next sheet identifies its
documents without needing the run. The current sheet is keyed and stays as it
is; scoring joins back to the run to recover the index.

Same commit fixed a second reader problem with the same shape: a results file
that did not record which prompt produced it. The prompt changed after the run,
and scoring a finished run then looked under the current prompt's key and found
nothing. Results now carry their own `prompt_hash` and readers use the recorded
one, so a finished run stays readable for free after the prompt moves on.
**Pin:** pending. Both are script-level and the honest pin is a tier-2 test that
reads a two-file record end to end, which needs the extraction fixtures that do
not exist yet.

---

## #29 — 2026-09-01 — Well-formedness is not groundedness

**What happened:** Alex checked the nine provenance crops at full resolution
and reported that the box does not land on the field it names. He was right,
and the diagnosis went further: the values are grounded and the geometry is
confabulated.

- On document 1 the casing row's cell boxes abut perfectly, edge to edge, in
  one identical y band: a schematic of a form, not a reading of a page.
  Scalar boxes drift downward one to two field-rows.
- Crop 08: the claimed operator, Gulf Oil Corporation, is genuinely written on
  the page in field 26; the box sits on field 28, two rows below.
- Crop 02: the box sits on field 18; field 14, the one it names, is directly
  above it with handwriting in it.
- The one field whose true position is known a priori on every form,
  `form_revision` in the top-right corner, is boxed correctly and tightly:
  centre (0.907, 0.079) +/- 0.02 across 14 documents. The model localizes the
  structural landmark and confabulates inside the dense body.

**Why it was wrong twice over.** The schema validated boxes for shape,
fractions in range and positive area, and reported "0 malformed", which said
nothing about whether a well-formed box points at anything. Then the eyeball
check cropped each page to the model's own box, so the reviewer was shown the
wrong region and the check tested the model against itself.

That is the third instance of one failure class: evidence generated by the
thing under test. DEFECTS #5, the archive echoing filters its executor never
applied; these boxes, shape-valid and ungrounded; and the crop check, which
inherited the boxes' errors and could only confirm them.

**Measured footprint, 2026-09-01, over the finished smoke run:**

- `geometry.schematic_grid`, now a permanent WARNING in pipeline/validate.py,
  fires on 8 table rows across the 20 documents.
- Snap coverage, `scripts/snap_coverage.py`: the embedded text layer's word
  boxes can locate 30.8% of present values under conservative matching, and
  the number follows the era gradient the value accuracy follows: 48-75% on
  Rev. 4/1/83 forms, under 21% on 1966-1975 paper, tables (22.8%) worse than
  scalars (38.0%). The residue is any fallback's load and Textract's ceiling.
- The read-vs-invented question the crops were meant to settle is reopened
  and moves to whole-page overlays (`scripts/overlay_boxes.py`).

**Resolution:** the sufficiency claim in docs/modules/extract.md ("a highlight
that lands on the right field is sufficient") is withdrawn until the box
grading measures what the boxes actually deliver; the protocol for that
grading is pre-registered before Alex grades. Design rules already fixed for
whatever follows: a snap happens only on a unique or decisively disambiguated
match, never a nearest-guess, because a wrong snapped box looks grounded; and
`Region` will carry a source tag (model | text_layer | page) that stays
visually distinct all the way into the viewer.
**Pin:** tests/tier1/test_geometry.py, whose fixture is document 1's real
casing row, plus the pre-registered grading protocol. The detector is
permanent output precisely because a regression into schematic geometry would
otherwise be silent.

---

## #30 — 2026-09-03 — Three rules abstained for reasons that were not facts about the paper

**What happened:** building the Rev. 7/5/66 template, three separate rules in
`pipeline/template.py` declined to locate fields. Each looked like the
mechanism honestly reporting that the paper would not support a box. None of
them was.

1. **The value-region rule ran the wrong way.** It was declared, before
   building, as a band from the label's right edge to the next anchor on its
   line. This form family prints the label in a ruled cell's top-left corner
   and the operator types the value **underneath** it: "6. LOCATION (Section,
   Block, and Survey)" sits at y 0.272 and its value at y 0.287. The rule
   returned bands 0.02 page-fractions wide that contained nothing.
2. **Label agreement was isotropic**, one threshold of 0.15 for both axes, so
   it was wrong in both directions at once. Too tight for a printed phrase:
   "6. LOCATION (Section, Block, and Survey)" spans 0.16 in x, so its own
   three anchors were ruled to disagree and the field abstained. Too loose in
   y: two anchors 0.137 apart, nineteen line-heights, were ruled to be one
   label.
3. **A one-anchor checkbox label tied with itself.** Checkbox specs are
   clustered both as a line and as a column, and for a label resolving to a
   single anchor those two groups are the same group. The tie-break, which
   exists so that two genuinely competing lines abstain rather than being
   settled by proximity, read that identity as a tie and abstained.
   `completion.type_of_completion` was located, then silently dropped.

**Why this is one entry and not three.** They share a cause: each rule was
written from an idealized picture of a form rather than from the paper in
front of me, and each failed in the direction that produces an abstention.
Abstention is the safe direction for a wrong box and the dangerous direction
for a measurement. All three were quietly lowering the probe's coverage,
which is the probe's headline number.

**Measured footprint:** the face template went from 6 of 12 fields located to
8 of 12, and `completion.type_of_completion` came back on the Section II
template. The ceiling the verdict is read from is 18 of 35. The verdict did
not change, because 18 is below both the pre-registered bar of 26 and the
comparator's 19. But these were moving the number the verdict is read from,
and moving it in the direction that would have killed the idea for the wrong
reason.

**The general form, which is the reason this is logged.** A mechanism that
can abstain has a failure mode a mechanism that always answers does not: its
bugs look like honesty. "The paper does not support this" and "my rule is
wrong" produce the same output, and only one of them is a finding. So an
abstention rate is not evidence until the abstentions have been read
individually. Every abstention in this probe was diagnosed by name before the
ceiling was reported: 13 of the 17 are labels missing from the canonical
anchor table, 2 are labels whose every token is shorter than the four
characters an anchor needs ("Top of Pay", "P.B. Depth"), and 2 more were
checked and are not recoverable.

This is the mirror of DEFECTS #29. There the model was confidently wrong and
the shape check called it well-formed. Here the mechanism was wrongly silent
and the silence looked like integrity.

**Resolution:** all three fixed, each with the tier-1 test that pins it,
written from the real anchor positions that exposed it. The diagnosis loop is
now permanent output rather than a one-off: `scripts/probe_boxes.py` prints
every abstaining field with its snap outcome and its model-box grade beside
it, so an abstention can never again be counted without being read.
**Pin:** tests/tier1/test_template.py — `test_the_region_is_the_cell_the_label
_corners`, `test_a_long_printed_phrase_resolves_along_its_line`,
`test_two_lines_carrying_one_token_each_abstain`, and
`test_a_one_anchor_checkbox_label_is_not_a_tie_with_itself`.

---

## #31 — 2026-09-03 — A pre-registration with two decision clauses is not a pre-registration

**What happened:** the stage-four grading protocol was written before the
sheet was drawn, which is the whole point of it. It contains a rule table
saying the template passes at **14 or more of 18**. Later the same day, while
recording a measurement caveat about oversized table bands, I wrote a second
sentence: "the twelve-scalar rate is the number that decides the Textract
question."

Both were committed before any box was graded. Neither was written as a
revision of the other. The result then split them:

| | |
|---|---|
| pooled, the numbered clause | 13 of 18 — **fails** |
| scalars, the unnumbered clause | 10 of 12 — **passes** |

**Why it was wrong:** I did not notice I was writing a second decision rule.
I thought I was writing a caveat about how to read a number. A sentence that
names which figure decides an outcome is a decision rule whatever section it
sits in and whatever else it is doing.

**How it was resolved, and this is the part that matters.** The numbered
clause governs, so the verdict is inconclusive and the AWS escalation stays
shut. That is the failing reading. **The clause I discarded was the one that
opened the door.**

The reason is not that pooled is a better metric than scalars; it might well
be worse, and the case for scalars was written down honestly before the
result existed. The reason is that only one of the two clauses ever had a
number attached to it, so only one of them could produce a verdict rather
than a preference. Choosing the other one after seeing which way each fell is
the exact failure the protocol exists to prevent, and no amount of being
right about metrics would repair it.

**A second thing, also against interest.** The same caveat predicted the
oversized table bands would be biased **toward** `hit`, on the reasoning that
a big box is easy to land. They graded 3 hit, 0 near, 3 miss: worse than the
scalars, and with no middle at all. A band covering a seventh of a page
either contains the value or is nowhere near it. So the prediction was wrong
in direction, and the pooled 13 was not inflated by the big boxes. My caveat
argued for discounting a number that turned out not to need discounting.

**The general form.** Pre-registration is not a ceremony about writing things
down early. It is a bet that you will accept a rule you no longer like. A
pre-registration containing two rules has already failed at that, because it
leaves a choice to be made at exactly the moment when you know which choice
you want. **The only test of whether you meant it is which clause you pick
when they disagree.**

**Resolution:** every grading stage in the protocol now carries exactly one
block marked `**DECISION RULE:**`, and a tier-2 test enforces that count. A
second decision clause becomes a failing test instead of a discovery made
after the result is in.
**Pin:** tests/tier2/test_repo_consistency.py::test_each_grading_stage_has_exactly_one_decision_rule

---

## #32 — 2026-09-03 — A unique text match is not a correct match

**What happened:** the snap tier locates a value by finding its text in the
PDF's embedded text layer and boxing the word it matched. Its safety rule,
settled after DEFECTS #29, is that it only asserts geometry when the match is
unique, because a wrong box that looks grounded is worse than an honest band.

On record 1493608 page 5, `identity.field_name` snapped to the word `Frio` at
y 0.30. That is field 12, "If Workover give former Field", whose value reads
`8400' Frio now isolated`. Field 1, the field name, is at y 0.17 and its value
is `Bay City (8000' Frio)`.

**`Frio` is printed twice on that page.** The OCR read one of the two
cleanly. So the uniqueness test passed on a word that is not unique on the
paper, and the tier asserted geometry on the surviving copy.

**Why it was wrong:** uniqueness was tested against the OCR's word list and
treated as a fact about the page. **The text layer's omissions manufacture
uniqueness.** Every word the OCR drops makes some other word look
unrepeated, and the degraded pages where the safety rule matters most are
exactly the pages that drop the most words.

**Measured footprint: at least 1 of 15** graded snap boxes on this document.
Recorded as a floor and never as a point estimate. Two reasons. That box was
graded `near` rather than `miss` only because the overlay hid it (#33), so
the grader was reasoning about a rectangle he could not see. And six other
fields carried a box from both mechanisms and the same occlusion risk, so an
unknown number of wrong-field snaps may be sitting inside `hit` grades.

**Resolution: none. Recorded as a measured limitation, not fixed.** The
provenance thread is closed and inventory-level repairs are permanently out
of scope. What does change is that the failure stops being silent: the
displayed region becomes the whole printed run the matched word sits in, so a
reader sees `8400' Frio` under a caption reading "Field name" and can tell it
is wrong. A one-word box gave them nothing to notice with.

Note what this does to a number the repo quotes. The snap tier passed its
stage-four rule at 14 hits of 15, and the same sitting produced a confirmed
wrong-field snap. Both travel together from here.
**Pin:** tests/tier2/test_textlayer.py::test_the_ocr_drops_one_of_two_printed_instances_of_frio

---

## #33 — 2026-09-03 — The instrument for grading geometry could not display geometry

**What happened:** Alex's note against box 1 of the stage-four sheet: "Can't
really see where box 1 is, I assume it's matching the first digit from box 15
and the boxes are identical." He graded it `near` on that assumption.

Box 1 and box 15 are the same field from the two different mechanisms. Box 1
is a single word; box 15 is a form cell that contains it. Drawn in the same
colour with the number always at the top-left corner, the small one is
invisible inside the large one.

**Why it was wrong:** the overlay's entire job is to show a human where a
rectangle is, so that they can judge whether it is in the right place. It
could not do that for a nested pair, and it gave no sign that it had failed.
The grader had to notice and say so.

**Measured footprint:** 7 of the 33 boxes were fields carrying a rectangle
from both mechanisms, so seven pairs were at risk. One is known to have
failed, because the grader said so. The others cannot be ruled out, which is
why #32's rate is recorded as a floor.

**The class.** DEFECTS #29 was evidence generated by the thing under test:
the crop check cropped to the model's own box and could only confirm it. This
is the neighbouring failure and it is worth separating. Here the instrument
did not generate the evidence, it **failed to display** it, and the grade
came back looking exactly like a grade.

**Resolution:** one shared drawing routine, used by both overlay scripts
rather than copied into each. Larger boxes are drawn first so a nested small
one lands on top. Each number label is placed at the first candidate position
that collides with no label already placed. Outline colour cycles by the
number printed on the box, and **never** by size, source or draw order: on a
blinded sheet a snap box is a word and a template region is a cell, so a
colour keyed to size would encode the mechanism and end the blind through the
back door.
**Pin:** tests/tier1/test_overlay.py, and
tests/tier2/test_overlay.py::test_a_nested_box_is_still_visible_after_the_big_one_is_drawn,
which asserts on pixels rather than on intent.

---

## #34 — 2026-09-03 — The guard fired after the deletion it was guarding against

**What happened:** found by a design review while planning the fixes above,
before it did any damage.

`write_sheet` in `scripts/probe_boxes.py` empties its output directory and
then, thirty lines later, calls `refuse_if_filled` to check whether the
grading sheet already carries grades.

    PROBE_OUT.mkdir(parents=True, exist_ok=True)
    for stale in PROBE_OUT.glob("*"):
        stale.unlink()                    # <- the answer key dies here
    ...
    refuse_if_filled(PROBE_SHEET, "grade")   # <- the guard runs here

The sheet is fully graded right now. Re-running `--sheet` would therefore
delete `KEY_do_not_open_until_graded.csv` and both graded overlay images, and
only then raise `RefusedToOverwrite`. The key is the only record of which
mechanism drew which box; without it the 33 committed grades cannot be
scored, and a tier-2 test that reads it cannot run. The key lives under
`data/`, which is git-ignored, so `git checkout` would not have brought it
back the way it brought back the 405 rows in #26.

**Why it was wrong:** `refuse_if_filled` was written for #26 and placed
correctly there, immediately before the write it protects. Here it was placed
immediately before the write it protects **again**, and the destructive act
had been put somewhere else. A guard protects the statement it precedes, not
the function it lives in, and the directory wipe was never anybody's idea of
a write worth guarding.

The near miss is the point. Alex's approved verification step for #33 was to
redraw the overlays and check by eye that the two boxes are now both visible.
Carrying out the approved plan would have destroyed the evidence the plan
exists to protect.

**Measured footprint:** none. Nothing was lost. The key and both overlays
were copied to a scratch directory before anything ran, and the entry is
being written before the fix rather than after a recovery.

**Resolution:** `refuse_if_filled` moves to the first statement of
`write_sheet`, before the directory is touched. The general form is the one
#26 already paid for and this entry sharpens: **a guard belongs at the top of
the operation it protects, not next to the last dangerous line somebody
happened to think about.**
**Pin:** tests/tier2/test_probe_sheet_guard.py::test_a_graded_sheet_refuses_before_the_output_directory_is_touched,
which fills a sheet, populates the directory, calls `write_sheet`, and asserts
the directory is intact after the raise.

---

## #35 — 2026-09-03 — The same two-clause failure, in a document the fix did not look at

**What happened:** DEFECTS #31 was logged at midday: a pre-registration
containing two decision clauses is not a pre-registration, because it leaves a
choice to be made at the moment you know which choice you want. The
resolution was a `**DECISION RULE:**` marker and a tier-2 test counting them.

Two hours later I wrote `docs/labeling-protocol-reassemble.md` and did it
again.

Its decision rule moves the threshold if either of two things fires, and the
second is **"it fails to attach two or more of the three DEFECTS #25 read-out
cases"**. The paragraph immediately below it reads **"Coverage is reported and
decides nothing. A run that attaches nothing and is wrong about nothing is a
legitimate outcome of this rule."**

A run that attaches nothing fails the second bullet. The two statements
cannot both be true, and Alex caught it by reading, not the test.

**Why the fix for #31 did not catch it.** The test I wrote scans sections
headed `## Box grading, stage N` in one file. The reassembly protocol is a
different document with no stage sections, so the scan found nothing to
check and passed. **The fix was scoped to the shape of the instance rather
than to the shape of the failure.** A rule that only holds where the last
example happened is not a rule, and this is the second time in one day that a
guard turned out to be standing in the wrong place (#34 was the first).

**A second error inside the first, and it is not a duplication.** The rule
responds to *either* failure by moving the threshold from 2 to 3. Tightening
is a coherent answer to attaching a page to the wrong face. It is an
incoherent answer to failing to attach a page that belongs, which tightening
makes worse. I wrote one response for two failures pointing in opposite
directions.

**What it would have cost.** Nothing yet: no measurement has run. Had it run,
the module could have attached nothing at all and I could have reported that
as a pass, quoting the sentence about coverage deciding nothing. Alex named
the reason it matters in one line: precision alone cannot choose a threshold,
because attach-nothing passes at any strictness.

**Resolution:** the protocol is amended before any measurement, two-sided,
with must-attach cases named individually and a response that depends on
which direction the failure points. The offending sentence is kept verbatim
and marked superseded, on the same reasoning as #31: a pre-registration that
edits out the clause it failed to honour is worth nothing.

The `**DECISION RULE:**` marker and its test now apply to **every** file
matching `docs/labeling-protocol-*.md`, not to one file's section headings.
**Pin:** tests/tier2/test_repo_consistency.py::test_every_protocol_marks_its_decision_rules
and ::test_no_protocol_decides_an_outcome_outside_a_marked_rule

---

## #36 — 2026-09-03 — The ignore rule that protects the corpus removes the safety net from everything else

**What happened:** raised by Alex as the structural lesson behind #34, which
was a guard that would have deleted a sealed answer key before refusing.

`.gitignore` excludes `data/` because the fetched PDFs carry surface owners'
names, addresses and phone numbers, and that rule is not negotiable. But the
answer key to a blinded grading sheet was also written under `data/`, and it
is not corpus imagery. It is a hand-made artifact that took a sitting to
produce and cannot be regenerated once the sheet it explains has been graded.

So it inherited an exclusion written for a different reason, and with it lost
the only recovery path this repo actually relies on. DEFECTS #26's 405 rows
came back with one `git checkout`. The key would not have.

**Why it was wrong:** the ignore rule answers "does this contain personal
data". It was allowed to answer "is this worth keeping", which is a different
question with a different answer, and nothing in the layout made the
difference visible. Everything under `data/` looks equally disposable from
the outside, and most of it genuinely is.

**Resolution:** irreplaceable hand-made artifacts live in `tests/fixtures/`
and are committed. The key carries field names, box coordinates and a source
tag, and no corpus imagery or personal data, so it relocates. Anything that
does carry imagery stays under `data/` and its tooling copies it out before
any destructive operation, which is enforced by the guard ordering that #34
established rather than by anybody remembering.

The general form: **an exclusion written for one reason must not be allowed
to decide a different question.** `data/` means "may contain personal data".
It has never meant "safe to lose".
**Pin:** tests/tier2/test_box_grades_probe.py::test_the_answer_key_is_committed_not_ignored

---

## #37 — 2026-09-03 — The module trusted a label the corpus had already measured as wrong

**What happened:** the first measurement of reassembly failed its own pin.
Record 1495193 page 8 is a section of the completion report whose face is
page 7, and the module attached it to nothing.

The cause is not the threshold and not the identity reader. **The census
classified page 8 as a `g1` face**, and the module only offers non-face pages
as candidates, so page 8 was never eligible to attach to anything. It became a
single-page document of its own. Case B cannot pass at any threshold with any
reader.

**Why it was wrong:** the module takes the classifier's `face` label as fact.
Stage 2 measured face precision at **44%, and 57.4% after the corrections**,
so it is wrong roughly two times in five.

And the evidence was not somewhere else. It is in DEFECTS #25, the entry this
module exists to satisfy, in the sentence I quoted while building it: "record
1495193 page 8 is a section of the W-2 whose face is page 7, **and the census
called page 8 a `g1` face**." I read that sentence, used the first half as the
test case, and built the module on the assumption the second half denies.

**Measured footprint:** on the ground-truth set, 63 of 122 pages were treated
as faces and therefore ineligible. Allowing a face to be a child opens 242
further pairings, of which 18 attach at the current threshold, and those 18
are 9 mirrored pairs: page 9 wants page 11 and page 11 wants page 9.

**How the measurement behaved, which is the reason it was found.** The
pre-registered rule named two explanations for a failed confirmed case, a
reader problem or a page that genuinely lacks two agreeing fields. The real
cause was neither. A rule that enumerates the outcomes it expects can be wrong
about the list, and the response to that is to inspect rather than to pick the
nearest listed option. Recorded beside the rule rather than corrected out of
it.

**Resolution:** a face may also be a child. The parent is the page carrying
more identity fields, on the reasoning that a real face carries the identity
block and a mislabelled section carries less. Ranking is
`(fields carried desc, page asc)`; a face may only become a child of a face
ranked above it, and a face that becomes a child leaves the parent pool. That
makes the mirrored pairs impossible by construction rather than by a
tie-break applied afterwards, and keeps documents flat rather than chained.

**What it does not fix, stated with it:** case B still fails. Pages 7 and 8
agree on operator and lease and disagree on completion date, `10-2-79`
against `8/30/79`, and date can reject a pair. Eligibility was one of two
reasons the pin failed. The other is open pending a reading of the paper.
**Pin:** tests/tier1/test_reassemble.py::test_a_mislabelled_face_attaches_to_a_richer_face
and ::test_the_richer_of_a_mirrored_pair_is_the_parent

---

## #38 — 2026-09-03 — A non-present value carrying its own text

**What happened:** `pipeline.identity.parse` built a `Value` with status
`illegible` and raw text `'2:-73-67'`. The `Value` constructor refused it: a
value that is not `present` carries no text.

**Why it was wrong:** the parser took the model's `raw` field and attached it
whatever the status said. `pipeline/extract.py` has handled this since it was
written, and the new reader was written without carrying the rule across.

**Measured footprint:** 1 page of 123. It surfaced as a raised exception that
the measurement script caught per page and counted, so the page was dropped
rather than silently mis-read.

**What is worth more than the instance.** The constructor caught this, which
is the whole reason the invariant lives in a constructor rather than in a
comment. This is the same shape as R11 and R12: a prompt or a convention is a
rule, and a raised exception is a constructor.

**Resolution:** text is dropped when the status is not `present`, matching the
extractor.
**Pin:** tests/tier1/test_identity.py::test_a_non_present_value_carries_no_text

---

## #39 — 2026-09-03 — A written "not applicable" was allowed to contradict

**What happened:** on record 1912687 the identity reader returned a completion
date of `present` with raw text `'N/A'`. Reassembly then compared that against
a real date on another page, found them different, and vetoed the pair.

**Why the first diagnosis was wrong, and this is the point of the entry.** I
logged this as a reader defect: the reader should have said `blank` or
`not_on_this_form` instead of returning a value. Then I read the protocol the
reader follows. **The operator wrote "N.A." on the paper.** The labelling
protocol says to key what is written. So the reader was right, and reporting
it as a present value with that text is exactly correct.

The defect is one layer down. **Reassembly allowed a value that means "there
is no value" to act as evidence of disagreement.** A field where one page says
`N/A` and another gives a date is a field where one page is silent, which is
`unknown`, not a contradiction. Treating it as a contradiction lets a page
that declines to answer veto a true pairing.

**Measured footprint:** 1 of 421 present values across the run, 0.2%.

**Why the fix goes where it goes.** A prompt change would invalidate the
identity cache and cost another run. A comparison change is free, is
deterministic, and is where the error actually is. The measured rate did not
decide this; the diagnosis did, and the rate only says the cost of being
wrong about it is small either way.

**Resolution:** normalisation in `pipeline.reassemble` returns `None` for a
declared list of written non-values, so they compare as `unknown` and can
neither agree nor contradict. Declared and listed, not a similarity judgement.
**Pin:** tests/tier1/test_reassemble.py::test_a_written_non_value_cannot_contradict

---

## #40 — 2026-09-03 — I gave the reader six field names and no idea what they mean on the paper

**What happened:** Alex read record 1495193 pages 7 and 8, which is the pin
this whole module exists to satisfy, and settled two questions at once.

**Page 8 is not a G-1 face.** It is headed SECTION II, it carries no form
number in the top right, and it is the second page of the W-2 whose face is
page 7. The census called it a `g1` face. DEFECTS #25's reading is confirmed
off the paper, and so is #37's premise: the classifier's `face` label is not
something a module may treat as fact.

**And `8/30/79` is the "Completed" date.** The field beside it is "Commenced",
reading 8/12/79. Those are the two halves of "Date Plug Back, Deepening, Work
Over or Drilling Operations Commenced / Completed". They are **not** field 14,
"Completion or recompletion date", which is the field `completion_date` means
and which lives on the face, reading 10-2-79.

**So the veto was right and the value was wrong.** Reassembly refused to join
pages 7 and 8 because their completion dates differed. They differed because
the reader had put a different field's value in the box. The date veto is not
too strict; it fired correctly on two genuinely different numbers, one of
which should never have been there.

**Why it was wrong:** the identity reader's prompt lists six bare field names
and defines none of them:

    Return ONLY these six fields, as JSON:
      operator_name, lease_name, well_number, completion_date, rrc_district,
      total_depth

A model shown a Section II with "Commenced" and "Completed" printed on it, and
asked for a "completion date", will read the Completed date. That is a
reasonable reading of an unreasonable instruction.

And the definition already existed. docs/labeling-protocol-extract.md defines
`completion_date` as field 14, "Completion or recompletion date", and defines
`drilling_commenced` and `drilling_completed` separately as the two halves of
the operations field. **I wrote a new reader against a schema the repo had
already written down precisely, and did not carry the definitions across.**
The same mistake as #38, which dropped an invariant the extractor already had,
in the same file, on the same day.

**Measured footprint:** 26 of the 48 non-face pages in the ground-truth set
report a `completion_date`. Some of those are legitimate, since a section can
repeat the date, and some are this defect. Which is which cannot be told from
the output, only from the paper, so the honest number is that **up to 26 of 48
are suspect** and one is confirmed.

Completion date was the single largest cause of rejection in the measurement,
42 pairs of 54. An unknown part of that is this defect rather than the paper.

**Resolution:** every field in the prompt gets the printed label it means,
taken from the labelling protocol, and `completion_date` is told explicitly
that it is not the Commenced/Completed pair. That changes the prompt, so the
identity cache is invalidated by construction, which is CLAUDE.md rule 7
working as intended rather than an inconvenience.

**Predicted before re-running, so the re-run tests a prediction rather than
producing one:** page 8 will return `completion_date` as `not_on_this_form`;
case B will then agree on operator and lease with no contradiction and will
attach to page 7 for the first time; and the count of date-based rejections
will fall from 42.
**Pin:** tests/tier2/test_identity_prompt.py::test_the_prompt_defines_every_field_it_asks_for

---

## #41 — 2026-09-03 — A pre-registered case that could not fail

**What happened:** case E of the reassembly measurement is "record 1495193
page 8 must not attach to page 9". It passed in both measurements and I
reported it as a pass twice.

Page 9 is a **W-12**. This module only considers completion faces and their
sections and `other_form` pages. A W-12 is neither a face nor a candidate, so
it was never in the running, and case E cannot fail whatever the module does.

**Why it was wrong:** the case came from DEFECTS #25's pin, "pages 7 and 8
must resolve to one document, and pages 7 and 9 must not", which was written
about scan order rather than about this module's candidate set. I copied it
into the protocol as a must-not-attach case without checking that the module
could ever attach those two pages.

**What it cost:** one of six pre-registered cases carried no information, and
was counted twice as evidence that the module does not over-attach. The
over-attachment side of the measurement is now thinner than it looked: what
remains is case F, "no wrong attachment anywhere", and only 2 of 17
attachments can be checked against ground truth.

**Resolution:** case E is marked as decided by construction and is not counted
as evidence. It stays in the protocol rather than being deleted, because a
pre-registered case that turned out to be vacuous is worth seeing.

A replacement is needed and is not invented here: it would have to be two
pages that this module genuinely could join and that are known not to belong
together, and finding one needs the paper.
**Pin:** none in code. The protocol carries the annotation.

---

## #42 — 2026-09-03 — A wrong-field read is invisible whenever the two fields agree

**What happened:** the identity reader was taking values out of the wrong
printed box, and the measurement reported it as working.

On record 1495193 page 8 it read the "Completed" half of the drilling
operations field, `8/30/79`, into `completion_date`, whose real value on the
face is `10-2-79`. Those differ, reassembly's veto fired, and the pin failed.
That failure is how the defect was found (#40).

On record 1493495 page 10 it made **the same mistake** and nobody could tell.
Field 30 on that page reads "Commenced 8-16-77, Completed 9-22-77", and the
face's completion date is `9/22/77`. **The wrong field held the right number.**
So case A attached, and I reported it as a pass twice.

The same thing happened to `lease_name` on the same page, from the other
direction: "State Tract 130" is printed on page 10 inside field 32,
"Location of Well Relative to Lease Boundaries", in the phrase "Line of The
___ Lease". The loose prompt found it and the corrected prompt refused it,
and in between nobody knew which box either answer had come from.

**Why this is its own entry and not part of #40.** #40 is the instance: one
field, badly specified. This is the class, and the class is worse than the
instance. **A value read from the wrong box is indistinguishable from a value
read from the right box, in every output the pipeline produces, whenever the
two boxes happen to hold the same thing.** It shows up only when they differ,
which means it shows up on some documents and hides on others, and the ones it
hides on look like successes.

Two "passes" in the first two measurements were of this kind. They were not
evidence the module worked. They were two fields agreeing by coincidence.

This is the same shape as DEFECTS #29 one layer up. There a box was
well-formed and pointed nowhere, and "0 malformed boxes" measured shape rather
than landing. Here a value is well-formed and comes from the wrong box, and a
matching value measures agreement rather than provenance. **In both cases the
output cannot distinguish the good case from the bad one, and the check that
was supposed to catch it was reading the wrong property.**

**Resolution:** the reader now returns `found_in`, the printed label it took
each value from, so a wrong-field read is at least *checkable* rather than
invisible.

**What `found_in` is not, recorded with it because the last time this lesson
was learned it cost a milestone.** It is a claim by the model about its own
reading, exactly as the provenance boxes were, and it is no more
self-verifying than they were. It does not prove a value came from that box.
Its job is to make the error visible to a human who checks, and to make
deterministic impossible-source flags possible later if they turn out to be
free. It is not evidence on its own and must never be reported as if it were.

**Measured footprint:** 2 of the 4 pre-registered must-attach cases were
affected, one failing and one passing for the wrong reason, across two runs.
**Pin:** tests/tier1/test_identity.py::test_a_value_carries_the_printed_label_it_came_from
and ::test_found_in_is_recorded_even_when_the_value_looks_ordinary
