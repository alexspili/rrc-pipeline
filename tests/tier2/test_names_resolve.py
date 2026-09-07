"""Tier 2: every name the source references is defined somewhere it can reach.

DEFECTS #70. Commit ce99e47 wired the paper confirmer into
scripts/measure_reassemble.py with three references to `papermatch` and no
import of it. The module imports cleanly, the calls sit inside main(), and
nothing in tiers 1 or 2 runs that path, so the hook passed a script that
raises NameError on every run.

An import-level test cannot catch this class, because importing executes
nothing inside a function body. What catches it is an undefined-name check,
which is pyflakes' job, so the repo does not grow a hand-rolled linter.

Restricted to the undefined-name message on purpose. pyflakes also reports
unused imports and redefinitions, which are style rather than defects, and a
test that fails on style teaches people to silence the test.
"""

from __future__ import annotations

import io
from pathlib import Path

import pyflakes.messages
from pyflakes.api import checkPath
from pyflakes.reporter import Reporter

ROOT = Path(__file__).resolve().parents[2]


class _Collector(Reporter):
    """Keeps the message objects instead of formatting them to a stream."""

    def __init__(self) -> None:
        super().__init__(io.StringIO(), io.StringIO())
        self.flakes: list = []

    def flake(self, message) -> None:  # noqa: D102 - pyflakes' own hook name
        self.flakes.append(message)


def source_files() -> list[Path]:
    """The repo's own Python: pipeline/, scripts/, tests/, and the root."""
    out: list[Path] = []
    for folder in ("pipeline", "scripts", "tests"):
        out += [p for p in sorted((ROOT / folder).rglob("*.py"))
                if "__pycache__" not in p.parts]
    out += sorted(ROOT.glob("*.py"))
    return out


def test_every_name_referenced_resolves_somewhere():
    """The pin for DEFECTS #70."""
    hits = []
    for path in source_files():
        reporter = _Collector()
        checkPath(str(path), reporter)
        for message in reporter.flakes:
            if isinstance(message, pyflakes.messages.UndefinedName):
                hits.append(
                    f"{path.relative_to(ROOT)}:{message.lineno}: "
                    + message.message % message.message_args)
    assert not hits, (
        "names referenced but defined nowhere reachable:\n  "
        + "\n  ".join(hits))
