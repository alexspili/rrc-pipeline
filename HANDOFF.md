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

1. ~~fetch + cached corpus~~ DONE. Corpus closed at 202/249/3,689.
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
--max-pages --start-page --order asc|desc --dry-run --force --no-strict
(experimental, known broken server-side). FETCH_DEBUG=1 prints request
headers/body + response p-block.
Behavior: client-side POTENTIAL filter by default; tripwire aborts if
num_images > 200k (means filters ignored / stale token); dedupe via
data/manifest.jsonl keyed on record_id; downloads to data/raw/<record_id>/;
verifies size; rate-paced. Known gaps: mint_token() NotImplemented; .env
loaded via `set -a; source .env; set +a` (no dotenv dep).

## Corpus status — CLOSED, do not pull more

data/raw/ on Alex's machine (~/Projects/RRC/data/raw). Final: **202 records,
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

- **1501720** Ducroz/Endeavor (Brazoria, 2007–09): 22pp combined file. G-1
  face p2, its Section III p5 (NON-CONTIGUOUS, P-4 between). W-4/W-4A/W-5/
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
6c. Per-revision templates PROBED and DEAD 2026-09-03, sixth candidate.
   Ceiling 18 of the 35 graded 1966 boxes against a pre-registered bar of
   26 and the layered join's 19, so the DEAD zone was reached on a free
   coverage gate and nothing was graded. `make template`, `make probebox`.
   The two halves came apart: registration works (96 anchors, residual
   0.0014, and the residual separates revisions with an order-of-magnitude
   gap) and the anchor inventory does not (80 pooled tokens on Section II,
   holding no `elevation`, `contractor`, `total` or `directional`, all of
   them printed on the paper). That is the anchor-poverty signature the
   Textract escalation names, not a layout-assumption failure, so the
   trigger condition as written is MET. It stays shut until one more
   number exists: whether the 18 regions the template does assert actually
   land, which coverage does not say and nobody has graded.
   The mechanism decision is still OPEN and the layered join is still the
   measured baseline: 77.3% overall, 100% on 1983, 54.3% on 1966.
7. Reassembly is unbuilt and is now the biggest known gap. It must pair in
   BOTH directions and settle candidates by identity-field agreement, not
   by position: the smoke pairing looked only forward and three of fifteen
   ground-truth documents turned out to be sections without their face.
   Design, evidence, worked cases and tier-1 test plan:
   docs/modules/reassemble.md.
