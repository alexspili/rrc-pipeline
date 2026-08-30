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
