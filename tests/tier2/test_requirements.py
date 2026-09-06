"""Tier 2: everything the repo imports is something the repo declares.

DEFECTS #52. Three committed scripts imported numpy and scipy while neither
appeared in requirements.txt. They ran only because a previous experiment had
left both in .venv. On a clean checkout they raise ImportError, and because
they are measurement scripts the first symptom is a measurement that silently
did not happen.

Walks the source rather than trusting a list, so a new import is caught the
day it lands.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("pipeline", "scripts", "tests")

#: Names the repo supplies itself.
LOCAL = {"pipeline", "fetch", "scripts", "tests"}

#: Distribution name -> the module name it installs under, where they differ.
INSTALLS_AS = {"pillow": "PIL", "anthropic": "anthropic", "requests": "requests",
               "openpyxl": "openpyxl", "pytest": "pytest", "numpy": "numpy",
               "scipy": "scipy"}


def declared() -> set[str]:
    """Module names requirements.txt makes available."""
    text = (ROOT / "requirements.txt").read_text()
    out = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name = line.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
        out.add(INSTALLS_AS.get(name, name))
    return out


def imported() -> dict[str, set[Path]]:
    """Top-level module names imported anywhere in the repo's own source."""
    found: dict[str, set[Path]] = {}
    for folder in SOURCE_DIRS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:                      # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    # `from . import x` has no module; relative imports are local
                    if node.level or not node.module:
                        continue
                    names = [node.module]
                else:
                    continue
                for name in names:
                    found.setdefault(name.split(".")[0], set()).add(path)
    return found


def test_every_third_party_import_is_declared():
    """The pin for DEFECTS #52."""
    have = declared() | set(sys.stdlib_module_names) | LOCAL
    missing = {name: sorted(str(p.relative_to(ROOT)) for p in where)
               for name, where in imported().items() if name not in have}
    assert not missing, (
        "imported but not in requirements.txt: "
        + "; ".join(f"{n} ({', '.join(f)})" for n, f in sorted(missing.items())))


def test_the_array_dependencies_are_declared_with_a_reason():
    """A bare pin says nothing. requirements.txt annotates every line with its
    consumer, and these two are the ones the repo had to argue for.
    """
    text = (ROOT / "requirements.txt").read_text()
    for name in ("numpy", "scipy"):
        line = [l for l in text.splitlines()
                if l.strip().lower().startswith(name)]
        assert line, f"{name} is not declared"
        assert "#" in line[0], f"{name} is declared with no reason given"
