# Project Setup Protocol — run this before Claude Code touches anything
Companion to HANDOFF.md (project knowledge). This file is the mechanical
setup: exact commands, in order, plus the guardrails that make commit
mistakes hard. Total time ~15 minutes.

Decisions already made (context in HANDOFF.md, don't relitigate):
- GitHub-linked from commit one, PRIVATE until cut-order step 6 (eval
  numbers real, README placeholders gone). Flip to public + resume link
  happen together.
- History is never squashed. It is the workflow evidence. Messages get
  amended/reworded (private-phase only) with a scalpel, not a shredder.
- If history ends up rough, the fallback is silence: don't claim the
  workflow story in the README. Pipeline stands alone.

## Step 0 — identity check (do this FIRST; unfixable later without rewrite)

    git config user.email

Must print an email verified on the GitHub account (github.com/alexspili →
Settings → Emails). Commits with an unmatched email never appear on the
contribution graph and cannot be reattributed later. If wrong:

    git config --global user.email "THE_VERIFIED_EMAIL"
    git config --global user.name  "Alex Spiliotopoulos"

## Step 1 — repo, ignore-before-content

    mkdir -p ~/Projects/rrc-pipeline && cd ~/Projects/rrc-pipeline
    git init -b main
    cat > .gitignore <<'EOF'
    .venv/
    data/
    __pycache__/
    *.pyc
    .env
    .DS_Store
    node_modules/
    dist/
    *.log
    EOF
    git add .gitignore
    git commit -m "gitignore before content"

data/ is ignored WHOLE: fetched PDFs contain surface owners' names, home
addresses, phone numbers. They never enter git. Redacted fixtures only,
placed deliberately in tests/fixtures/, referenced by record id.

## Step 2 — secret-leak tripwire (pre-commit hook, 2 minutes, zero deps)

    mkdir -p .githooks
    cat > .githooks/pre-commit <<'EOF'
    #!/bin/sh
    # Block obvious secrets and bulk data from ever being committed.
    fail=0
    # 1. JWTs / bearer tokens in staged content
    if git diff --cached -U0 | grep -qE 'eyJ[A-Za-z0-9_-]{20,}'; then
      echo "BLOCKED: staged content contains a JWT-shaped string."; fail=1
    fi
    # 2. .env or anything under data/ staged despite gitignore
    if git diff --cached --name-only | grep -qE '^(\.env$|data/)'; then
      echo "BLOCKED: .env or data/ is staged."; fail=1
    fi
    # 3. fetched-record PDFs anywhere
    if git diff --cached --name-only | grep -qE 'Neubus0_.*\.pdf$'; then
      echo "BLOCKED: raw fetched PDF staged (contains personal data)."; fail=1
    fi
    # 4. any staged file over 5 MB
    for f in $(git diff --cached --name-only); do
      [ -f "$f" ] && [ "$(wc -c < "$f")" -gt 5000000 ] && {
        echo "BLOCKED: $f is >5MB."; fail=1; }
    done
    exit $fail
    EOF
    chmod +x .githooks/pre-commit
    git config core.hooksPath .githooks
    git add .githooks && git commit -m "pre-commit tripwire: secrets, data/, oversized files"

Note: the hook lives IN the repo and is itself a nice artifact. The redacted
cURL captures in docs/recon must have tokens replaced with REDACTED or the
hook will (correctly) block them.

## Step 3 — skeleton

    mkdir -p pipeline docs/recon docs/modules tests/tier1 tests/tier2 tests/tier3 tests/fixtures viewer
    printf 'NEUBUS_TOKEN=paste-daily-from-devtools\n' > .env.example
    printf 'requests>=2.31\n' > requirements.txt
    # NOTE: recipe lines below MUST begin with a literal tab. A plain heredoc
    # does not strip this document's own indentation, so copy-pasting this
    # block writes spaces and every target dies with "missing separator".
    # See DEFECTS #8. Verify with: grep -P '^\t' Makefile
    cat > Makefile <<'EOF'
    .PHONY: fetch test eval
    fetch:
    	@set -a; . ./.env; set +a; python3 fetch.py $(ARGS)
    test:
    	python3 -m pytest tests/tier1 tests/tier2 -q
    eval:
    	python3 -m pytest tests/tier3 -q
    EOF
    git add -A && git commit -m "skeleton: layout, env example, make targets"

## Step 4 — CLAUDE.md (this is the context-index file; Claude Code auto-reads it)

Create CLAUDE.md with, at minimum:
- One-paragraph project description (lift from HANDOFF.md).
- Line budget declaration for this file (e.g. 120 lines) stated inside it.
- Pointers: HANDOFF.md (all project knowledge), DEFECTS.md, docs/modules/.
- Standing rules for the agent, verbatim:
  1. Bug found → entry in DEFECTS.md and a failing test BEFORE the fix.
  2. Never send an external API a parameter value not observed from a
     working client without a bounded test (see DEFECTS.md #3).
  3. data/ and raw PDFs never get committed; fixtures are redacted copies
     in tests/fixtures only.
  4. Commit small and in sequence: failing test → fix → rule/doc. Never
     amend or rebase anything already pushed. Message format below.
  5. Propose before writing: for any new module, present page
     classes/schema/test plan in chat first.
- Commit message format: imperative first line stating WHY not just what
  ("fix rotation guard: classifier was eating sideways pages"), body
  optional, reference DEFECTS entry when applicable ("DEFECTS #6").

    git add CLAUDE.md && git commit -m "CLAUDE.md: context index + standing rules"

## Step 5 — carry over the artifacts

Copy in: fetch.py (latest patched version), HANDOFF.md, README.md (the
[N]-placeholder draft), DEFECTS.md seeded with the five banked entries from
HANDOFF.md, docs/recon/*.md (cURL captures, TOKENS REDACTED first).
Move the corpus: mv ~/Projects/RRC/data ./data  (ignored, stays local).
Recreate venv: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

    git add -A && git commit -m "carry over: fetch.py, recon captures (redacted), handoff, defect log, README draft"

Then verify the tripwire actually fires before trusting it:

    cp data/raw/*/Neubus0_*.pdf /tmp/x.pdf 2>/dev/null; git add -f /tmp 2>/dev/null
    # Type the token shape yourself at the shell. Do not paste a JWT-shaped
    # literal into this file: the hook scans staged content, so a literal here
    # makes SETUP.md itself unstageable. See DEFECTS #7.
    echo "token eyJ<20+ base64 chars>" > /tmp/leak.txt
    git add /tmp/leak.txt 2>/dev/null || true
    # simpler: stage .env.example edited to contain a real-looking eyJ... and
    # confirm `git commit` is blocked, then revert. Do not skip this check.

## Step 6 — GitHub, private, push everything

    gh auth status || gh auth login
    gh repo create rrc-pipeline --private --source . --push

If not using gh: create private repo in the web UI, then
    git remote add origin git@github.com:alexspili/rrc-pipeline.git
    git push -u origin main

Optional while private: GitHub → Settings → Profile → enable "Private
contributions" so the graph shows activity now. Public flip at step 6 of the
cut order retroactively publishes the full graph + history anyway.

## Step 7 — open Claude Code in the repo root

Opening prompt, roughly (written 2026-08-30; the corpus has grown since and
CLAUDE.md carries the live figures):
  "Read CLAUDE.md and HANDOFF.md. Corpus: data/raw, manifest at
   data/manifest.jsonl. Next milestone is the page
   classifier and the census table. Per standing rule 5: propose the page
   classes, the classifier prompt approach, and the tier-1 tests before
   writing any pipeline code."

## Commit-mistake prevention, summarized (the habits, not the tools)

1. `git status` glance before every `git add`. Never `git add .` blindly —
   prefer `git add -p` or explicit paths. (The hook is the backstop, not
   the practice.)
2. Five seconds per message: first line says WHY. "wip" is acceptable
   mid-struggle; "asdf" is not. Rough is fine; unnarratable is not.
3. Push at every stopping point. Unpushed local history is where cleanup
   temptation lives; pushed history is settled and honest.
4. Amend/reword only the latest unpushed commit (`git commit --amend`).
   Interactive rebase only over a small UNPUSHED span, only for messages,
   only while private. Never after push. Reserve history rewrite for actual
   leaked secrets (mandatory then).
5. Dead ends stay in history. The strict:"false" saga pattern — confused
   commits, then fix, then DEFECTS entry — is the portfolio content, not
   the mess.
6. Daily token: .env only, never exported in a committed script, never in
   docs/recon un-redacted. The hook catches eyJ-shaped strings; trust it
   but don't test it with a real token.
7. If a mistake lands anyway: secret → rewrite immediately + rotate (token
   is 24h public-user anyway, low stakes); wrong file → `git rm --cached` +
   amend if unpushed, follow-up removal commit if pushed; ugly message
   pushed → leave it, it's history now.
