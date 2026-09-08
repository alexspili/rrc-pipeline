# RRC Extraction Pipeline — Session Handoff
2026-08-29. Written at the end of the recon/corpus session so a fresh thread
(or Claude Code) can take over with zero re-discovery.

## What this project is

Portfolio repo for Alex's job search (Houston energy + applied AI roles; Oxy
asks for GitHub explicitly). One repo, two layers:

1. **Extraction pipeline** over Texas Railroad Commission imaged well records:
   classify pages, extract G-1/W-2 completion reports to JSON, validate,
   cross-check facts across forms in the same file, measure accuracy and cost.
2. **AI-assisted-engineering workflow layer** (CONTEXT.md, DEFECTS.md,
   three-tier tests) present from first commit, accruing evidence, but NOT
   claimed as a story until it has real entries. Publish-by date fixed in
   advance; cut order below decides what ships.

Time budget: a few days total. Kill switch: no single layer gets a second day.
Stack: Python core + static TypeScript span-viewer (his TS resume evidence).
Only claim what can be defended line-by-line in an interview. No PDFs of
fetched records in the repo (they contain personal data); redacted fixtures
only, referenced by record id.

## Cut order (each line is a shippable stopping point)

1. ~~fetch + cached corpus~~ DONE. District 03 closed at 202/249/3,689;
   district 02 opened 2026-09-07, 155 more records, sitting frame only.
2. ~~page classifier w/ measured number on small labeled page set~~ DONE
   2026-08-31. Census: 115 of 202 records (57%) hold a completion report,
   hand-verified 15/15. Corpus sufficient; fetch.py stays closed.
   Caveat that travels with it: the per-form G-1 vs W-2 split is NOT
   reportable, and the 83.6% arm accuracy is a uniform-sample number on 60
   pages containing 0 G-1. See docs/modules/classify.md.
   2b. Stage-2 labels, stratified over census predictions, to make G-1 vs
   W-2 measurable. Labelling only; the prompt fix is a separate gated step.
   DONE 2026-08-31. 143 pages in nine strata, blinded, seeds and metrics
   pre-registered before the draw in docs/labeling-protocol-stage2.md.
   Result: G-1 face precision 64.7% +/-4.5pp, W-2 face 44.0% +/-5.2pp, and
   the cause is legibility rather than layout confusion: 20 of 20 drawn
   faces with an illegible form number were wrong, and where OCR reads the
   number the model chose it is right 16 of 16. Full results and the two
   defects it surfaced: docs/modules/classify.md → Stage 2 results.
3. G-1 **and W-2** extraction. IN PROGRESS. Schema, extractor, validation
   rules and ground truth all exist; scoring is the next step.
   - The cut order's "Sections I & III, skip Section II" is WRONG and was
     corrected by reading the paper: on the 1975 W-2 every depth and casing
     string is in Section II, and section numbers are not stable across
     forms or revisions. The schema is organised by data type (identity /
     completion / test) with the section as provenance. docs/modules/extract.md.
   - v1 is identity + completion + date_of_test only. Do not let it grow
     into the per-form test tables; that is v2.
   - Provenance is region-level from the model, in the schema and prompt
     from v1. Textract stays a documented road not taken.
   - Cost MEASURED: $0.0705/doc standard, $0.0352 batched, on
     claude-sonnet-5 at $2/$10. Output is 85% of it, so image resolution is
     effectively free and must not be optimised.
   - Ground truth: 15 docs x 27 fields, tests/fixtures/extract_truth.csv.
   - Five statuses, not four: present, blank, illegible, not_on_this_form,
     page_not_in_document. The last two are 87 and 47 of the 405 rows and
     are different facts (a form family that changed vs an archive imaged
     front-only).
4. Deterministic validation (API check structure + county prefix, date order,
   depth order)
5. Cross-form identity extractor + disagreement detector (scoped: identity
   fields only on non-G-1 pages, diffed vs G-1)
6. Eval table, `make eval`, README with real numbers
7. TypeScript static viewer (page image + span overlays + disagreements +
   client-side search over processed wells). No backend, no hosted inference
   (rejected deliberately: cost/injection/uptime; documented in future-work)
8. Stretch: Section II, three-source text ablation, Postgres projection
   (schema.sql with CHECK constraints embodying the validation rules +
   idempotent load_db.py + docker-compose; explicitly first thing cut)

## The archive (all verified this session)

- UI: https://rrcsearch3.neubus.com/search-profile?profileId=17 (Neubus
  "neuDocs" v5.5 on Postgres FTS; backend PHP-ish on pubcore.neubus.com)
- Profile 17 = Oil & Gas Well Records + P-17s + Well Logs mixed. Record-level
  `profile_type`: POTENTIAL (well records series) vs WELL LOG vs P-17 etc.
- **~1,907,311 records total** in profile 17 (from the unfiltered-bug run).
- Backfile conversion started ~2007: 01/2005–01/2007 window = 0 records;
  01/2007–01/2009 = 49,612; 08/2009–09/2009 D03 = 64; 09/2009–01/2011 = 3,452.
- All metadata dates are IMAGING time, not filing time. Era sampling must come
  from the paper itself.
- ~17/64 (~25%) of one window was POTENTIAL; rest logs/P-17.
- Results ordered ascending by record id = imaging order (oldest batches
  first). Same id space across doc types (logs imaged later, higher ids).
- Post-Feb-2011 completions are filed electronically; NO images exist for
  them (verified: 2015 records return well logs/P-17s only). Ground truth via
  Completion Query pairing is DEAD. Optional: check if the CMPL webapp
  (webapps.rrc.texas.gov/CMPL) renders post-2011 filings as clean PDFs — if
  yes, usable only as an easy-distribution "ceiling" ablation, never headline.
- Search matching: `strict:"true"` is exact-match after punctuation stripping
  (tooltip: "No punctuation; except & and -"). Substring/operator search
  effectively unavailable server-side; do it client-side over manifest.
- Records reference sibling files not necessarily in the archive ("REFER TO
  1965 FILE"). A record matches a date window if ANY of its files was
  uploaded in it (windows overlap at record level; manifest dedupes).

## API chain (all captured, verified end-to-end, hashes matched)

Captures should live in docs/recon/ as raw cURL. Rate limit: server declares
x-ratelimit-limit: 60/min; fetcher runs ~24/min and backs off reading
x-ratelimit-remaining.

1. **Token**: 24h public JWT (Keycloak realm rrcsearch3 via
   pubcore.neubus.com/api.php?function=GetTenantEnvOauth — mint not yet
   automated; daily paste into NEUBUS_TOKEN. Script decodes exp and warns.)
2. **Search**: POST https://rrcsearch3.neubus.com/getSearchImages
   JSON: {excludeName:"", excludeValue:null, extraParams:"", includeName:"",
   order:"asc|desc", orderBy:"", page:N, pageSize:100, profile:17,
   recordFromDate:"MM/DD/YYYY", recordToDate:"MM/DD/YYYY",
   saveSearch:"true", Searchitems:{item:[{key,value,label,type}]},
   strict:"true"}
   - **strict MUST be "true"** — "false" silently disables ALL filter binding
     and returns the whole 1.9M archive while the response p-block still
     echoes your filters. (Echo comes from the parser, not the executor.)
   - district item: {key:"district", value:"03", label:"District",
     type:"DROPDOWN"}. Text items type:"TEXT", key e.g. operator_name,
     lease_name.
   - Response: data.data.meta.num_images (total),
     data.data.search_results.images[] with image_fields[] (field_name/
     field_value pairs: id, profile_type, lease_name, operator_name, county,
     api_number, api_ft tsvector...), doc_id (EPHEMERAL encrypted blob,
     re-encrypted per response — never persist), allow_access,
     image_is_processing, path (populated for POTENTIAL, null for logs).
   - Empty result: data.data is a LIST not dict (handled in fetch.py).
3. **Tab files**: POST https://rrcsearch3.neubus.com/getTabFilesOauth
   {profile_id:17, image_id:<doc_id blob>, page:1, page_size:50, order_by:"",
   order:""} → data.data: {tabname, total_files, files:[{nuid (UUID),
   name, format, document_type (e.g. "SUPPORTING DOCUMENT"), uploaded_on,
   page_count, file_size, ...}], folders}. Paginate by total_files.
4. **Download**: GET https://rrcsearch3fs.neubus.com/api/v1/single/{nuid}?profileId=17
   Requires ONLY: authorization Bearer + browser User-Agent (UA enforced by
   nginx; bare 403 page = proxy header filter). Validates nuid as UUID
   (param name "nuid"); doc_id blobs rejected.
   Verify: %PDF magic + Content length == file_size from step 3.

Auth notes: rrcsearch3 endpoints work with bearer + UA (+ x-csrf-token /
x-requested-with headers sent; the elaborate cookie session proved NOT
load-bearing — a malformed cookie worked fine once strict was "true").
Their JS has old_nuid→new_nuid migration → archive has been re-keyed; cache
by numeric record id only, resolve blobs/nuids fresh each run.

## fetch.py (written, working, in repo root)

Python 3 + requests only. Env: NEUBUS_TOKEN (required), NEUBUS_COOKIE /
NEUBUS_XSRF (optional, proved unnecessary). CLI: --district --from --to
--profile --search key=value (repeatable) --all-types --max-records
--max-pages --start-page --dry-run --force --no-strict
(experimental, known broken server-side). **--order desc does nothing** and
now refuses: it is accepted by the server and returns the same page id for id
(DEFECTS #65). Use --start-page to reach elsewhere in a window. FETCH_DEBUG=1 prints request
headers/body + response p-block.
Behavior: client-side POTENTIAL filter by default; tripwire aborts if
num_images > 200k (means filters ignored / stale token); dedupe via
data/manifest.jsonl keyed on record_id; downloads to data/raw/<record_id>/;
verifies size; rate-paced. Known gaps: mint_token() NotImplemented; .env
loaded via `set -a; source .env; set +a` (no dotenv dep).

## Corpus status — district 03 CLOSED, district 02 opened 2026-09-07

Totals now **357 records, 405 files, 6,443 pages**. Two populations, never
blended: district 03 below, closed, which every measurement in this document
rests on; and district 02, 155 records, described at the end of this file.

District 03, data/raw/ on Alex's machine. Final: **202 records,
249 files, 3,689 pages, 0 dupes.** Upload years: 2007:34 2008:27 2009:17
2010:2 2012:1 2013:1 **2014:120** (a second imaging wave — 59% of corpus;
paper vintage of that wave unknown until classification). Files/record:
164×1, 32×2, 4×3, 1×4, 1×5. Pages/record: median 14, p90 40, max 115
(stress fixture). Old operators present, by exact operator_name: Exxon 8,
Amoco 6, ATLANTIC RICHFIELD 5, Sage 6, Maverick 6.

DEAD HEURISTICS (measured on full manifest, do not chase):
- api_number is empty on ALL 202 records — an unpopulated index field, NOT a
  pre-1967 signal. Era bucketing must come from classifying the paper.
- files[].document_type is "SUPPORTING DOCUMENT" on all 249 — no classifier
  prior exists in metadata.
- Metadata thinness is itself a README number: 202/202 blank API, 20 blank
  county, 14 blank operator, 29 blank lease_name.
- NOT dead: api_ft carries the API number on 176/202 records as a tsvector
  (e.g. record 1501720 -> '03931674' = 42-039-31674). Every county name in
  the manifest maps to exactly one 3-digit prefix, all matching real RRC
  county codes. It is not a classifier prior, but it is a free cross-check
  for extraction and the disagreement detector.

Full-census classify cost: estimated ~9.1M Haiku input tokens ≈ $9 ($4.50
batched). MEASURED 2026-08-31: **$4.25 batched**, 3,689 pages on vision_1000
at ~2,045 input tokens each, 0.4% parse failures. The reopen-fetch condition
(G-1-bearing records < ~80) was not met: 115.

## Ground truth / eval design (post-pivot)

Status 2026-08-31. Stage-1 page labels DONE: 60 pages, uniform, seed 20260830,
at tests/fixtures/labels_stage1.csv. Uniform was right for an unbiased class
prior and overall accuracy, and is exactly why it contains 0 G-1 pages: a
corpus with 112 G-1 pages in 3,689 will not put one in 60 draws reliably.
Stage 2 is stratified over census predictions and is the instrument for
per-class precision. Never blend the two: stage 1 owns the prior and overall
accuracy, stage 2 owns per-class numbers.

- Hand-label 12–15 docs (G-1 Sections I & III), stratified across form
  eras/buckets AFTER classification. Honest small-n error bars in README.
- Corpus-wide metric: cross-form per-field agreement rate (needs no labels).
- Accuracy reported PER ERA bucket, not just blended.
- Dev fixtures ≠ eval set; hold out eval, don't look while iterating.

## Documents seen (fixture candidates, on Alex's machine + this thread)

- **1501720** Ducroz/Endeavor (Brazoria, 2007–09): 35pp combined file. G-1
  face p2, its Section III **p4** (NON-CONTIGUOUS, P-4 between). Corrected
  2026-09-07: this said p5, and p5 is a Form G-5 Gas Well Classification
  Report, rendered and read. The structure was right and the page number was
  wrong by one, in the file a fresh thread is told to read first. The census
  calls p4 a `g1` FACE; it opens with SECTION III, so it is a back page, which
  is DEFECTS #60 firing on the very page this entry describes. W-4/W-4A/W-5/
  W-6/G-5/W-15, Rule 37 complaint, shut-in letters, internal RRC emails,
  surveyor plat, schematic. REAL ERRORS: G-5 API 42-309-31674 vs 039-31674
  everywhere else (transposed digit; county prefix check catches);
  1202 vs 1201 Louisiana; completion 11/20/08 vs 20-Nov-07; field named
  COWTRAP (WILDCAT) vs (MIOCENE 6350); RRC memo admits production reported
  in nonexistent field. THE demo document.
- **1760703** Fleck/Strand (Waller): THREE G-1s (11/4/08, 3/19/09, 11/17/09)
  = completions are a time series per well; W-3 lists perf interval
  3,264–3,286 not in any Section III (files reference missing siblings).
- **2737207** Phillips/Ducroz lease (Matagorda): 2001 W-3 for well drilled
  1962, plugged 1965; handwritten remarks; single-doc POTENTIAL record.
- **1493418** Humble/Trinity Bay (Chambers): 1967 letters, Rule 49(B) calc
  sheets, and **Form WS-1 rev-1959 notarized Feb 1965** (potential test:
  72,500 MCF, AOF 290,000, ASTM distillation table, notary block). Proof of
  form-family drift. NO G-1 in file.
- **1494070** Exxon/Cockburn (Wharton): 1989 P-4, handwritten X-REFERENCE
  card, 1991 W-3. NO G-1.
- **1865621** Texas City Refining (lease "Section 15-Humble Fee" — operator
  strings inside lease names = entity-resolution gotcha): 1983 P-4. NO G-1.
- **1504455** Humble/Liberty South: 1969 Form SW-1 transport auth. NO G-1.
- P-17s (post-2011): typed applicant half + handwritten RRC-USE-ONLY block;
  checkbox-dense; amended filings duplicate a permit under one record.
- Well log TIFF: single strip 1010×15,167 px.

**Key inversion**: profile_type POTENTIAL ≠ contains completion report. The
classifier is also the corpus census; fraction-with-G-1 is unknown and is
itself a headline README table.

## Pipeline design decisions (settled)

- Two-pass: Haiku classify every page (~2,500 tok/page image) → Sonnet
  extract G-1 pages only. Batch API (50% off) default. MEASURED 2026-08-31 on
  one two-page document: $0.0775 standard, $0.0388 batched, on claude-sonnet-5
  at $2/$10 per 1M. The earlier ~$0.17/doc was an estimate priced at $3/$15,
  which is claude-sonnet-4-6's rate and not the model this pipeline uses
  (DEFECTS #21). Textract is not in the pipeline; see docs/modules/extract.md.
- AWS Textract DetectDocumentText ONLY ($1.50/1k pages) for word-level
  geometry = source spans (provenance, not accuracy). NO Forms/Tables
  analysis ($50–65/1k, not worth it). Three-source ablation available:
  embedded (bad) PDF text layer vs Textract vs vision — with cost per arm.
- Real cost center is eval iteration (~$50/full 300-doc run): tiered eval
  (20-doc smoke set per iteration, full set on merge), cache by (doc hash,
  prompt hash), Haiku-first with confidence escalation (escalation rate is
  a publishable metric). That cache is our own result cache, keyed on those
  two hashes. It is not Anthropic prompt caching: the classifier system
  prompt is ~400 tokens, below Haiku's minimum cacheable prefix, so no
  prompt-cache discount applies and none should be claimed.
- Every value carries a source span; deterministic validation post-extract;
  confidence routing → review queue = the TS viewer.
- Preprocessing guards: aspect-ratio check (log strips would be destroyed by
  the 1568px long-edge downscale; classify by geometry, spend no tokens);
  orientation normalization (rotated pages observed); "separator/ID card"
  page class (handwritten scrawl cards open many files).
- Identity-fields extractor doubles as era coverage across form families
  (WS-1/SW-1/P-4 yield field/operator/lease/well/county) without expanding
  the full schema beyond G-1/W-2.

## DEFECTS.md — banked entries (write these in before coding)

Superseded by the real DEFECTS.md, which now carries 16 entries. Kept because
1, 2 and 5 predate any code and that is the point of them. Entries 6-14 came
out of the classifier milestone; nine of the fourteen were found by measuring
rather than by reading, and three by Alex asking a question the tests could
not answer. 15 and 16 came out of sizing the stage-2 strata: the header
scanner counted a form's mention of other forms as their headers, and the
first fix for it was defeated by one space in the OCR. 16 is open.

1. Log-strip aspect ratio would silently destroy pages via downscale
   (found pre-code from a real file).
2. Amended P-17 filings double-count a permit within one record.
3. **strict:"false"**: sent a parameter value never observed from a working
   client; it silently disabled all filtering; the parameter echo concealed
   it; a day of session archaeology preceded controlled variable isolation.
   Rules: never send an unobserved value without a bounded test; an echo of
   input is not evidence it was applied.
4. Unbounded pagination in dry-run (paged an unfiltered 1.9M-row result).
5. p-block echo ≠ binding (subsumed in 3 but worth its own line).

## Repo conventions

- .gitignore BEFORE content: .venv/, data/, __pycache__/, .env
- .env.example committed; requirements.txt (requests now; later anthropic,
  pypdf, pillow, boto3)
- docs/recon/ holds raw cURL captures (redact tokens)
- CLAUDE.md (not CONTEXT.md) with stated line budget: 120, currently 95. The
  number came from SETUP.md's "e.g. 120" template line and is arbitrary; the
  discipline is not, and the rule on hitting it is move content out, not raise
  the ceiling. per-module rules with defect origins + pinning test + RETIRED
  section; README numbers all [N]-placeholder until measured
- Alex's style: plain declarative, no em dashes, no marketing adjectives, no
  "turns X into Y", no absolutes. Only defensible claims.

## Immediate next steps

1. ~~Corpus pulls~~ DONE (202 records; see Corpus status).
2. ~~Repo skeleton + first commits~~ DONE. 40+ commits, pushed to
   github.com/alexspili/rrc-pipeline (private). DEFECTS.md carries 14 entries,
   nine of them found during the classifier milestone. The pre-commit hook now
   runs tiers 1 and 2, so CLAUDE.md rule 6 is enforced rather than stated.
3. ~~Classifier + corpus census~~ DONE 2026-08-31. See Cut order 2.
4. ~~Stage-2 labelling~~ DONE 2026-08-31. See Cut order 2b.
5. ~~Decide what the fix is~~ DECIDED 2026-08-31: abstain rather than
   guess. Two new classes, `completion_face_unknown_form` and
   `completion_face_legacy`; the record-level union covers all four, so the
   115 headline is stable by construction. Not implemented, gated on a
   rule-5 proposal for the PageLabel invariant plus a before/after run on
   the stage-2 labels. Deferred on purpose: a targeted OCR/vision read of
   the form-number region, which would reopen Textract. See
   docs/modules/classify.md → The decided fix, and Era drift.
6. ~~Extraction smoke + scoring~~ DONE 2026-09-01: status 87.4%, value
   82.5%, by era and never blended. Validation runs on every document
   (`make findings`) and caught real errors with no labels.
6b. Provenance boxes MEASURED 2026-09-03 and the pre-registered rule fired:
   model boxes are not field locators (hit+near 60.9% overall, 11.4% on
   1966 paper; values grounded, geometry confabulated, DEFECTS #29).
6c. Provenance CLOSED 2026-09-03. Six candidates, two killed by gates
   written before the numbers existed.
   - Per-revision templates: dead on both gates. Coverage ceiling 18 of the
     35 graded 1966 boxes against a bar of 26; landing 13 of 18 against a
     bar of 14. `make template`, `make probebox`.
   - Snap tier graded for the first time and PASSES: 14 of 15 hits against a
     bar of 12, judged on hit alone. The 54.3% comparator stands.
   - SHIPPED: snap, then the widened model band, then page plus raw text.
     Source tags on every region; click-to-zoom with the printed field label
     as caption.
   - Textract shut PERMANENTLY on this argument. Its trigger condition fired
     and the second gate refused it anyway (DEFECTS #31 and extract.md).
   - Registration residual identifies a revision from layout rather than
     from a masthead: 24 candidates sit under a residual of 0.005 and the
     next one is at 0.040, with 11 of 12 agreeing with the recorded
     revision. Not built. It outlives the template and is
     the only idea on the table for the 41% of graded boxes whose revision
     the model could not read.
   - Four defects: #31 two decision clauses in one pre-registration, #32 a
     unique text match is not a correct match, #33 the overlay could not
     display what it measured, #34 a guard standing after the deletion it
     guarded. Limitations with measured rates: extract.md.
   - Nothing on this thread is open. Do not reopen it without a new
     measurement and a new gate.
7. Reassembly BUILT 2026-09-03, pure domain, `pipeline/reassemble.py`, 22
   tier-1 tests, DEFECTS #25's pin discharged. Pairs in both directions and
   settles by agreement on identity fields, never by position. Exact after
   normalising, never fuzzy; a contradiction rejects a pair; a tie attaches
   to nothing; candidates never cross a file boundary. Threshold is 2
   agreeing fields, PRE-REGISTERED not settled: the measurement that decides
   it is docs/labeling-protocol-reassemble.md, against the 15 ground-truth
   documents and the 5 worked cases, with the contradicted-but-agreeing list
   read by eye before the semantics are called final.
   The census number behind the design: of the 249 files, 112 hold a
   completion face and 64 of those hold more than one; the largest holds
   fifteen. So "which report does this page belong to" is the ordinary case
   and nothing based on nearness can answer it.
   `pipeline/identity.py` reads the six fields it compares. Cost MEASURED
   2026-09-03: $0.0074/page, 166 output tokens, so $2.01 standard or $1.01
   batched over the 274 candidate pages. That run is GATED and lands with
   the full extraction run as one spend decision.
   STATE 2026-09-04, AWAITING A VERDICT. Three verification sittings, six
   identity runs, ~$4.60 total. Do not spend on the corpus until the third
   sitting is graded.
   - Sitting 1: 8 attachments judged, 5 WRONG, three of them among the four
     drawn at random. Cause (DEFECTS #43): the identity fields identify the
     WELL, not the document. Two filings for one well agree on every field
     compared, because it is one well.
   - Three fixes followed. A predicted face may be a child only when its own
     cited boxes say back page (#44); purpose_of_filing and received stamps
     added as veto fields; the stamp respecified as office-plus-date after
     one page turned out to carry two stamps from two offices (#45).
   - Sitting 2 was the held-out check and it earned its keep: 7 of 8 on the
     pairs the fixes were BUILT from, 2 of 7 on fresh pairs (#46). Without
     it, 7 of 8 would have been reported and the corpus run would have
     followed it.
   - Two of the three new holes then closed: a back page may not be a
     parent, and the child test is keyed to `part` rather than `is_face`,
     which is gated on form_class and let the first page of a P-4 through.
   - The third hole STAYS OPEN on purpose. A form-family rule keys on
     form_class, and the two cases it must separate are indistinguishable
     there: 1495193 p7+p8 are w2 and g1 and ARE one document, which is the
     pin this module exists for; 1912687 p2+p8 are g1 and w2 and are not.
     The rule that closes the failure breaks the pin.
   - 13 of 15 across the first two sittings, all of it development data.
   - Sitting 3 is drawn and with Alex: 6 pairs, on a set of twenty records
     selected at random before reading, no page of which has ever been
     judged. The rule
     is all must verify. That is the number that decides the corpus spend.
   - Twice now Alex has verified a pair by the shape of its punch holes. The
     signal is real, measured at +0.911 on a clean pair, and parked because
     ink touching the hole defeats the isolation step and because it can only
     ever pair two sides of one sheet. docs/modules/reassemble.md.
   Superseded by the above, kept for its reasoning: reassembly is unbuilt and is now the biggest known gap. It must pair in
   BOTH directions and settle candidates by identity-field agreement, not
   by position: the smoke pairing looked only forward and three of fifteen
   ground-truth documents turned out to be sections without their face.
   Design, evidence, worked cases and tier-1 test plan:
   docs/modules/reassemble.md.

---

# Days 5 and 6, 2026-09-05 and 06: reassembly, and reading the paper

## Reassembly is built, measured, and its limits are known

Four judging sittings. **All 39 corpus attachments have been judged**, so there
is no held-out pair left for any rule keyed to identity fields.

The finding that shaped everything after it: **identity fields can only
exclude.** They describe the *well*, and a file holds several filings for one
well, so their agreement is guaranteed rather than informative. Held out, the
identity-only module was 65% clean, 13 of 20 documents.

Current state: 224 documents, 35 attachments, **25 of 32 multi-page documents
clean**. The six wrong attachments that remain are all same-form, same-well,
different-filing. No rule about forms or fields can reach them.

## The paper confirms what identity cannot

`pipeline/paper.py` (pure) and `pipeline/papermatch.py` (I/O). Two pages are
one SHEET when at least two solid marks on them — punch rims, blots, torn
corners — agree under a flip the paper can physically perform.

- **The statistic is the margin**, best legitimate flip minus best
  orientation-preserving control, never the raw correlation. A stack punched in
  one stroke puts three unrelated sheets at 0.53-0.57 raw.
- **The transform is predicted, never searched.** Searching rotations lifts
  every control to +0.42 and +0.49.
- **Zero false confirmations in 850 negatives** across development, held-out
  and human-labelled sets. Below 0.35% at 95%.
- It **failed its pre-registered recall bar** (4 of 16) and shipped anyway,
  because the bar compared it to a perfect mechanism instead of to reassembly,
  which attaches none of those 16. Both facts are asserted in tests/tier3.

**Why recall is low, and it is the next piece of work:** 15 of Alex's 16
same-sheet calls rested on **staple marks**, which sit below the mark-area
floor. The floor cannot be lowered — bold printed glyphs are the same size and
pass every other test, which is how an operator's address once got into a
"redacted" fixture.

## A back page's form family can be read off the paper

Two signals, neither ever wrong on the pages with derived truth, never
disagreeing with each other:

- **The section heading.** A G-1 carries Sections I and II on its face and
  Section III on the back; a W-2 carries Section I on the face and Section II
  on the back. No crossover in 55 readings.
- **The printed field number.** G-1 numbers Notice of Intention 19 and
  Location of Well 24; W-2 numbers them 26 and 31 or 32. Total Depth is
  excluded, being carried by many other forms.

This corrected a claim asserted in seven places — "24, 31 and 32 on three
revisions" — which is two *families*, not three revisions (DEFECTS #59). And it
closed DEFECTS #44's last hole: attachments 39 to 35, wrong ones 12 to 6, one
correct lost.

## Extraction is ready to run and has not been run

`scripts/run_extraction.py`, batched, **$8.07 for 223 documents** by the dry
run of 2026-09-07; the $7.17/218 quoted earlier described a pre-wiring
grouping that no longer exists. Gated on nothing now except the decision to
spend. `found_in` was added to the prompt on 2026-09-05, so the scored
87.4% / 82.5% describes a prompt that no longer ships; re-scoring is a
separate $1.54, and it does NOT ride along free: only 8 of the 15
ground-truth documents match a corpus document on (record, file, pages), so
the corpus cache cannot serve the other 7. The re-score is `make smoke`
re-run, same 20 documents, same seed, only the prompt changed.

## What the corpus decision now is

**Reopening the corpus is the declared next step**, roughly 110 more records,
because the staple channel cannot be graded on evidence that is spent. That
reverses "Corpus status — CLOSED" above, deliberately and for a stated reason.

## Working practice, unchanged and load-bearing

Every measurement pre-registers its rule; three of them failed and are recorded
as failures rather than rewritten. The most expensive lesson of these two days
is DEFECTS #51: **a pre-registered bar must be checked for reachability before
it is written down**, and the mirror, DEFECTS #58: **a bar on a mechanism that
supplements an existing system is stated against that system's output, not
against perfection.**

---

# Day 7, 2026-09-07: under the mark-area floor

## What was asked for and what the paper actually supports

The task was a staple channel for `pipeline/paper.py`. The evidence for it was
the 2026-09-06 sitting's evidence column: 15 of the 16 pairs Alex judged
same-sheet cite staple marks, which sit below `MIN_MARK_AREA`.

**The staple model did not survive measurement.** "Two marks about 10 mm apart
near a corner, with pitch and angle as the signature" fires on **1 of the 8**
development pairs where a flip beat the control. The other seven have their
agreeing marks 1.6, 3.4, 5.0, 8.7 and 9.2 inches apart. Rendered and looked at,
the marks are specks, nicks and show-through rather than staple holes. Pitch
appears nowhere in the shipped code because it earned no place there. Same
shape as DEFECTS #59: a fact assembled from real observations, generalised in
the wrong direction, repeated until repetition made it look established.

What ships instead is a **small-mark channel**: marks under `MIN_MARK_AREA`, on
the sheet rather than the scanner surround, roughly equant, near the paper's
own edge, and with at most one comparable neighbour within a character pitch.
Printing comes in runs and damage does not, and that one test took 2,357
candidates to 37 on a real page.

## Two things that had to be got right, both measured

**Count replaces shape.** These marks are a few dozen pixels and have no rim to
sample, so position carries the whole claim, which R2 forbids it to do alone.
Several marks agreeing at once under one transform stands in for the outline,
with the controls given the same freedom, and the statistic is still the margin.

**No offset is searched**, and this is R1 turning up in a new place:

| | cross-record | same file | positives |
|---|---|---|---|
| Marks matched one at a time | **0 of 120** | 3 of 160 | 4 of 16 |
| A shared rigid offset searched | 2 of 120 | 11 of 160 | 5 of 16 |

## Development result

On the 91 development records, fires on **4 of the 16** pairs Alex judged
same-sheet, and those four are **disjoint** from the four `compare` already
confirms, so on the sitting's own pairs the two channels together reach 8 of
16. Fires on **0 of the 8** pairs he judged not-same-sheet and **0 of 120**
guaranteed-false cross-record pairs. Three of 160 non-adjacent same-file pairs
fire; those are not guaranteed false and the protocol's standing rule is that
Alex adjudicates them.

Every constant was chosen while looking at that data and the firing rule was
chosen after seeing both halves. Frozen at commit `1a01829`; pre-registration
in `docs/labeling-protocol-staple.md`.

## The corpus is split, and the split is committed

`tests/fixtures/paper_record_split.csv`: **91 development, 111 held out**, seed
20260906. Every record whose pages Alex has looked at, 35 of them, is
forced into
development, derived from `seen_by_alex` rather than remembered, because such a
record can never supply a positive again (DEFECTS #56). The split guards one thing and
one only: that the false-confirmation number is measured on records nobody
tuned on. Negatives never reach Alex, so nothing here protects the positives.

## The bar is a bound, not a zero, and that was checked first

A mark's catchment at `SMALL_TOLERANCE` is 0.000201 of the sheet, so the chance
of two independent agreements arising and beating the control is about **0.46%
per pair**. Over 400 pairs the expected count of false confirmations is **1.8**.
A pre-registered bar of "zero" would therefore have been unreachable, which is
DEFECTS #51 in the other direction. The rule is a **95% upper bound below 2%**
on the held-out cross-record rate: met by 0 of 150, 1 of 250, 2 of 350 or 3 of
400, above the expected value at every size, and failed at twice it.

**If it passes, the module's safety claim still gets worse.** `compare` alone
is 0 of 850, below 0.92%. Two per cent is a looser bound. The trade is roughly
double the reach for a weaker safety claim, it is Alex's to make rather than
the rule's, and the protocol says so before the number exists.

## Two defects, both found by reading rather than by failure

**#61.** `papermatch.page_marks` called `solid_marks` with the default 300 dpi
on every page. Measured over all 3,689 pages: **53 are 200 dpi**, every one
inside a file that is otherwise 300, and 11 adjacent pairs straddle the change.
The damaging half is not the floor but `area_in2`, which came out 2.25x small
and so put one physical mark outside `AREA_RATIO` from itself, making those 11
pairs unconfirmable by construction. Fixed; 0 of 494 verdicts changed.

It also settled something larger. Reading those pages honestly admits 19
components and **all 19, rendered and inspected, are printing**: fax-header
text, casing-schematic hatching, part of a RECEIVED stamp, plat linework. So
**the area floor was never what kept printing out. `MAX_ASPECT` was.** That is
why the small-mark channel carries structural discriminators instead of a size
envelope.

**#62.** I built the adjacent-negative stratum from census `form_class` and 6
of its 7 rows were pairs Alex judged **same**-sheet, because `form_class`
contradicts its own section heading on 31 of 65 back pages (#60). A noisy label
may choose which rows a human looks at; it may never stand in for the human.
The 2026-09-06 sitting is unaffected: it used that stratum to sample and took
the blind verdict as truth.

## What is still missing, and what buys it

**There is no measured false-confirmation rate on genuinely adjacent pairs that
are not one sheet.** None exists with a trustworthy label: the eight negatives
Alex judged are all three or more pages apart, and DEFECTS #62 sets out what
happened when the classifier was asked to supply the label instead. That gap is the main
thing the fetch has to buy.

**Orientation** is a recorded limitation rather than a defect. The two flips
and the two controls are each closed under `rot180`, so a page stored upside
down costs nothing; only a quarter turn breaks it, and that is 2.9% of adjacent
corpus pairs and 0 of the 54 in the 2026-09-06 frame.

## The fetch, when it happens

**District 02**, Alex's choice on 2026-09-07, adjacent on the coast, so a
generalization test across offices with a population close enough to compare.
The confound is written down in advance: a regression there has two possible
causes and this run cannot separate them. Needs a fresh `NEUBUS_TOKEN` on the
day. `fetch.py --dry-run` first to size it. No census and no model money: the
frame is adjacent pairs screened by the detector.

---

# District 02, fetched 2026-09-07

## What was pulled and why

The staple work could not measure one thing on any evidence in the repo: **the
false-confirmation rate on adjacent pairs that are not one sheet.** DEFECTS #62 sets
out what happened when the census `form_class` was asked to supply that label, and DEFECTS #63 and #64 record why the gap matters most in exactly that
regime. So the corpus was reopened.

**District 02 rather than more district 03**, Alex's choice. It is the adjacent
Gulf Coast district, so the population is close enough to compare, and it is a
genuine test of whether the paper channels generalise across offices, which is
`docs/modules/paper.md`'s standing limitation. The confound is written down in
advance: a regression here has two possible causes, the mechanism and the
population, and this pull cannot separate them.

## The pull

    fetch.py --district 02 --from 01/01/2007 --to 01/01/2009
             --start-page {70,110,160,210,260} --max-records 30

**155 records, 156 files, 2,754 pages.** Five draws spread across the window
rather than one contiguous block, because a contiguous block of record ids is
one imaging batch and probably one box of paper.

- The window holds **28,827 records**. The count is what proved the session was
  binding: an unprimed session returns the whole 1.9M archive (DEFECTS #3).
- **Composition varies by depth.** Page 1 of the result is entirely WELL LOG;
  pages 50 onward are entirely POTENTIAL. Ascending order is record id order,
  and the logs occupy the low ids. Sampling the front of this window would have
  returned nothing usable.
- Pages per file: **median 11**, min 1, max 288, against district 03's median
  of 14. Thinner but not much. An early note calling them two-to-four-page
  files came from the five smoke-test records only and was wrong.
- Counties are right for the district: Victoria 27, Jackson 21, Refugio 15,
  Live Oak 10, Bee 9, Karnes 6, Lavaca 6, and 42 with the field blank.

## What these records are for, and what they are not for

They are recorded in `tests/fixtures/paper_record_split.csv` as
**`sitting_frame`**, a third value beside development and held_out. They are
not a tuning set. Tuning on one would spend the thing the fetch just bought.

`scripts/split_records.py` now **extends** that file and refuses to rewrite it,
so a record's half stays whatever it was decided to be before anybody looked at
it. A tier-2 test asserts the district 03 halves did not move.

## Corpus totals now

**357 records, 405 files, 6,443 pages**, across two populations that are never
blended. Every measurement in this document above this section is district 03.
The repo-consistency guard (DEFECTS #6) is now population-aware: a documented
count must match the total or one of the district subtotals, so stating either
is allowed and stating a wrong number still breaks the build.

## One defect out of the fetch

**DEFECTS #65: `--order desc` does nothing.** Ascending and descending return
the same page, id for id. `fetch.py`'s help and this document both claimed it
sampled the other end of a window. The flag now refuses and points at
`--start-page`, which demonstrably works. Probable cause is that `orderBy` is
sent empty, so there is no sort key for a direction to apply to; that stays a
hypothesis because confirming it means inventing a value never observed from a
working client.

## Next

Screen the 155 records for adjacent pairs both of whose pages carry at least
two small marks, size the sitting from the count, then a blind sitting with the
three-way label Alex chose on 2026-09-06: same sheet, same bundle but not the
same sheet, different. That yields the adjacent negative rate and fresh
positives in one sitting.

## The district 02 sitting, judged 2026-09-07

40 adjacent pairs, no masking, three-way label, sealed at `ceb7e34c8c448196`
before Alex saw an image. Protocol and full result:
`docs/labeling-protocol-adjacent.md`.

**The pre-registered rule passed on both halves.**

| | | |
|---|---|---|
| false confirmations among not-one-sheet | **1 of 20** | bar: at most 1 |
| confirmations among same-sheet | **3 of 17** | bar: at least 2, denominator 8 |
| `cannot-tell` | 3 of 40, 8% | trip: 30% |

Half (a) cleared by nothing. **Three things it turned up matter more than the
pass**, and all three are stated here because a pass is the least informative
thing a measurement can produce.

**1. The adjacent rate is twenty times the cross-record one and 20 pairs
cannot resolve it.** 1 of 20 is 5.0% against 1 of 400, 0.25%. But 20 pairs
licenses only a 95% upper bound of 21.6%, inside which 1.18% sits comfortably.
The protocol said before the draw that 40 pairs could detect a gross difference
and could not show the regimes were similar. It did neither. The gap DEFECTS
#62 opened is narrowed, not closed.

**2. `same-bundle` was used zero times, so the bundle confusion is still
unmeasured.** That label existed because a staple goes through every sheet of a
bundle at the same place, making bundle-mates the machine's one predicted
failure. Whether the distinction was invisible, absent from the draw, or folded
into `different` is unknown. **DEFECTS #63's prediction has still never been
tested**, and designing a sitting that tests it is open work.

**3. Page parity beats the mechanism, and costs nothing.**

| First page of an adjacent pair | Judged same-sheet |
|---|---|
| **even** | **14 of 19 (74%)** |
| odd | 3 of 18 (17%) |

Fisher exact two-sided **p = 0.0008**, on labels independent of the mechanism.
Consistent with these files opening with a separator or ID card, which shifts
every sheet boundary by one page. District 03's sitting points the same way
more weakly, 77% against 55%, on a classifier-selected frame that is not
comparable. **This is a larger effect than anything the paper channels have
produced and it is free and deterministic.** It is not adopted here: adopting a
rule from the sheet that discovered it is what this repo does not do. It needs
its own frame and its own pre-registration.

**Which channel carries the reach.** Of 17 same-sheet calls, 13 cite a channel
the mechanism is blind to — show-through, folds, tears — and the 3 it confirmed
all cite punch or staple, which it shares. So it confirms where the human read
the same evidence and is silent where the human read something else. That is
the mirror of 2026-09-06, when 15 of 16 calls rested on staples it could not
read, and it is a sharper statement of reach than 3 of 17 alone.

**DEFECTS #66, from the one false confirmation.** Both agreeing marks sat at
opposite edges, page A's along its bottom and page B's along its top, and
`flip_v` maps one band onto the other, so y carried nothing. A band is cheap in
the mirrored coordinate as well as the preserved one, and #64's table measured
only the preserved axis, so it answered half the question while appearing to
answer all of it.

**State of the channel:** it has now passed two pre-registered bars and is
still wired into nothing, because #63, #64 and #66 are open and a band of
candidates kills one axis whichever way the flip acts on it.

## Wired in, and what is left, 2026-09-07

**The paper confirmer ships.** `papermatch.sheet_confirmer`, restricted to
adjacent pairs (R8 in `docs/modules/paper.md`), passed to
`reassemble.group(confirms=...)` from `scripts/measure_reassemble.py`. On the
corpus it adds 14 paper attachments, 10 of 11 decisive verdicts same-sheet, 1
judged different (the known attach-04), 2 unjudged; the "7 of which 6" was
the small-channel probe's count, one channel of the two that ship (DEFECTS
#71). `pipeline/reassemble.py` imports neither channel.

What had blocked it was never the three band defects (DEFECTS #67): those were
priced into every measured rate. It was the absence of a document-level
measurement, which `scripts/wiring_effect.py` supplies for nothing.

### Open, in the order I would take them

**1. The extraction run, $8.07, and it is the only thing that costs money.**
`scripts/run_extraction.py`, batched, 223 documents. The pipeline has never
been run over the corpus; extraction is scored on 15 hand-labelled documents
only. The corpus-wide output the viewer needs rides along at no extra cost.
The re-score of the 15 does not: it is `make smoke` re-run at $1.54, because
only 8 of the 15 truth documents share a page set with a corpus document.
It matters because the published 87.4% and 82.5% describe a prompt that
stopped shipping on 2026-09-05 (`found_in`). Quoting them as they stand is
the one claim in this repo that is not defensible line by line.

**2. The TypeScript span viewer, cut-order item 7, entirely unbuilt.** Page
image, span overlays, cross-form disagreements, client-side search. It is the
only TypeScript in the project and the only way to *see* any of the output; a
reader currently has JSON and markdown. No backend and no hosted inference,
rejected deliberately on cost, injection and uptime.

**3. README with the real numbers**, cut-order item 6. It carries the
classifier and extraction figures and nothing about reassembly or the paper
channels.

### Open and NOT blocking anything

**DEFECTS #63, #64 and #66**, the band hole in three faces: a band of
candidates kills one axis whether the transform preserves it or mirrors it.
Closing it would lower the false-confirmation rate. It is not a gate, and
treating it as one was #67. Any fix is post-hoc by construction and needs a
fresh frame; the district 02 window holds roughly 28,000 matches
and only 155 were pulled.

**The bundle confusion has never been measured.** `same-bundle` was offered on
a 40-pair sheet and used zero times, so DEFECTS #63's central prediction is
still untested. A sitting that tests it needs a frame built to contain
bundle-mates, which the adjacent frame was not.

**Page parity does not replicate.** 74% even-start against 17% odd on district
02, Fisher p=0.0008; 3 of 7 on district 03. A district 02 phenomenon until
something says otherwise. Unadopted.

**The 2026-08-28 fixture list is unverified.** DEFECTS #69 found one of its
page numbers wrong; the rest have had the same amount of checking, which is
none.

---

# Day 8, 2026-09-07 evening: the run, the viewer, and four defects

## The corpus extraction run happened

`run_extraction.py --grouped --confirm`, batch
msgbatch_01Soru8fL644i1R2P1PQMjKd. **197 of 223 documents extracted, $9.31**
($0.29 more for the 5-document live smoke that preceded it, 5 of 5 clean).
The grouping it extracted is the regenerated one, confirmer live, 223
documents (176/44/3 by page count).

The 26 failures are two families, both characterized (#72, #73):

- **10 are the monthly API cap**, hit mid-batch:
  "You will regain access on 2026-10-01 at 00:00 UTC." Cap-shaped, not
  paper-shaped. Retrying costs about $0.35 and needs either October or a
  raised limit in the console. The $1.54 re-score is behind the same wall.
- **16 are a taxonomy finding, not a failure of extraction.** Every one is a
  census g1/w2 FACE the model reads as the pre-1966 form family: Form 3,
  Form 2, GWT-1, one "well test report"; the sampled revision is "1-1958".
  R8 validates form_class against the census taxonomy, which has no such
  class, so parsing refuses. The full 27-field responses are CACHED, so the
  decision, whenever taken, re-parses free. This is the
  `completion_face_legacy` class the stage-2 decided fix named, now with 16
  paid-for exhibits. Gated on a rule-5 proposal, unchanged.

Free passes over the 197: snap 1,678 of 4,742 values (35.4%), era gradient
as the module doc predicts (48-75% on 1983 paper, 7-17% on 1966); findings
151 clean, 46 carrying at least one, 40 errors led by depth.below_total at
19.

## The viewer exists, cut-order 7

`scripts/export_viewer.py` projects a finished run into `data/viewer/`
(never committed; 115 MB, 197 documents, 244 page images). `viewer/` is Vite +
React + strict TypeScript: three region tiers rendered distinctly (#29's
rule), the model band widened upward at display time (R5), click-to-zoom at
readable scale with the found_in label as caption (the 2026-09-03 rule),
attachment channels named per page, findings panel, client-side search. 23
vitest tests; the pre-commit hook runs them; a tier-2 test pins the TS
vocabularies against pipeline/extract.py. `cd viewer && npm run dev`.

## Four defects, all from running things end to end

- **#70** the wiring commit called papermatch and never imported it; the
  committed path could not run at all. Pin: a pyflakes undefined-name check
  over the whole repo (new dev dep, declared).
- **#71** "7 attachments, 6 correct" was the one-channel probe's count; the
  shipped two-channel confirmer makes 14 paper attachments, 10 of 11
  decisive verdicts same-sheet. Corrected in four places, pinned in tier 3.
- **#72** ten failures said "batch result errored" while the API named a
  dated usage cap; the reason now travels into the error string.
- **#73** the free passes crashed on a results row with nothing cached
  behind it, and export_viewer repeated the mistake hours after the entry
  was written. The pin covers all three walkers.

## Open, in order

1. **The legacy-form taxonomy call**, 16 cached documents, re-parse free,
   rule-5 proposal required. 2. **The cap-blocked 10 and the re-score**,
   about $1.90 total, after 2026-10-01 or a raised limit. 3. **README with
   the real numbers** (cut-order 6). 4. Sitting backlog: two unjudged paper
   attachments (1493451 p22+p23, 1494717 p20+p21) and one attached
   cannot-tell (1494774 p8+p9). 5. 1493616-0 p4 truncates the identity
   reader deterministically; that page is in no identity map.

## Later the same evening: the limit raised, the run completed, the re-score read

Alex raised the API limit and both blocked spends ran.

**The corpus run is API-complete: 206 of 223, $10.17 extraction total** (the
$0.29 smoke five, $9.31, then $0.57 for the ten the cap had refused; 9 of
those 10 extracted). The residue is now ONE family: **17 faces the model
reads as the pre-1966 form family**, the 16 known plus 1494483-0-15, which
came back "Form 2". All 17 full responses are cached; the taxonomy call
re-parses them free. Bundle re-exported: 206 documents, 253 page images;
snap 34.5%; findings 157 clean, 49 carrying at least one.

**The re-score, $1.84 actual against the $1.54 quote: status 71.5%, value
equivalent 85.1%**, against the published 87.4/82.5 on the retired prompt.
The flips were read before the number was written anywhere (rule 10's
habit), and 63 of 95 wrong statuses are fields the model never returned
where the parser looks: **three of the twenty documents came back
flattened**, every field a root-level key beside `document`. `dropped`
reported zero for them, which is DEFECTS #74; root keys are counted now.

**The shape is path-correlated and the rates are the finding: 3 of 20 on
the live streamed path, 0 of 206 on the batch path, same prompt hash.** The
re-score is a fair comparison (the published numbers were live-path too) and
it describes a path the corpus does not use. Two decisions follow, both
gated: whether the parser should accept the flattened shape (the keys are
exact schema field names; accepting changes a measured number, so it is
proposed, not slipped into a fix), and whether to spend about $0.77 on a
batched re-run of the same twenty documents to measure the deployed path.

Session spend in full: $12.09. $0.08 identity, $10.17 extraction, $1.84
re-score.

## Open, in the order I would take them, superseding the list above

1. The legacy-form taxonomy call, 17 cached documents, rule-5 proposal.
2. The flattened-shape decision, with the optional $0.77 batched re-score.
3. README with the real numbers (cut-order 6).
4. Sitting backlog: 1493451 p22+p23 and 1494717 p20+p21 unjudged, 1494774
   p8+p9 attached on a cannot-tell.
5. 1493616-0 p4 truncates the identity reader deterministically.
