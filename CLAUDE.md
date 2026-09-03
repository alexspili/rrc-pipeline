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
- Classifier and census DONE. **115 of 202 records (57%) contain a completion
  report**, hand-verified 15/15. Corpus sufficient; fetch.py stays closed.
- Stage-2 labels and the abstention fix DONE 2026-08-31. G-1 face precision
  64.7% -> **94.0%**, W-2 44.0% -> **57.4%**, whose interval still contains
  its own before figure so W-2 is not claimed. The failure was an unreadable
  form number, not a confused layout. Never quote the 83.6% arm accuracy as
  accuracy on the target classes. All of it, with the caveats that travel
  with each number: docs/modules/classify.md.
- Extraction: schema, extractor and validation rules built. Ground truth DONE
  2026-09-01, 405 rows over 15 documents, keyed blind from page images.
- Extraction SCORED 2026-09-01: headline (excl. doc 1 per DEFECTS #23)
  status 87.4%, value 82.5% where both present, reported BY ERA, never
  blended: 1983 near-perfect, 1966/1975 far worse. `make score`.
- Provenance boxes MEASURED 2026-09-03: not field locators (hit+near 60.9%
  vs the pre-registered 90%; 1966 bucket 11.4%). Values grounded, geometry
  confabulated (DEFECTS #29). **Mechanism decision OPEN** — five candidates
  measured and recorded, none adopted; a new approach is being tried next
  and is graded by the same instruments. docs/modules/extract.md → "The
  mechanism decision is OPEN".
- Then validation output review -> cross-form disagreement -> eval
  (`make eval`) -> TypeScript span viewer -> optional Postgres projection.
- Biggest known gap, unbuilt: page reassembly. Pair in both directions and
  settle by identity-field agreement, never by position.
  docs/modules/reassemble.md.

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
