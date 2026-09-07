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

- HANDOFF.md — all project knowledge: API chain, corpus facts, document
  findings, design decisions, costs, cut order. Read it before proposing.
- DEFECTS.md — append-only defect log. Five entries predate the code.
- SETUP.md — repo mechanics, guardrails, commit rules in full.
- docs/modules/ — per-module rules with defect origins; docs/recon/ — raw
  captures behind fetch.py, tokens redacted.

## Current state

- fetch.py works. Corpus 357 records, 405 files, 6,443 pages in data/raw
  (git-ignored). TWO populations, never blended: district 03 closed, which
  every measurement rests on, and district 02, 155 records from 2026-09-07.
  paper_record_split.csv: 91 dev / 111 held out / 155 frame, last two barred.
- Classifier and census DONE. 115 of the 202 records in district 03 (57%) hold
  a completion report. G-1 face precision **94.0%**; W-2 NOT established;
  never quote 83.6% as accuracy on the target classes. `form_class` on back
  pages self-contradicts 31 times in 65 and MAY NOT define a negative (#60,
  #62).
- Extraction SCORED 2026-09-01: **87.4%** status, **82.5%** value, by era, on
  a prompt that no longer ships; re-scoring ~$1.50. Provenance CLOSED. Batched
  run **$7.17, NOT YET RUN**: the gated spend everything waits on.
- Reassembly BUILT, 25 of 32 multi-page documents clean; the six wrong are
  same-form same-well different-filing, beyond any form rule.
- pipeline/paper.py confirms two pages are ONE SHEET from the marks on it: 0
  false confirmations in 850. It failed its pre-registered recall bar and
  shipped anyway on a measured gain (#57, #58). `make eval` runs tier3.
- A SECOND channel, `compare_small`, reads marks under MIN_MARK_AREA, frozen
  1a01829, and PASSED both pre-registered bars: cross-record 1 of 400 (bound
  1.180%) and the district 02 sitting 1 of 20 false, 3 of 17 same-sheet. Not a
  staple detector. **Wired into nothing**, and what blocks it is NOT #63/#64/
  #66 — those are priced into the measured rates (#67) — but the absence of a
  DOCUMENT-level measurement: every paper number is per pair.
- Its real findings are not the pass. `same-bundle` was used 0 times so the
  bundle confusion is STILL unmeasured; the adjacent false rate is 5.0% against
  0.25% and 20 pairs cannot resolve it; and page parity predicts same-sheet at
  14 of 19 even-start against 3 of 18 odd (Fisher p=0.0008), a 78% prior, so a
  screen and not a confirmer. Unbuilt, not to be adopted from its own sheet.
- The area floor never kept printing out, MAX_ASPECT did; every page is read at
  its own resolution (#61).
- Next: decide on the parity prior, then the TypeScript span viewer, unbuilt.

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
