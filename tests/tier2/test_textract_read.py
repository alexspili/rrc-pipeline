"""scripts/textract_read.py: a paid response is cached before it is judged.

DEFECTS #76: three pages were paid for, failed the shape check, and were
discarded. The cache is raw vendor data; parsing strictness is the
reader's job at build time, not the transport's job at spend time.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pytest

from scripts import textract_read as tr


class StubClient:
    """Answers with a response the parser refuses outright."""

    def detect_document_text(self, Document):
        return {"DocumentMetadata": {"Pages": 2}, "Blocks": []}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    out = tmp_path / "textract"
    monkeypatch.setattr(tr, "OUT", out)
    monkeypatch.setattr(tr, "INDEX", out / "index.jsonl")
    monkeypatch.setattr(tr, "page_png", lambda *a: b"png-bytes")
    monkeypatch.setattr(tr.time, "sleep", lambda s: None)
    return out


def test_paid_response_is_cached_even_when_the_shape_check_fails(sandbox):
    with pytest.raises(Exception):
        tr.send_page(StubClient(), {}, ("1490000", 0, 1), set())
    cached = list(sandbox.glob("*.json"))
    assert len(cached) == 1, "the paid response was discarded"
    assert json.loads(cached[0].read_text())["DocumentMetadata"]["Pages"] == 2
    index_rows = [json.loads(l) for l in (sandbox / "index.jsonl").open()]
    assert index_rows and index_rows[0]["record_id"] == "1490000"


def test_a_cached_page_is_never_resent(sandbox):
    class Exploding:
        def detect_document_text(self, Document):
            raise AssertionError("re-sent a cached page")

    import hashlib
    known = {hashlib.sha256(b"png-bytes").hexdigest()}
    outcome = tr.send_page(Exploding(), {}, ("1490000", 0, 1), known)
    assert outcome == "cached"
