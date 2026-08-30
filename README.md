# [repo-name]

An extraction pipeline over public [EDGAR filings / municipal permit records], and a record of
the workflow used to build it with an AI coding agent.

Two things are on offer here. The pipeline is real software with a measured accuracy number and
a merge gate. The workflow layer is the part most repositories leave out: the context file, the
per-module rules, the defect log, and the test tiers that make agent-generated code reviewable.

If you are evaluating me for work on AI-assisted engineering practice, the second half is the
part to read.

## What the pipeline does

[One paragraph. What goes in, what comes out, what it is for. Name the data source and the
record type. Keep it to five sentences.]

Current accuracy on the held-out set: **[N]%** per-field exact match across [N] labeled
documents. The number comes from `bench/`, is reproducible with `make eval`, and is printed on
every pull request.

## How it was built

I wrote this with an AI agent doing most of the typing. That is now common. What follows is the
structure I use to keep the output reviewable, which is less common, and which is the substance
of what I am showing you.

### CONTEXT.md is an index, not a manual

`CONTEXT.md` holds a stated budget of [N] lines and has stayed within it since [date]. It carries
the system description, the module map at one line per module, the invariants that hold across
module boundaries, and pointers into `docs/modules/`.

Detail lives in the per-module files. The budget exists because a context file that grows with the
codebase stops being read, by the agent and by people. Line count over time is in
`docs/metrics/context-size.md`.

### Rules come from defects, and carry their origin

Each file in `docs/modules/` ends in a numbered rule section. Every rule names the defect that
produced it and the test that pins it:

```
R4. Never construct a FieldResult without a source span.
    Origin: 2026-09-14, the agent returned confidence 0.9 on a field it had
    fabricated. With no span there was no way to check the claim.
    Pinned by: tests/tier1/test_field_result.py::test_span_required
```

There are [N] active rules across [N] modules. Every one has a defect behind it. `DEFECTS.md` is
the append-only log those origins point back to, and it includes the cases that produced no rule.

### Rules are retired by making them unrepresentable

A rule is a weaker fix than a type. Each module file has a `RETIRED` section listing rules removed
because the invariant moved into a constructor or a type signature, with the commit that did it.
[N] of [N] rules written have been retired this way.

The retirements are the part I would most want to talk through in an interview.

### Three test tiers, each with a trigger and a time budget

| Tier | Scope | Runs on | Budget |
|---|---|---|---|
| 1 | Pure functions, no I/O | Save | [N]s |
| 2 | Real boundaries, fixtures | Commit | [N]s |
| 3 | Eval harness on labeled data | Pull request | [N]m |

The split exists so the agent has a fast signal to iterate against and a slow one it cannot
iterate against. Tier 3 gates the merge and is the only tier that sees the held-out set.

The working rule is that a bug fix opens with a failing regression test. The commit history shows
this in order, which is the only way to check it.

## What the history shows

This was built over [N] weeks of intermittent work. The commits are unsquashed and in sequence
because the sequence is the evidence. Reviewing three or four consecutive fix commits will show
the loop running or will show that it does not.

## Measured

All from the repository. Nothing estimated.

- Per-field extraction accuracy: [N]%, on [N] held-out documents
- `CONTEXT.md`: [N] lines, budget [N]
- Active rules: [N] across [N] modules. Retired: [N]
- Logged AI-authored defects: [N]
- Tests: [N] across three tiers

## What this is not

It is not a framework, and there is nothing here to install. The pattern is four files and a test
layout, and it is worth what it is worth only alongside a codebase that generated the defects.

It is one engineer's practice on one project. I have not tested whether it holds across a team,
and I would treat that as an open question in any conversation about applying it.

## Running it

```
make install
make test        # tiers 1 and 2
make eval        # tier 3, prints the accuracy table
```

[Any credentials or data download step goes here.]

## Contact

Alex Spiliotopoulos
[email] · [linkedin.com/in/alexspiliotopoulos] · github.com/alexspili
