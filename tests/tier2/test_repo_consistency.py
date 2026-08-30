"""Tier 2: the repo's own invariants, checked against files on disk.

These are not pipeline tests. They pin claims the repository makes about
itself, which is where this project has actually been losing to drift:
CLAUDE.md's index pointed at files git never had (commit 8248354), and the
Makefile shipped recipes make cannot parse (DEFECTS #8).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- makefile

def test_makefile_recipe_lines_begin_with_tab():
    """Origin: DEFECTS #8. SETUP.md step 3 writes the Makefile from a heredoc
    indented inside the document; a plain heredoc does not strip that
    indentation, so the recipe lines lost their tabs and every target died
    with "missing separator". Nothing caught it because no test ran make.
    """
    lines = (ROOT / "Makefile").read_text().splitlines()
    target = re.compile(r"^[A-Za-z0-9_./%$()-]+:")

    offenders, in_recipe = [], False
    for n, line in enumerate(lines, 1):
        if target.match(line):
            in_recipe = True
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            in_recipe = False
            continue
        if in_recipe and not line.startswith("\t"):
            offenders.append((n, line))

    assert not offenders, (
        "Makefile recipe lines must start with a literal tab; make reports "
        "'missing separator' otherwise. Offending lines: "
        + "; ".join(f"{n}: {line!r}" for n, line in offenders)
    )
