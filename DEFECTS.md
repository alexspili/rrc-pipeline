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

---

## #43 — 2026-09-04 — Identity fields identify the well, not the document

**What happened:** the verification sitting judged eight of reassembly's
eighteen attachments against the paper. **Five are wrong**, and three of those
five are among the four drawn at random, so this is not confined to the two
pairs that were flagged as risky in advance.

| Pair | In sample because | Verdict | Why |
|---|---|---|---|
| 1493495 p10+p9 | ground truth | yes | face and its Section II |
| 1495193 p8+p7 | ground truth | yes | face and its Section II |
| 1493608 p6+p5 | random | yes | face and back of one form |
| 1495195 p87+p52 | flagged risk | **no** | one well, two filings: initial potential and retest |
| 1495195 p114+p89 | flagged risk | **no** | same |
| 1511465 p9+p7 | random | **no** | same |
| 1510666 p3+p1 | random | **no** | same, and different Received-date stamps |
| 1912687 p6+p2 | random | **no** | back page attached across filings |

**Why it was wrong.** Four of the five failures are one pattern. Two filings
for the same well agree on **every identity field the module compares**, and
they must: same operator, same lease, same well number, same district, and the
same completion date, because the well was completed once and both filings
report that completion.

So the premise is wrong. **Agreement on these fields is evidence that two
pages concern the same well. The module reads it as evidence that they are the
same document.** Those are different claims and one does not imply the other
on any file where a well has been filed on more than once, which is most of
this corpus: 64 of the 112 files that hold a completion face hold more than
one.

The field that separates an initial potential test from a retest is
`purpose_of_filing`, the field 11 checkboxes, and it is not among the six the
identity reader collects. Alex separated them at a glance; the module has no
way to see the distinction at all.

**What made it visible, and what caused it.** These attachments did not exist
in the first measurement. They appeared when a face was allowed to be
somebody's child (DEFECTS #37), a change made to fix the module's own pin. It
bought the pin and cost precision: the first run's five attachments included
two that this sitting confirms are right and none that it confirms are wrong.

**The honest reading of the earlier numbers.** "No known wrong attachment" was
reported after runs 1 and 2 on a checkable sample of two. The sample was two
because nothing else could be checked, and the phrase was chosen carefully.
It still read as reassurance, and it was reassurance about a module that was
wrong five times in eight.

**Resolution:** none applied. Per the pre-registered rule the corpus spend does
not happen and the failure pattern goes back to Alex before anything runs. The
threshold is not the problem and is not moved. A proposal exists and is
recorded in docs/modules/reassemble.md rather than implemented, because the
evidence for it comes from the same eight pairs that would judge it.
**Pin:** tests/tier1/test_reassemble.py::test_two_filings_for_one_well_are_not_one_document

---

## #44 — 2026-09-04 — Letting a face be a child let two faces become one document

**What happened:** DEFECTS #37 allowed a page the classifier calls a face to
become another face's child, because the classifier is right about faces only
44% of the time and the module was treating that label as fact. It fixed the
pin. It also created every one of the two-filings-in-one-document errors that
the verification sitting then found (DEFECTS #43).

Both halves are true and they are not in tension. **A page mislabelled a face
must be allowed to be a child. A page that really is a face must not.** The
change made no distinction between them, so it bought one and paid for the
other.

**What the sitting measured**, and it is the cleanest split in the whole
thread:

| Verdict | What the pair joins |
|---|---|
| yes, yes, yes | a first page and a **back** page |
| no, no, no, no | two **first** pages |
| no | a first page and a back page, wrong parent |

Every join of two real first-pages is wrong, four times out of four.

**Why the fix was not available in September's design and is now.** Telling a
real face from a mislabelled one needs to know which printed boxes a page's
values came from, and until `found_in` was added on 2026-09-03 (DEFECTS #42)
nothing recorded that. A real face cites "2. LEASE NAME" and "3. OPERATOR'S
NAME". A back page cites "Notice of Intention to Drill this Well was filed in
Name of" and "Location of well, relative to the nearest lease boundaries".

**Resolution:** a page the classifier calls a face may become a child only
when its own cited boxes say it is a back page. Pages the classifier already
calls a section or a continuation are unaffected: they were always candidates
and the classifier's error rate on *those* labels is not what #37 was about.

Keyed to the **label text, never the field number**. The same printed box is
numbered 24, 31 and 32 on three revisions of this form, so a number-keyed rule
is silently wrong on two of them.

**Stated because it is the point of the firewall:** this rule was derived from
the eight pairs Alex judged, so its score on those eight is a development
number and decides nothing. The verdict comes from a fresh sample, and its
rule is pre-registered in docs/labeling-protocol-reassemble.md.
**Pin:** tests/tier1/test_reassemble.py::test_a_real_face_may_not_become_a_child

---

## #45 — 2026-09-04 — I probed one prompt and shipped a different one

**What happened:** before spending $0.91 on adding `received_stamp` to the
identity reader, I probed it on four pages for $0.029 against Alex's own
readings. Two came back exact and the field went in.

The probe used a **stamp-only prompt**: one field, a long description of what
a received stamp looks like, nothing else. What shipped was an **eight-field
prompt** where the stamp is one item among eight.

They disagree. On record 1912687 page 2 the probe read `AUG 18 2009` and the
shipped prompt read `JUN 09 2009`.

**Neither is wrong, and that is the second defect inside the first.** The page
carries **two** received stamps: `RECEIVED RRC OF TEXAS JUN 09 2009 O&G
DIVISION HOUSTON` at the top left, and `RECEIVED CENTRAL RECORDS AUG 18 2009
AUSTIN, TEXAS` in the middle. That is the ordinary filing path, a district
office then Central Records, and the Austin stamp lands on the packet's top
page. The field asks for "the" received stamp, which is not a thing the paper
has.

**Why the probe failed at its job.** A probe exists to de-risk a spend by
testing the thing that will ship. Mine tested a different artifact, so its two
exact matches licensed nothing about the prompt that ran, and the discrepancy
only surfaced because the shipped run produced an attachment the probe's
reading would have rejected.

**What it cost.** The $0.91 run happened on a field that cannot do its job as
specified. And it is worse than a wasted field: on record 1912687 pages 2 and
6 the shipped prompt reported the same Houston stamp from both pages, so the
field *added* agreement and helped attach a pair, which is the opposite of the
veto it was added to be.

**A third thing, and it is the most useful.** Alex judged that pair wrong
during the verification sitting, and his stated reason was that the two pages
carry different received dates. He was comparing page 2's Austin stamp against
page 6's Houston stamp. Both pages carry the same Houston stamp. **A human
expert reading the paper made the same mistake the field makes**, which is
strong evidence that the ambiguity is in the document rather than in anybody's
attention, and that verdict is now back with him.

**Resolution:** open. Three options are with Alex: re-judge the pair, respecify
the field as office-plus-date compared per office, or drop it and keep
`purpose_of_filing`, which is the field the four clear failures actually turned
on. Nothing further is spent until he rules.

The general form, which stands whichever he picks: **a probe that does not run
the artifact that will ship has not de-risked anything.** It measured a
neighbour.
**Pin:** pending, on whichever resolution is chosen.

---

## #46 — 2026-09-04 — 7 of 8 on the data the rules were built from, 2 of 7 on fresh data

**What happened:** the second verification sitting judged all seven
attachments Alex had not already seen. **Two verify.** The pre-registered rule
was that every pair must, so the corpus spend does not happen.

The gap is the entry. Against the eight pairs the three fixes were **built
from**, the module scored 7 of 8. Against seven pairs it had never been shown,
it scores 2 of 7. **The firewall did the job it was put there for**: without a
fresh sample, 7 of 8 would have been reported as the result and a corpus run
would have followed it.

**The five failures are one sentence, arrived at from three directions.**

| Pair | Child | Parent | Alex |
|---|---|---|---|
| 1494690 p3+p7 | other_form face | w2 face | face of a P-4 attached to a W-2 |
| 1760703 p24+p6 | other_form face | g1 face | a different random form |
| 1912687 p8+p2 | w2 sec_iii | g1 face | — |
| 1495195 p88+p53 | w2 continuation | w2 face | both are back sides |
| 1511465 p8+p10 | g1 sec_ii | w2 face | both are back sides |

Three holes, and they are the same hole seen three ways:

1. **`other_form` pages are candidates.** The design admitted them so that a
   completion page misfiled as `other_form` could still attach. It also admits
   genuinely different forms, and a P-4 about the same well shares operator,
   lease, district and even the received stamp. Both instances are
   `other_form/**face**`, and the face of another form is another document by
   definition.
2. **A back page can be a parent.** DEFECTS #44 stopped a real face becoming a
   child and never asked the same question in the other direction. On both
   "both are back sides" pairs the parent is a back page the classifier called
   a face.
3. **A child may cross form families.** A W-2 Section III attached to a G-1
   face.

**Why this keeps happening.** #43 said the identity fields identify the well
and not the document. Every round since has fixed one way that bites and
revealed the next: two filings of one form, then two sides that are both
backs, then two different forms about one well. The fields cannot say which
*document* a page belongs to because they do not describe documents at all.

**What the sitting also showed, twice.** Alex verified one of the two correct
pairs with "punch holes match perfectly", having used the same signal in the
first sitting. The physical-sheet evidence is what a human reaches for, and it
is the thing this module does not have.

**Resolution:** open, and the decision is Alex's. The three holes collapse to
one rule — two pages are one document only when they are the same form family,
one is a real face and the other is not — and that rule would score 7 of 7 on
this sitting, which is exactly why it cannot be adopted on this sitting's
evidence. A third sitting would be needed, and each round so far has revealed
another layer.

**Resolved in part, 2026-09-04.** Two of the three holes are closed: a back
page may not be a parent, and a page the classifier calls a face may only be a
child if its own cited boxes say back page, which is keyed to `part` rather
than `is_face` because `is_face` is gated on form_class and let the first page
of a P-4 through.

**The third is NOT closed, deliberately.** A form-family rule would be keyed to
the classifier's `form_class`, and the two cases it must separate are
indistinguishable there: record 1495193 pages 7 and 8 are `w2` and `g1` and
ARE one document, which is DEFECTS #25's pin and the reason this module
exists, while record 1912687 pages 2 and 8 are `g1` and `w2` and are not. The
rule that closes the failure breaks the pin. `form_class` is untrustworthy for
exactly the reason `part` is, which was #37's lesson.

Across both sittings the rule now scores 13 of 15, and **all fifteen are
development data**, since the rule was derived from the second sitting. The
module makes seven attachments and all seven have now been judged, so **the
pool for a third sitting is empty** and no held-out check is available without
reading further records.
**Pin:** tests/tier1/test_reassemble.py::test_a_back_page_may_not_be_a_parent,
::test_a_page_of_another_form_may_not_attach, and
::test_a_child_crossing_form_families_is_a_known_limitation, which pins the
hole that is staying open.

---

## #47 — 2026-09-05 — The guard the docstring said was shared was on one path only

**What happened:** `extractor.extract_document` says in its own docstring:
"One parse and one guard shared by the cached and fresh paths, which is
DEFECTS #14's lesson: a cache that changes the answer is worse than no cache."

The parse is shared. The guard is not. The guard is the check that refuses to
treat a response cut off at `max_tokens` as a document, and it sits below the
cache-hit return, on the fresh path only.

**Why that is a defect and not a stale comment.** The guard exists because a
truncated response arrives as malformed JSON and reports itself as malformed
JSON, which sent me looking for a parser bug that was not there. Four of the
first fourteen smoke documents were truncations wearing that disguise. The
fix raised `MAX_TOKENS` from 8000 to 16000 and added the guard, and the guard
also refuses to cache a truncation, on the reasoning that the cache key does
not include `max_tokens` so a stored truncation would be served back forever
with the cap already raised.

That reasoning is right and it is only half-applied. Entries written before
the guard existed are still in the cache, and every one of them is still
served back as "malformed JSON" rather than as the truncation it is. The cache
answers differently from the live call for exactly the case the guard was
written for.

**Found by:** design review while factoring `extract_document` so the Batch
API path could share its cache and guard logic. Not by a failure. The
duplication I was about to create is what made me read the guard's position.

**Blast radius, measured, and it is not what I first wrote.** I wrote this
entry with the words "the live corpus is clean and this is a latent fault, not
damage", then measured before committing, and the measurement says the
opposite on both numbers I had guessed.

`data/extract/cache_smoke.jsonl` holds **54** entries under 54 distinct keys,
and **four** of them are stored truncations: all four at exactly 8000 output
tokens, which is the old cap. They are the four documents the cap was raised
for. They were never evicted, because the cache file is append-only and
nothing has been written over those keys.

What limits the damage is not the guard. It is that all four sit under prompt
hash `cbaf1068fc56d59c`, two prompts ago, so today's reader does not look under
their keys. That is luck, and it is luck with a documented way of running out:
`recorded_prompt_hash` exists precisely so a finished run can be read back
under the hash it was made with (DEFECTS #28). Anything that re-reads that run
walks straight into all four.

The lesson is the one standing rule 9 keeps making: I described the residue
before measuring it, and got both the count and the verdict wrong in the
direction that made the fault sound smaller.

**Fix:** the guard moves above the cache-hit return, so a cached truncation
and a fresh truncation give the same answer. `MAX_TOKENS` is named in the
error message either way, which means a cached truncation reports the cap in
force now rather than the cap in force when it was stored. That is the
useful direction: it tells you the run needs repeating under today's cap.

**Pin:** tests/tier2/test_extract_batch.py::test_a_cached_truncation_is_still_a_truncation

---

## #48 — 2026-09-05 — The run said "over 19 records" while reading 108

**What happened:** `scripts/measure_reassemble.py` opens every run with a line
saying what it is about to read:

    say(f"{len(wanted)} pages over {len(RECORDS)} records\n")

`wanted` is the page set actually being read. `RECORDS` is the hard-coded tuple
of the nineteen records the module was developed against. The two halves of
that sentence came from different places, and only one of them followed the
`--all` flag that was added so the read could cover the whole corpus.

So the corpus run printed **"532 pages over 19 records"**. The page count is
right. The record count is the length of a constant. The 532 pages come from
**141 records**, and the 218 documents the run built span **108** of them.

Both of those are worth stating, because I got them the wrong way round on
first pass and wrote 108 into this entry as the header's correct value. It is
not: the header describes what was read, so it is 141, and 108 is the separate
and also interesting fact that a third of the records read yielded no document
at all.

**Why it matters more than a cosmetic slip.** That line is the header of the
report the run writes to `data/extract/reassemble_report.txt`, and it is the
first thing read when the numbers are quoted. Quoted as printed, it says the
corpus read covered nineteen records out of 202. It covered a hundred and
eight. A reader would conclude the run had not done what it was asked to do,
and the correction would arrive only if someone counted the output by hand.

The corpus-consistency guard in tests/tier2/test_repo_consistency.py was
written for the same shape of mistake — a stale count sitting next to a live
one — but it reads prose in the docs, not f-strings in scripts, so it could
not have caught this.

**Found by:** reading the run's own header before quoting it, after the header
disagreed with the 218 documents underneath it.

**Fix:** the record count is derived from `wanted`, the same set the page count
comes from, so the two halves of the sentence cannot disagree again. `RECORDS`
keeps its job of naming the development set and loses its job of describing
any run.

**What remains, per standing rule 9:** this fixes one sentence, and checking
the rest of the report found a second fault rather than a clean bill. The
document count reconciles against `reassemble.jsonl` exactly: 218 faces plus
39 attached pages is the 257 pages inside documents that the file holds. The
four failed pages are reported by the run itself and are truncations, not
silent drops. But 218 + 39 + 251 unattached + 4 failed is 512 against 532 read,
and the missing 20 are DEFECTS #49.

**Pin:** tests/tier2/test_reassemble_report.py::test_the_header_counts_the_records_it_read

---

## #49 — 2026-09-05 — Twenty pages were read, paid for, and left out of the total

**What happened:** the corpus reassembly run reports three outcomes for the
pages it read: they became a document, they attached to one, or they went
unattached with a reason. Those come to 218 + 39 + 251 = 508. Four more failed
and are named. The run read **532**.

Twenty pages are in none of the four buckets.

**Where they went.** `reassemble.group` builds its candidate list as

    candidates = [p for p in pages if p.is_candidate and not p.is_face]

A page that is neither a face nor a candidate falls out of that expression and
is never seen again. It is not attached, and it is not in the leftovers, so it
is not in the total either.

**What the twenty are:** all of them are the printed instruction backs of
forms — 15 on G-1s and 5 on W-2s, `part == "back_instructions"`. Those pages
carry no filing data at all: they are the "read this before completing the
form" side. Excluding them from attachment is correct and is not in question.

**So the behaviour is right and the accounting is wrong, which is the harder
version.** A page that should not attach and is reported as not attaching is
fine. A page that should not attach and is reported as nothing has left the
count silently, and the count is what the run is for. The run also paid to
read all twenty: they went to the model like every other page.

This is the same failure the module doc already records against `tubing` and
that R16 records in the classifier, in a third place: a drop nobody counts is
a drop nobody can argue with. It is also standing rule 9 exactly — the residue
has to be characterised before the number is quoted, and here the residue was
not even visible.

**Found by:** adding up the run's own summary before quoting it to Alex,
because the header above it had already turned out to be wrong (DEFECTS #48).
Two faults in one report, and the first one is what made me add up the second.

**Fix:** `group` returns pages it has no opinion about as a fourth outcome,
with the reason `not_a_candidate`, so every page that goes in comes out
somewhere. The run's summary asserts the sum closes against the pages read and
fails loudly if it does not, which is the only version of this fix that stops
the next such page from vanishing quietly.

**Pin:** tests/tier1/test_reassemble.py::test_every_page_that_goes_in_comes_out_somewhere

---

## #50 — 2026-09-05 — I quoted $2.61 for a run that cost $5.24

**What happened:** before the corpus identity read, I sized it for Alex and
said: 532 pages in scope, 353 of them not yet cached, **$2.61**. He approved
the spend against that number. The run has finished. The 349 pages it actually
read cost **$5.24**, which is 2.0x the quote.

**The page count was right and the price per page was half.** 349 read against
353 predicted is a good estimate of scope. $0.0150 per page against $0.0074
quoted is not an estimate of price, it is a different number.

**Where the factor of two came from.** The identity reader sends one page image
at `IMAGE_CAP = 1568`, the same cap extraction uses and deliberately not the
classifier's 1000. A 1568-px page image is about 4,000 input tokens; the run
measured 3,975 per page. My quote was built on roughly half that, which is
what a 1000-px image costs. I priced the identity reader as though it were the
classifier, because the classifier is the module whose per-page cost I know by
heart.

**Why this is the same defect as #21 and not a new kind.** DEFECTS #21 was a
price taken from the wrong model's rate card. This is a price taken from the
wrong module's image size. Both are the same mistake underneath: quoting a cost
from memory of a neighbouring thing instead of computing it from the constants
in front of me. `scripts/estimate_batch.py` exists for extraction precisely so
that cannot happen there, and I did not give the identity reader the same
instrument before spending on it.

The money is not the damage. The damage is that Alex approved a spend against
a number I had not computed, and standing rule 8 says numbers in prose are
measured or absent.

**Found by:** measuring what the finished run cost before reporting its
results, rather than repeating my own estimate back as though the run had
confirmed it.

**Fix:** `scripts/estimate_batch.py` grows an `--identity` mode that prices a
page read from the identity reader's own constants and its own measured cache,
so the next quote for that module comes from the same kind of instrument
extraction already has. Nothing is quoted from memory again.

**What remains:** the extraction quote in this session's report ($15.35
standard, $7.67 batched for 218 documents) comes from `estimate_batch.py` and
from the smoke run's measured tokens, not from memory, so it is not exposed to
this fault. It is still an estimate of a run that has not happened.

**Pin:** tests/tier2/test_estimate_batch.py::test_a_page_is_priced_from_the_cap_the_module_actually_sends

---

## #51 — 2026-09-05 — I pre-registered a bar that was arithmetically unreachable

**What happened:** the fourth sitting's rule said 24 of 26 attachments must
verify. **The maximum attainable score was 20.** The bar sat four above the
ceiling, so the module was going to fail before Alex read a single page.

**Why the ceiling is 20.** Three of the twenty faces on the sheet were given
more than one page: 1493451 face p10 got five, 1493399 face p41 got two,
1494036 face p12 got two. A face has one reverse side, so **at most one of
each group can be right**. Five mutually exclusive rows contribute at most one
"yes" and at least four guaranteed "no", before anyone looks at the paper.
17 faces with one page each, plus 3 faces contributing at most one each, is 20
of 26 — a ceiling of 77% where I had set a bar of 92%.

Alex spotted this from the sheet and said so before I scored it: "this can only
have one right combination at most, so at least 4/5 will be no." He put the
ceiling at 19; I count 20. The difference does not matter and I have not chased
it, because the bar was above both.

**This is DEFECTS #41 in a mirror, and I cited #41 while making it.** #41 was a
pre-registered case that could not fail. This is a pre-registered bar that
could not pass. While writing this rule I explicitly checked the *escape* for
vacuity — the "three or more agreeing fields" fallback, rejected because 37 of
39 attachments rest on exactly two — and wrote that check into the protocol as
#41's lesson applied. **I checked the fallback and never checked the bar.**

**The deeper fault is the unit, not the arithmetic.** I already corrected the
unit once, from documents to pairs, and the correction was in the right
direction and still wrong. A pair is not the thing being decided. The thing
being decided is: **did this face end up with a correct and uncontaminated set
of pages?** That is what extraction consumes and what a wrong answer corrupts.
Scored per pair, a face given five pages is punished five times for one
decision. Scored per face, it is one decision, judged once.

**What the sitting measured, stated in all three units so none of them can be
cherry-picked later:**

| Unit | Result |
|---|---|
| Pairs correct | 16 of 26 (62%), against a ceiling of 20 |
| Faces given at least one right page | 16 of 20 (80%) |
| Faces clean — every page right and no wrong one | **13 of 20 (65%)** |

The third row is the one that matters, because a face carrying one right page
and one wrong page produces a document that mixes two wells and looks complete.
All three of the multi-page faces are in that state: each found its correct
page and each also picked up wrong ones.

**Both predictions committed before the sitting held.** 1493451: predicted most
of the five wrong, 4 of 5 wrong. 1493399: predicted at least one of two wrong,
one wrong. Those were called from the sheet's structure before any verdict
existed and they are not affected by the broken bar.

**What this does to the gate.** The pre-registered decision rule is void. I
will not pick a replacement threshold now and score against it — choosing a bar
after seeing the numbers is the thing pre-registration exists to prevent, and I
have just demonstrated I can get a bar wrong. **The decision returns to Alex,
with the three numbers above and my recommendation, and it is recorded as a
judgement call rather than as a rule firing.**

**What is not damaged.** The 26 verdicts are real and were keyed against a
sheet built before any of this was known. They do not depend on the threshold.
What is lost is the ability to say "the module passed or failed a bar set in
advance", which was the whole point of the exercise and is exactly the thing my
mistake destroyed.

**What remains, per standing rule 9:** the pool is now exhausted. All 39 corpus
attachments have been judged, so no held-out pair exists to test any new rule
on. Two patterns in the verdicts are strong — no backward attachment was ever
correct, 0 of 6 here and 0 of 8 across four sittings; and faces given several
pages are right 33% of the time against 76% for faces given one — and **neither
can be adopted on this evidence** for the reason DEFECTS #46 records. Dropping
every backward attachment would leave 16 of 20 pairs, which is 80%, so the
direction signal is real and would not have been sufficient either.

**Rule that comes out of this:** a pre-registered threshold is checked against
the maximum attainable score before it is written down, in the same pass that
checks the escape can fire. Both halves or neither.

---

## #52 — 2026-09-05 — Three committed scripts import dependencies nobody declared

**What happened:** `scripts/probe_sheet.py`, `scripts/score_outline.py` and
`scripts/score_marks.py` are committed and all three `import numpy`; the last
also imports `scipy.ndimage`. **Neither package is in `requirements.txt`, and
`git log -S numpy -- requirements.txt` shows neither ever was.**

They run here because both are installed in `.venv` (numpy 2.5.2, scipy
1.18.1), left over from the punch-hole work of 2026-09-04. That work was
abandoned and `docs/modules/reassemble.md` records the tidy-up: "`numpy` and
`scipy` were added for this and then removed with it, rather than left in
`requirements.txt` for code that no longer exists." The removal was right at
the time. The scripts written on 2026-09-05 then re-introduced the imports and
did not re-introduce the declaration.

**Why it matters.** CLAUDE.md's Environment section says "No new deps without
saying so". A checkout on a clean machine installs from `requirements.txt` and
three committed scripts fail on import. Worse, nothing says so: the failure is
an `ImportError` at run time, in scripts that produce measurements, so the
first symptom is a measurement that did not happen.

**Found by:** an inventory of repo conventions taken while planning the paper
module, not by any failure. It has been latent since the scripts were
committed earlier today.

**Fix:** both packages declared in `requirements.txt` with the real reason, and
a test that walks every third-party import in `pipeline/` and `scripts/` and
fails if one is not declared. A rule enforced by a test rather than by memory,
which is the only kind that survives (CLAUDE.md rule 6).

**What remains:** the test checks declaration, not version compatibility. It
would not have caught numpy 2.0 removing `ndarray.ptp()`, which cost a whole
cycle on 2026-09-04 because an `except Exception` swallowed it.

**Pin:** tests/tier2/test_requirements.py::test_every_third_party_import_is_declared

---

## #53 — 2026-09-05 — "Redacted by construction" put an address in a fixture

**What happened:** `scripts/make_paper_fixtures.py` builds a tier-2 fixture by
blanking a page and pasting back only the marks `pipeline/paper.solid_marks`
detects. Its own docstring says the result is "redacted by construction rather
than by hand" and prints, on every run, "No form text, no handwriting, no
names".

I rendered the fixture and looked at it before committing. It contains
**"Lamar Street, Suit"** — part of the operator's business address — along with
"RAI AD", "EXAS", "W B", "R m R Log", "NAM", a signature fragment and a dozen
checkbox squares.

**Why the redaction leaked.** The claim rests entirely on `solid_marks` finding
paper damage. It does not. It finds any connected component over 0.008 in²
with an ink density above 0.30, and that admits bold printed glyphs, checkbox
outlines and — the damaging one — a whole underlined text line, because the
underline joins the letters into a single component. Measured on page 6 of
1495414: the address line is **5,628 px, larger than either punch hole at
4,432 and 4,292 px**. No area threshold can separate them.

Shape can. The address line's bounding box is 465x38, an aspect of **12.2**.
The corner blot is 197x148, aspect 1.3, and the punch holes are 1.1. A limit
of 3 removes every text line and printed rule on both pages while keeping every
real mark.

**Two defects in one, and the second is the worse one.**

The fixture leak is a CLAUDE.md rule 3 near-miss: raw pages are never committed
because they carry personal and business information, and I was about to commit
one under a label asserting the opposite. It was caught by looking at the image,
not by any test, and nothing in the pipeline would have caught it.

The detector fault is larger than the fixture. **`solid_marks` was treating
printing as paper.** Printing is shared between two pages of the same form
revision, so it is a false-confirmation channel; the margin statistic happens to
defend against it, because printing matches under the orientation-preserving
control rather than under a flip, but that is a defence the module was relying
on without anyone saying so.

**Fix:** `MAX_ASPECT = 3.0` applied to every mark, and `MIN_MARK_AREA` raised
from 0.008 to 0.02 in², which is the gap the measurement shows between printed
glyphs and real marks. The fixture generator asserts the redaction rather than
claiming it: it refuses to write a fixture whose surviving marks are not all
within the size and shape envelope of paper damage.

**What remains, and it is a real loss.** Staple holes are small — a few hundred
pixels — and the new floor excludes them. Individual bold glyphs are the same
size and pass every other test, so area is the only thing separating the two and
staples cannot be recovered by loosening it. Staple marks need their own
discriminator and do not have one yet. Recorded rather than quietly dropped:
the physical-signal work of 2026-09-05 identified staples as a real channel and
this module cannot currently read them.

**Resolution: the fixture approach is abandoned, and that is the real lesson.**
With the aspect limit in place I regenerated and looked again. Page 6 came back
clean — the torn corner and two punch holes, nothing else. **Page 9 did not.**
It still carried a printed "rm" at 2,178 px, fill 0.46, comfortably inside the
envelope, and a handwritten squiggle that may be someone's initials.

The envelope can be tightened again, and something else will get through,
because **the detector's whole failure mode is mistaking ink for paper.**
Redaction by detection asks the component that is wrong in exactly this
direction to certify that it was not wrong. No threshold makes that sound.

So there are no page fixtures. Tier 2 reads the corpus and skips when `data/`
is absent, which is the pattern the repo already uses in eight places in
tests/tier2/test_textlayer.py; the only committed test data is synthetic arrays
in tier 1. `scripts/make_paper_fixtures.py` is deleted rather than left as a
trap for someone who reads its docstring and believes it.

**The detector fix stands on its own merits** and is unaffected: printed text
lines and printed rules were being read as marks on the paper, and they no
longer are.

**Pin:** tests/tier1/test_paper.py::test_a_line_of_text_is_not_a_mark_on_the_paper,
::test_a_printed_rule_is_not_a_mark_on_the_paper,
::test_a_bold_glyph_is_not_a_mark_on_the_paper

---

## #54 — 2026-09-06 — The probe printed "Zero of 517" in the same breath as reporting one

**What happened:** `scripts/probe_paper.py` ran 517 scoreable hard negatives and
found **one false positive**. Its closing summary read:

    scoreable negatives: 517   false positives: 1
    ...
    Zero of 517 licenses a false-positive rate below 0.58% at 95% (rule of three).

The rule-of-three line is printed unconditionally. It says "Zero of 517"
whatever the count above it says, because I wrote it while assuming the answer
would be zero and never made it read the number it was standing next to. Two
lines apart, one of them says 1 and the other says zero.

**And the pair it found cannot be identified from the output.** Rows are
labelled `f"{ra}-{fa} p{pa}+p{pb}"` — the first record, the first file, and both
page numbers. For the cross-record stratum, where the two pages come from
*different* records, that prints the second record's page number under the
first record's id. The offending row reads `record 1865938-0 p2+p1`, which
looks like two adjacent pages of one file and is nothing of the sort. The
second record is not written down anywhere, so the one result that matters
most is the one I cannot go and look at.

**Why this is the same defect twice.** Both halves are a number or a name
printed next to data it does not describe. DEFECTS #48 was a header counting a
constant while the run counted something else. This is a summary line counting
an assumption while the run counted the truth, and an identifier naming half a
pair. The corpus-consistency guard scans prose in `docs/`; nothing scans an
f-string in a script, which is what #48 already said and what I did not act on.

**Found by:** reading the probe's own output rather than its headline, after
the false-positive count and the rule-of-three sentence disagreed.

**Fix:** the rule-of-three line derives from the measured count and states the
bound for that count, or says plainly that a bound is not available. Every row
carries both sides of the pair, `ra-fa pPA + rb-fb pPB`, so any result can be
found and looked at.

**What remains:** this fixes two lines in one script. Every other script in
`scripts/` builds its own labels the same way, and none of them is scanned by
anything. That is a standing exposure, not a fixed one.

**Pin:** tests/tier2/test_probe_paper.py::test_a_pair_label_names_both_sides
and ::test_the_false_positive_bound_uses_the_measured_count

---

## #55 — 2026-09-06 — A two-hole punch is symmetric, so one flip pairs any two pages

**What happened:** the development measurement ran 517 hard negatives and
produced **one false confirmation**: 1865938-0 p2 against 1495009-1 p1. Lease
VAN WART B in Fayette county against lease HAINES, LYDIE GRABOW in Burleson
county, different operators. Two sheets that cannot be one sheet.

**It is not a coincidence and a higher threshold does not fix it.** Both pages
carry a standard two-hole punch, and a two-hole punch is symmetric about the
page's centre line:

    1865938-0 p2   holes at x = 0.338, 0.672
    1495009-1 p1   holes at x = 0.344, 0.670

Under `flip_h`, the reflection about the vertical axis, 0.672 maps to 0.328 and
0.338 maps to 0.662. **Each hole lands on the other hole.** The positional
pairing therefore succeeds between *any* two pages punched by *any* standard
punch, which is most of the archive.

R2 says position locates and pairs marks and the outline decides. That rule
assumes the pairing constrains something. Here it constrains nothing: the
transform maps the mark pattern onto itself, so the assignment is free and the
outline correlation is asked to carry the whole claim alone. Two rims that
happen to agree then become a confirmation.

**Why raising the threshold is the wrong fix.** The false pair's second margin
is +0.316. The one true pair that currently confirms has a second margin of
+0.359. A threshold between them leaves 0.04 of headroom on a sample of two,
which is not a threshold, it is a coincidence waiting to be re-measured.

**The fix is to say what the transform is allowed to be evidence for.** A mark
that the transform maps onto *another mark of its own page* is ambiguous under
that transform: the mechanism cannot tell the mark from its twin, so its
agreement is not evidence about which sheet this is. Such marks are excluded
from pairing under that transform, and if too few remain the pair abstains.

Checked against everything already measured:

  1865938 p2 / 1495009 p1   both holes self-symmetric under flip_h, both
                            excluded, nothing left, refused
  1495414 p6+p7             matched under flip_v, where the marks sit at
                            y = 0.016, 0.033, 0.034 and map to 0.98 and 0.97
                            where there are no marks. Nothing excluded, still
                            confirms.
  the stack negatives       unaffected: they never reached two marks anyway

So it removes the false positive and costs none of the evidence in hand. That
is the test of a fix found by looking at a failure: it has to be justified by
what the paper does, not by which row it deletes.

**Found by:** reading the one failing row rather than the summary line, after
DEFECTS #54 made the row identifiable.

**What remains:** this is a development-set fix, discovered after seeing the
failure, and it therefore has no held-out support at all. It goes into the
frozen mechanism before the pre-registration is written, and the held-out run
is what tests it. Nothing about it is confirmed yet.

**Pin:** tests/tier1/test_paper.py::test_a_mark_the_transform_maps_onto_its_own_twin_is_not_evidence

---

## #56 — 2026-09-06 — The blind sitting was built from pages Alex had already judged

**What happened:** `scripts/make_paper_sheet.py` drew 30 held-out pairs for a
blinded sitting. Checked before handing it over: **4 of the 30 rows are pairs
Alex has already judged** in the four reassembly sittings, and **16 of 30 are
in records whose page images he has already looked at.**

Row `pair-03` is 1493399-0 p41+p42. He judged that exact pair "yes" on
2026-09-05. The frozen mechanism confirms it. Had he recognised it, a
remembered answer would have been recorded as an independent confirmation of
the thing it was meant to test.

**Where the reasoning went wrong, and it is a distinction worth keeping.** The
frame excluded three records — the ones whose *marks* I had inspected — on the
argument that a record used to develop the identity rules tells the paper
matcher nothing, because knowing an operator name repeats says nothing about a
punch hole. **That argument is correct about the rules and irrelevant to the
human.** Alex did not read identity fields in those sittings. He looked at
photographs of the paper, which is the same evidence this sitting asks him to
judge, and he wrote down a verdict for each.

The contamination vector is his memory, not the rules. I reasoned about which
records had informed the *code* and never asked which records had informed the
*judge*.

**Measured cost of fixing it:** 54 likely-true pairs exist corpus-wide; 23 are
in records he has never seen; at the measured 72% scoreable rate about 17
survive screening. The pre-registered floor is 10 and the rule needs a
denominator of 8, so the stricter frame still clears both.

**Fix:** the held-out frame excludes every record appearing in any verification
sheet, plus every record whose pages were displayed in conversation. The
exclusion list is data, derived from the sheets themselves rather than
remembered, so it cannot drift.

**What remains:** exclusion is by record, not by page, which is stricter than
strictly necessary and deliberately so. And it cannot cover pages Alex has seen
that left no written trace; the list is built from the four sheets and from
records named in conversation, and if there are others they are not recoverable.

**Pin:** tests/tier2/test_paper_sheet.py::test_the_sitting_excludes_records_alex_has_seen

---

## #57 — 2026-09-06 — The paper matcher is safe, blind, and does not ship

**The pre-registered rule** (docs/labeling-protocol-paper.md, fixed before the
sheet was drawn; mechanism frozen in commit `4868fdd`, verdicts sealed and
hashed at `943d12256c7e20de` before Alex saw a single image):

> Ships if and only if **both**: Part A returns zero false confirmations on
> held-out records, **and** Part B confirms at least half of the pairs judged
> same-sheet, with a denominator of at least 8.

**Result.**

| | |
|---|---|
| Part A, held-out guaranteed-false pairs | **0 false confirmations of 325** |
| Part A, pairs Alex judged not-same-sheet | **0 of 8** |
| Part A, development negatives | 0 of 517 |
| Part B | **4 of 16 same-sheet pairs confirmed, 25%** |
| Rule needed | at least 8 of 16 |
| cannot-tell | 6 of 30, 20%, under the 30% trip |

**It does not ship.** One clause, a conjunction, and half of it failed.

**Why it failed, and it is not a tuning problem.** The evidence column was on
the sheet so that a verdict could be read alongside what produced it. Of the 16
pairs Alex judged same-sheet, **15 cite staple marks**:

    11  staple
     3  torn edge, staple
     1  staple, show-through
     1  fold

**Staples are the one physical channel this module structurally cannot read.**
They sit below `MIN_MARK_AREA`, and DEFECTS #53 established that the floor
cannot be lowered to reach them, because individual bold printed glyphs are the
same size and pass every other test. That cost was recorded when the floor was
set. What this sitting measures is how large it is: the human and the machine
were reading almost entirely different evidence, and the machine's channel —
punch rims and blots — was the minority one.

Three same-sheet pairs were refused holding a **strong single margin**: pair-11
at 0.944, pair-01 at 0.684, pair-30 at 0.456. All three failed on the two-mark
rule alone. That rule is right — a one-mark rule leaked at every threshold that
confirmed anything, measured on 86 hard negatives — and it is also the binding
constraint on reach.

**What is genuinely established.** The safety property held everywhere it was
tested: **zero false confirmations in 850 negatives** across development,
held-out, and human-labelled sets. Zero of 325 held-out licenses a false
positive rate below 0.92% at 95%. When this mechanism speaks, on this evidence,
it has not yet been caught being wrong.

**What may not now happen.** The rule says a retune requires a fresh record
split and a re-run of both parts. These 30 pairs are spent. Lowering the mark
floor, relaxing the two-mark rule, or adding a staple channel and re-scoring on
this sheet would be fitting to the test and quoting the test, which is DEFECTS
#46 for the fourth time in this project.

**Pin:** tests/tier3/test_paper_eval.py, which is the first content in tier 3
and gives `make eval` something to run.

---

## #58 — 2026-09-06 — I pre-registered a recall bar against no baseline

**What happened:** the paper matcher failed its pre-registered bar at 4 of 16
and I reported that it does not ship. Alex pushed back: it made four
confirmations, all correct, and no wrong ones anywhere. Why reject a mechanism
that is never wrong for being often silent?

He is right, and the fault is in the bar.

**The bar measured recall against an implicit ideal instead of against the
alternative.** "At least half of the pairs judged same-sheet" compares the
mechanism to a hypothetical perfect one. The decision that actually matters is
whether it adds correct attachments the current system misses. I never
measured that, and never wrote it into the protocol, although the plan does say
in its own limitations section that "the reach that actually matters is the
rate among pairs where identity agreement is below the threshold". I wrote the
right sentence and then pre-registered a different quantity.

**Measured now, and it was never used to tune anything:**

| | |
|---|---|
| Same-sheet pairs on the sheet | 16 |
| Attached today by reassembly's identity fields | **0** |
| Confirmed by the paper mechanism | 4 |
| **Correct attachments it would add that identity misses** | **4** |

Recall is 25% against a baseline of **zero**, not against 100%. Wilson 95%
interval 10% to 49%, so the size of the gain is genuinely uncertain; that it is
a gain is not.

**What is and is not contaminated by measuring this after the fact.** The
false-positive rate is independent of the sitting's positives: 0 of 325
held-out guaranteed-false pairs and 0 of 517 development ones, 0 of 850 in
total, below 0.92% at 95%. The four additions are a quantity that was never
pre-registered and never tuned against, computed once, on held-out pairs. **No
threshold was moved and nothing was refitted.** It is a different question
answered on the same data, not the same question answered again until it came
out right.

I would be recording this the same way had the answer been zero additions. It
would have been damning rather than exculpatory, and the flaw in the bar would
have been identical.

**Alex's second point, and it is half right.** He observed that the negatives
he rejected were obviously different forms and so were easy. True of the eight
on the sheet. Not true of Part A: 115 of its 325 held-out negatives are
same-file stack-mates — same office, same punch, same stroke — which no form
type separates. The safety claim does not rest on the easy eight.

**What does not change.** The pre-registered rule failed as written and that is
recorded as a failure, in tests/tier3/test_paper_eval.py, permanently. The rule
is not rewritten and the sitting is not rescored. What changes is that the
decision to ship is put to Alex on the measured quantity rather than settled by
a bar that measured the wrong thing.

**Rule that comes out of this:** a bar on a mechanism that supplements an
existing system is stated against that system's current output, not against
perfection. "Half of true pairs" and "more correct attachments than today"
are different questions and only the second one decides anything.

---

## #59 — 2026-09-06 — "24, 31 and 32 on three revisions" is wrong, and it hid a working signal

**The claim, asserted in seven places** across `pipeline/reassemble.py` (three
times), `pipeline/extract.py`, `docs/modules/extract.md`, `DEFECTS.md` and a
tier-1 test docstring:

> the same printed box is numbered 24, 31 and 32 on three revisions of this
> form, so a number-keyed rule is silently wrong on two of them

**It is not three revisions of one form. It is two form families.** Measured on
27 back pages whose true family is derivable from a pair Alex judged one
document:

| Printed box | G-1 | W-2 | overlap |
|---|---|---|---|
| Notice of Intention to Drill | 19 | 26 | none |
| Location of Well relative to lease boundaries | 24 | 31, 32 | none |
| Total Depth | 28 | 35, 36 | none |

Six G-1 back pages, every one using 24. Eighteen W-2 back pages, using 31 or
32. **Zero overlap on any of the three boxes.** The revision difference is real
and it sits *inside* W-2, between 31 and 32; the 24 is a different form
altogether.

**What the mistake cost.** The claim was the stated justification for matching
back-page boxes as text and throwing the number away. Matching as text is still
correct and nothing about the existing rule was wrong. But the number carries
**which form family this page belongs to**, and that is precisely the thing the
classifier is worst at and the thing DEFECTS #44's open hole needs. We had the
signal on disk since the identity run and discarded it on a false premise.

**Measured against the classifier on the same 27 pages:**

| | correct | wrong | abstained |
|---|---|---|---|
| Census `form_class` (Haiku, vision) | 20 (74%) | 7 | 0 |
| Field number off the printed box | **24 (89%)** | **0** | 3 |

Strictly better, and it never asserts a wrong family — it abstains, which is
the discipline the rest of this pipeline runs on.

**How the error was made.** The three numbers were collected from real pages
across the corpus and I inferred "three revisions" without checking what form
each page was. It is the same shape as DEFECTS #21 and #50: a fact assembled
from real observations, generalised in the wrong direction, and then repeated
until repetition made it look established.

**What remains.** 27 pages, all development, and the "truth" is derived from
face labels which are themselves 94% precise for G-1 and never established for
W-2. The rule is a lookup off printed form numbers rather than a fitted model,
so it generalises by construction, but the *measurement* of it is
development-only and a held-out check is cheap and not yet done.

**Fix:** the claim is corrected everywhere it appears. Shipping the family rule
is proposed separately and not done here.

**Pin:** tests/tier1/test_reassemble.py::test_the_location_box_number_names_the_form_family

---

## #60 — 2026-09-06 — The classifier reads the section heading and then contradicts it

**Found by Alex asking a question I had not thought to ask.** Looking at
`1494037-0 p9`, which the census calls a W-2, he said: the first thing on the
page is "Section III" — have we ever seen a W-2 back page starting with
Section III?

**No. Not once.** Measured across every back page the identity reader has read,
with the family taken from the printed field numbers (DEFECTS #59), which is an
independent signal from a different model call reading a different thing:

| Census `part` | field numbers say G-1 | say W-2 |
|---|---|---|
| `sec_ii` | 0 | **25** |
| `sec_iii` | **30** | 0 |
| `continuation` | 6 | 23 |

**Section III is a G-1. Section II is a W-2. Fifty-five pages, no crossover.**
That is the form design: a G-1 carries Sections I and II on its face and
Section III on the back; a W-2 carries Section I on the face and Section II on
the back.

**So the classifier's own output contradicts itself, and often.** It reads the
section heading off the page and records it in `part`. Then it assigns a
`form_class` that the heading rules out:

| | pages |
|---|---|
| `sec_ii` called `w2` — consistent | 31 |
| `sec_ii` called `g1` — **contradicts** | 3 |
| `sec_iii` called `g1` — consistent | 3 |
| `sec_iii` called `w2` — **contradicts** | **28** |
| **self-contradictory** | **31 of 65** |

Nearly half, and overwhelmingly in one direction: 28 of the 31 Section III
pages were called W-2. W-2 is the commoner form in this corpus, and a back page
usually prints no form number, so the classifier appears to fall back on the
base rate while its own `part` field already held the answer.

**Validated against Alex's judgements.** On the 27 back pages whose family is
derivable from a pair he judged one document, the section heading alone is
right 10 times, **wrong 0 times**, and abstains 17 (the page was called
`continuation`, which is genuinely mixed). The field-number rule on the same 27
is right 24, wrong 0, abstains 3. Two independent signals, neither ever wrong,
and they never disagree with each other.

**Why this matters beyond tidiness.** `form_class` on back pages is what
DEFECTS #44's open hole needs and what DEFECTS #37 already established could
not be trusted. The information to fix it was inside the classifier's own
output the whole time.

**What remains.** Reach differs sharply: 65 corpus pages carry a `sec_ii` or
`sec_iii` label, against 238 called `continuation`, where the heading says
nothing and only the field numbers speak. Neither signal covers a page that
cites no numbered box and carries no section heading. And all of this is
development data — 27 pages of derived truth, from face labels that are
themselves 94% precise for G-1 and never established for W-2.

**Pin:** tests/tier2/test_taxonomy_coverage.py::test_a_section_heading_and_a_form_class_must_not_contradict

---

## #61 — 2026-09-06 — The mark detector assumes 300 dpi and 53 corpus pages are not

**What happened:** `pipeline/paper.solid_marks` takes `dpi` and defaults it to
300. `pipeline/papermatch.page_marks` is the only caller that reads real pages
and it never passes one:

    marks = paper.solid_marks(np.asarray(image) < 128)

**Measured across all 3,689 corpus pages with `pdfimages -list`:**

| x-ppi, y-ppi | pages |
|---|---|
| 300, 300 | 3,610 |
| **200, 200** | **53** |
| 300, 301 | 24 |
| 301, 300 | 2 |

The 200 dpi pages are not a separate class of file. **Every one of them sits
inside a file that is otherwise 300 dpi**, in eight files across six records,
and **11 adjacent page pairs straddle the change**, one of them in 1501720, the
demo document.

**Three consequences.**

*The floor is converted at the wrong scale.* `MIN_MARK_AREA` becomes
`0.02 * 300 * 300` = 1,800 px. On a 200 dpi page 1,800 px is **0.045 in²**, so
the effective floor there is more than twice what the module documents.

*Areas are not comparable across the change, so `_compatible` refuses every
cross-dpi pair.* `area_in2` is `area / dpi ** 2`, so one physical mark reports
2.25x smaller on a 200 dpi page than on a 300 dpi one. `AREA_RATIO` is **1.6**,
and 2.25 > 1.6, so two readings of one physical mark can never be paired across
the change and a true pair straddling it **cannot be confirmed by
construction**. There are 11 such adjacent pairs. This is the damaging half.

*`kind` is mislabelled there.* `HOLE_AREA` is an inch band, so a punch hole on
a 200 dpi page falls outside it and is recorded as a blot. That travels into
the report only and changes no decision.

**What the fix actually gains, and it is the opposite of what I predicted.**
I wrote this entry expecting the corrected floor to recover real marks the
assumption was dropping. Measured on all 53 pages: 11 of them change, gaining
19 marks. **All 19 were rendered and looked at, and all 19 are printing.**

    1501720 p31   five fragments of large bold sideways fax-header text,
                  "williamt", "Turner Williams", "18 PM"; two called `hole`
    1501720 p19   two pieces of a printed casing schematic's hatching
    1501720 p35   a filled wedge and a fragment of survey linework on a plat
    1498123 p6    part of a RECEIVED stamp, and handwriting

So on these pages an honestly converted floor does not admit damage, it admits
ink. That is DEFECTS #53's fault in miniature and it carries #53's lesson
further than #53 stated it: **the area floor was never what kept printing out.
`MAX_ASPECT` was.** The address line of #53 was 0.0625 in², well over the
floor, and was excluded by its 12.2 aspect. These fax-header fragments are
chunky rather than long, so no aspect test reaches them, and the only reason
300 dpi pages do not show the same thing is that they do not happen to carry
fax headers.

**It changes no verdict.** All 494 within-file pairs across the six affected
records were compared under both readings: **0 verdicts changed**. The two-mark
rule and the margin absorb the extra components, which is the defence #53 noted
the module was relying on without anyone saying so. It is now said.

**Found by:** an inventory taken while planning the staple channel, not by any
failure. The staple channel is why it matters: its discriminator is a leg
separation measured in millimetres, so a page read at the wrong scale puts
every staple on it outside the band. It also sharpens the staple design, which
goes *below* the area floor where `MAX_ASPECT` cannot help, and must therefore
carry structural discriminators rather than a size envelope.

**Fix:** the page's real resolution is read from the file and passed. The
resolution is a property of the page rather than of the detector, so it goes in
the per-page cache key and not in `papermatch.DETECTOR`.

**What remains:** the 19 printed components stay. They are found, they are
carried, and nothing downstream currently distinguishes them from damage; what
stops them mattering is the margin, measured over 494 pairs on these records
and over 850 negatives before that. No test asserts that they are harmless,
because a test that asserted it would be asserting a coincidence.

**Pin:** tests/tier1/test_paper.py::test_the_area_floor_is_read_at_the_page_s_own_resolution
and tests/tier2/test_papermatch.py::test_a_page_is_read_at_its_own_resolution

---

## #62 — 2026-09-07 — I built a negative stratum out of a label that is wrong half the time

**What happened:** measuring whether a new small-mark channel is safe, I needed
adjacent page pairs that are *not* one sheet. I built the stratum the way
`docs/labeling-protocol-paper.md` builds its likely-false rows: a G-1 or W-2
face immediately followed by a back-ish page whose `form_class` is a
**different** form family. Different form, therefore not the same sheet.

It returned 7 pairs. **Six of them are pairs Alex judged same-sheet**, and the
seventh is 1495414 p6+p7, the one true pair the module was built on. The
stratum was not merely noisy. It was inverted.

**Why, and it was already written down.** DEFECTS #60 established that the
census `form_class` on back pages contradicts its own section heading on **31
of 65** labelled pages, overwhelmingly in one direction. A back page rarely
prints a form number, so the classifier falls back on the base rate. "The next
page is a different form family" is therefore not evidence that the next page
is a different form family, and a stratum keyed on it is keyed on noise.

**I cited #60 in the plan for this work and then used the label anyway.** The
plan says in as many words that the frame needs no classifier. I reached for
the classifier the moment I wanted a negative, because the existing protocol
had a stratum shaped that way and I copied its shape without re-reading what
had since been measured about the field it rests on.

**What is and is not damaged.** Nothing shipped and nothing was reported: the
contradiction was visible in the output because every row carried its record
and pages (DEFECTS #54's fix, doing exactly its job). **The 2026-09-06 sitting
is not affected.** It used that stratum only to *sample* rows for Alex, and
took his blind verdict as ground truth rather than the stratum label; its Part
A guaranteed-false pairs are a different construction entirely, being
cross-record, cross-file and non-adjacent. A sampling frame may be noisy. A
truth label may not.

**Fix:** adjacent negatives come from the eight pairs Alex judged
not-same-sheet, which are the only adjacent negatives in existence with a
trustworthy label. The stratum built from `form_class` is deleted rather than
weighted, and this entry records why it cannot come back.

**What remains:** eight labelled negatives is a small denominator, and all
eight are non-adjacent in page terms (p7+p11, p4+p8 and so on), so **there is
still no measured false-confirmation rate on genuinely adjacent
not-one-sheet pairs.** That gap is real, it is not closed here, and it is one
of the things the fetch has to buy.

**Pin:** tests/tier2/test_taxonomy_coverage.py::test_form_class_may_not_define_a_negative_stratum
