"""Tier 2: the fetch CLI's guards, on the argument parser rather than the API.

No network. These load fetch.py by path, which is how this repo loads a script
from a test, and exercise the checks that stop a run doing something silently
wrong.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "fetch.py"


def fetch():
    spec = importlib.util.spec_from_file_location("fetch_mod", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_order_desc_refuses_because_it_does_not_bind():
    """DEFECTS #65. Run the same query ascending and descending and the first
    four record ids are identical: the flag is accepted and changes nothing.

    A flag that silently does nothing is worse than no flag, because two
    documents claimed it worked and a future measurement would have trusted
    them. It now refuses and names `--start-page`, which does work.
    """
    module = fetch()
    with pytest.raises(SystemExit) as raised:
        module.check_order("desc")
    message = str(raised.value)
    assert "start-page" in message
    assert "#65" in message

    module.check_order("asc")          # the only value that means anything


def test_the_dry_run_cannot_page_forever():
    """DEFECTS #4: an unfiltered dry run paged a 1.9M row result. The default
    cap is the fix and it belongs to the parser, not to a habit."""
    source = SCRIPT.read_text()
    assert "args.max_pages = 3" in source
    assert "dry run: defaulting to --max-pages 3" in source


def test_the_archive_scale_tripwire_is_still_armed():
    """DEFECTS #3: a stale session returns the whole archive with the filters
    echoed back. The tripwire is what catches it now that a truncated cookie
    can produce the same state without any warning."""
    source = SCRIPT.read_text()
    assert "200_000" in source
    assert "--force" in source
