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

- fetch.py works end to end. Corpus 202 records, 249 files, 3,689 pages in
  data/raw (git-ignored), manifest at data/manifest.jsonl. Closed since
  2026-08-31; **reopening it is the declared next step** for the staple
  channel, about 110 more records.
- Classifier and census DONE. 115 of 202 records (57%) hold a completion
  report. G-1 face precision **94.0%**, W-2 **57.4%** whose interval contains
  its own before-figure, so W-2 is NOT established. Never quote 83.6% arm
  accuracy as accuracy on the target classes. Its `form_class` contradicts its
  own section heading on 31 of the 65 section labels it gave (DEFECTS #60).
- Extraction built and SCORED 2026-09-01: status **87.4%**, value **82.5%**,
  reported BY ERA and never blended. Those numbers describe a prompt that no
  longer ships — `found_in` was added 2026-09-05 — and re-scoring them is an
  unspent ~$1.50.
- Provenance CLOSED 2026-09-03: snap, then the widened model band, then page
  plus raw text, every region source-tagged. 77.3% highlight coverage.
- Extraction runs **batched**, scripts/run_extraction.py, $7.17 for 218
  documents. NOT YET RUN. It is the gated spend everything downstream waits
  behind.
- Reassembly BUILT and measured across four judging sittings; all 39 corpus
  attachments are judged. 25 of 32 multi-page documents clean. The six wrong
  ones left are same-form, same-well, different filing, which no form rule
  can reach.
- pipeline/paper.py confirms two pages are ONE SHEET from the marks on it:
  0 false confirmations in 850 negatives. It failed its pre-registered recall
  bar and shipped anyway on a measured gain, both facts recorded (DEFECTS
  #57, #58). `make eval` runs tests/tier3.
- Next: the staple channel, then the TypeScript span viewer, still unbuilt.

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
10. An abstention rate is not evidence until the abstentions are read one
   by one. "The paper will not support this" and "my rule is wrong" produce
   identical output, and only one of them is a finding. Origin: DEFECTS #30.
   The mirror of #29: there the model was confidently wrong and the shape
   check called it well-formed, here the mechanism was wrongly silent and
   the silence looked like integrity. Confidently wrong and wrongly silent
   are one pair, and a measurement is defended against both.

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
