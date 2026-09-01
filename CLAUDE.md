# CLAUDE.md — context index
Line budget for this file: 120. It is an index, not a manual. Detail lives in
the files it points to. If this file grows past budget, move content out.

## What this project is

An extraction pipeline over the Texas Railroad Commission's imaged well
records: fetch scanned well files from the state archive, classify pages,
extract G-1/W-2 completion reports to structured JSON with per-value source
spans, validate with deterministic rules, cross-check facts that repeat
across forms in the same file, and measure accuracy and cost against a
hand-labeled set. Built by one engineer with AI assistance; this repo also
carries the working practice that keeps that output reviewable (this file,
DEFECTS.md, three-tier tests). It is a portfolio project: every claim in it
must be defensible line by line in an interview.

## Read next

- HANDOFF.md — all project knowledge: verified API chain, corpus facts,
  document findings, pipeline design decisions, cost figures, cut order.
  Read it before proposing or writing anything.
- DEFECTS.md — append-only defect log. Five entries predate the code.
- SETUP.md — repo mechanics, guardrails, commit rules in full.
- docs/modules/ — per-module rules with defect origins (created as earned).
- docs/recon/ — raw captures behind fetch.py (tokens redacted).

## Current state

- fetch.py works end to end; corpus is CLOSED: 202 records, 249 files,
  3,689 pages in data/raw (git-ignored), manifest at data/manifest.jsonl.
- Page classifier done and measured. Census run 2026-08-31 on 3,689 pages,
  $4.25 batched, 0.4% parse failures, reconciled with none missing.
- **115 of 202 records (57%) contain a completion report.** Hand-verified
  15/15 on a seeded sample. Corpus is sufficient; fetch.py stays closed.
- The G-1 vs W-2 split is NOT yet reliable: sectionless pages carry no form
  number and get attributed by guess. Do not quote a per-form split. The
  83.6% arm accuracy is a uniform-sample number on 60 pages containing 0
  G-1 pages; never quote it as accuracy on the target classes. Both caveats
  in full: docs/modules/classify.md.
- Extraction ground truth DONE 2026-09-01: 405 rows, 15 documents, keyed
  blind from page images. Protocol docs/labeling-protocol-extract.md.
- NEXT, in order: (1) re-run the 20-doc smoke, ~$1.41, the prompt changed
  when `page_not_in_document` was added so the cache is invalidated;
  (2) score against the ground truth. Reporting rules fixed in advance:
  exclude document 1 from the headline (DEFECTS #23, it is the document
  the schema was designed on), and report documents 6/8/9 separately as
  absence detection (DEFECTS #25, they are sections without their face).
- Stage-2 labels DONE 2026-08-31, 143 pages. **G-1 face precision 64.7%
  +/-4.5pp, W-2 face 44.0% +/-5.2pp.** All 20 drawn faces whose printed form
  number is illegible were misclassified; where the number is legible the
  model is essentially never wrong. The split is measurable and still not
  reportable as a count. docs/modules/classify.md → Stage 2 results.
- Fix DECIDED 2026-08-31, NOT implemented, gated: abstain rather than guess.
  A completion face with no legible form number gets
  `completion_face_unknown_form`; the pre-numbering family (Form 2/3, GWT-1)
  gets `completion_face_legacy`. The 115 headline is a union over all four
  completion classes, so it does not move. Needs a rule-5 proposal for the
  PageLabel invariant, then a before/after on the stage-2 labels. Design and
  test plan: docs/modules/classify.md → The decided fix.
- Then extraction per the cut order in HANDOFF.md → validation →
  cross-form disagreement → eval (`make eval`) → TypeScript span viewer →
  optional Postgres projection.
- Open finding, no implementation: page grouping. 157 pages / 83 records are
  form pages carrying no form number, plus 137 non-face completion pages.
  See docs/modules/classify.md.

## Standing rules

1. Bug found → entry appended to DEFECTS.md AND a failing test written
   BEFORE the fix. No silent fixes, ever. The log and the test are the
   deliverable; the fix is the afterthought.
2. Never send an external API a parameter value not observed from a working
   client without a bounded test first. Origin: DEFECTS #3 — strict:"false"
   silently disabled all server-side filtering while the response echoed
   our filters back.
3. data/ and raw fetched PDFs are never committed — they contain personal
   information (surface owners' names, addresses, phone numbers). Fixtures
   are redacted copies placed deliberately in tests/fixtures/, referenced
   by record id. A pre-commit hook enforces this; do not work around it.
4. Commit small and in sequence: failing test → fix → rule or doc update.
   Never amend or rebase anything already pushed. Dead ends stay in
   history; the history is the workflow evidence.
5. Propose before writing. For any new module: present the interface,
   page classes or schema, and the tier-1 test plan in chat, get agreement,
   then write code.
6. Tests are tiered: tier1 pure functions no I/O (runs on save), tier2 real
   boundaries with fixtures (on commit), tier3 eval harness on labeled data
   (gates merge). A rule in docs/modules/ that gets enforced by a type or
   constructor moves to that module's RETIRED section, citing the commit.
7. Model calls: Haiku for page classification, Sonnet for extraction, batch
   API by default. Every extracted value carries a source span. Cache model
   outputs by (document hash, prompt hash); never re-infer unchanged pairs.
8. Writing style for any prose (README, docs, comments): plain and
   declarative. No em dashes, no marketing adjectives, no absolutes, no
   "turns X into Y" constructions. Only claims backed by something in the
   repo. Numbers are measured or absent — never estimated in prose.
9. A fix's report states what remains, not just what it removed; the
   residue gets characterized before the fix is called done. Origin:
   DEFECTS #11 cut a leak from 373 pages to 147 and stopped, and #20 found
   all 147 were still leaks; #15's "actual" counts were still over, which
   #16 found the same day; and the general form of the W-15 header rule
   was caught only because its residue was measured before it shipped.

## Commit message format

Imperative first line stating WHY, not just what:
  good: "fix rotation guard: classifier was eating sideways pages"
  bad:  "fix bug", "update classify.py"
Reference defect entries where applicable: "(DEFECTS #6)". Body optional.
"wip:" prefix is acceptable mid-struggle; unnarratable messages are not.

## Environment

- Python 3.11+ in .venv; deps in requirements.txt (requests now; anthropic,
  pypdf, pillow, boto3 as the pipeline grows). No new deps without saying so.
- NEUBUS_TOKEN pasted daily into .env (24h public JWT); loaded via
  `set -a; . ./.env; set +a` or `make fetch`. Never printed, never committed.
- Anthropic API key: ANTHROPIC_API_KEY in .env, same rules.
- Rate limits are honored by reading the server's own headers; fetch.py is
  the reference implementation of that pattern.
