#!/usr/bin/env python3
"""Refuse to overwrite hand-keyed work.

Pure. Origin: DEFECTS #26, where re-running a generator after a sheet had been
labelled replaced 405 hand-keyed rows with blanks.

The rule is not "warn" and not "back up first". It is refuse: a generator that
can destroy a day of somebody's work should not be able to, and a prompt or a
flag is a rule while this is a constructor.
"""

from __future__ import annotations

import csv
from pathlib import Path


class RefusedToOverwrite(Exception):
    """Raised rather than replacing a sheet somebody has filled in."""


def filled_rows(path: Path, column: str) -> int:
    """How many rows carry a value in `column`. Zero if the file is absent."""
    if not Path(path).exists():
        return 0
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return 0
        if column not in reader.fieldnames:
            raise ValueError(
                f"{path} has no column {column!r}; the guard cannot check a "
                f"column that is not there. Columns: {reader.fieldnames}")
        return sum(1 for row in reader if (row.get(column) or "").strip())


def refuse_if_filled(path: Path, column: str) -> None:
    """Raise if any row of `path` has been filled in.

    One filled row is enough. It is not a threshold, because a threshold would
    be a judgement about whose work is worth keeping.
    """
    path = Path(path)
    if not path.exists():
        return
    filled = filled_rows(path, column)
    if not filled:
        return
    with path.open(encoding="utf-8-sig", newline="") as fh:
        total = sum(1 for _ in csv.DictReader(fh))
    raise RefusedToOverwrite(
        f"{path} already carries labels: {filled} of {total} rows have a "
        f"{column}. Refusing to overwrite hand-keyed work. Move or delete the "
        "file deliberately if you really mean to regenerate it.")
