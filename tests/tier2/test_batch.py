"""Tier 2: the Batch API path, against a stubbed batches client.

No network. What is covered is everything around the call, which for a batch is
most of the risk: results come back in arbitrary order keyed only by custom_id,
a page can be missing from them entirely, and 3,689 image requests are 1.22 GB
and cannot go in one batch.

CLAUDE.md rule 7 makes batch the default. The census is the first run large
enough for it to matter, and it runs once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pipeline import classify
from pipeline import pageclass as pc

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pages.pdf"

GOOD = ('{"form_class":"g1","part":"face","orientation":"up",'
        '"confidence":"high","alt_class":null,"form_number_legible":true}')


# ------------------------------------------------------------- stub batches API

@dataclass
class _Usage:
    input_tokens: int = 1500
    output_tokens: int = 40


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Msg:
    content: list
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Result:
    type: str
    message: _Msg | None = None


@dataclass
class _Entry:
    custom_id: str
    result: _Result


class StubBatches:
    """Mimics client.messages.batches: create, retrieve, results."""

    def __init__(self, body=GOOD, *, shuffle=True, drop=(), errored=()):
        self.body, self.shuffle = body, shuffle
        self.drop, self.errored = set(drop), set(errored)
        self.submitted: list[list] = []

    def create(self, requests):
        self.submitted.append(list(requests))
        return type("B", (), {"id": f"batch_{len(self.submitted)}",
                              "processing_status": "ended"})()

    def retrieve(self, batch_id):
        return type("B", (), {"id": batch_id, "processing_status": "ended"})()

    def results(self, batch_id):
        index = int(batch_id.split("_")[1]) - 1
        out = []
        for req in self.submitted[index]:
            cid = req["custom_id"]
            if cid in self.drop:
                continue
            if cid in self.errored:
                out.append(_Entry(cid, _Result("errored")))
            else:
                out.append(_Entry(cid, _Result(
                    "succeeded", _Msg([_Block(self.body)]))))
        # Results arrive in arbitrary order. Reversing is the cheapest way to
        # guarantee the code never relies on position.
        return reversed(out) if self.shuffle else iter(out)


class StubClient:
    def __init__(self, **kw):
        self.messages = type("M", (), {"batches": StubBatches(**kw)})()


def _pages(n):
    return [("1493418", 0, p, FIXTURE) for p in range(1, n + 1)]


# ---------------------------------------------------------------- chunking

def test_requests_are_chunked_under_the_payload_ceiling():
    """3,689 vision requests are 1.22 GB at ~331 KB each; the documented batch
    limit is 256 MB. One batch is not an option and the failure would arrive
    only after building the whole payload.
    """
    reqs = [{"custom_id": f"1-0-{i}", "params": {"x": "y" * 100_000}}
            for i in range(20)]
    chunks = classify.chunk_requests(reqs, max_bytes=500_000, max_requests=100)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) == len(reqs)
    for chunk in chunks:
        assert len(json.dumps(chunk)) <= 500_000 or len(chunk) == 1


def test_chunking_also_respects_a_request_count_ceiling():
    reqs = [{"custom_id": f"1-0-{i}", "params": {}} for i in range(25)]
    chunks = classify.chunk_requests(reqs, max_bytes=10_000_000, max_requests=10)
    assert [len(c) for c in chunks] == [10, 10, 5]


def test_a_single_oversized_request_is_not_silently_dropped():
    """Better one over-limit batch that fails loudly than a page missing from
    the census with nothing to say so.
    """
    reqs = [{"custom_id": "1-0-1", "params": {"x": "y" * 1_000_000}}]
    chunks = classify.chunk_requests(reqs, max_bytes=1000, max_requests=100)
    assert [len(c) for c in chunks] == [1]


# ------------------------------------------------------------------ collection

def test_results_are_matched_by_custom_id_not_by_position():
    """The stub returns results reversed. Keying by position would attach every
    label to the wrong page, and every page would still have a plausible label.
    """
    api = StubClient()
    attempts = classify.run_batched(
        api, "vision_1000", _pages(3), cache=None,
        doc_hashes={FIXTURE: "abc"})
    assert set(attempts) == {"1493418-0-1", "1493418-0-2", "1493418-0-3"}
    for page_id, attempt in attempts.items():
        assert attempt.label is not None
        assert attempt.label.page == pc.parse_page_id(page_id)[2]


def test_an_errored_result_becomes_an_attempt_not_an_exception():
    api = StubClient(errored={"1493418-0-2"})
    attempts = classify.run_batched(api, "vision_1000", _pages(3), cache=None,
                                    doc_hashes={FIXTURE: "abc"})
    assert attempts["1493418-0-2"].label is None
    assert "errored" in attempts["1493418-0-2"].error
    assert attempts["1493418-0-1"].label is not None


def test_a_page_missing_from_the_results_is_reported(capsys):
    """A silently absent page becomes a hole in the census that nothing counts.
    It must come back as an Attempt carrying an error.
    """
    api = StubClient(drop={"1493418-0-2"})
    attempts = classify.run_batched(api, "vision_1000", _pages(3), cache=None,
                                    doc_hashes={FIXTURE: "abc"})
    assert set(attempts) == {"1493418-0-1", "1493418-0-2", "1493418-0-3"}
    assert attempts["1493418-0-2"].label is None
    assert "no result" in attempts["1493418-0-2"].error


def test_a_malformed_body_is_recorded_like_it_is_on_the_live_path():
    api = StubClient(body="I think this is a G-1?")
    attempts = classify.run_batched(api, "vision_1000", _pages(2), cache=None,
                                    doc_hashes={FIXTURE: "abc"})
    assert all(a.label is None and a.error for a in attempts.values())


# --------------------------------------------------------------------- caching

def test_cached_pages_generate_no_requests(tmp_path):
    """CLAUDE.md rule 7. A resumed census must not re-infer, and re-spending on
    3,689 pages because a run died at page 3,000 is the case this exists for.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl")
    api = StubClient()

    first = classify.run_batched(api, "vision_1000", _pages(3), cache=cache,
                                 doc_hashes={FIXTURE: "abc"})
    submitted_first = sum(len(b) for b in api.messages.batches.submitted)

    api2 = StubClient()
    second = classify.run_batched(api2, "vision_1000", _pages(3), cache=cache,
                                  doc_hashes={FIXTURE: "abc"})
    submitted_second = sum(len(b) for b in api2.messages.batches.submitted)

    assert submitted_first == 3
    assert submitted_second == 0
    assert all(a.cached for a in second.values())
    assert {p: a.label.form_class for p, a in first.items()} == \
           {p: a.label.form_class for p, a in second.items()}


def test_a_partly_cached_run_only_requests_the_rest(tmp_path):
    """The resume case: a census that died partway re-requests only what it
    never got. The fixture has three pages, so cache one and ask for all three.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl")
    classify.run_batched(StubClient(), "vision_1000", _pages(1), cache=cache,
                         doc_hashes={FIXTURE: "abc"})
    api = StubClient()
    attempts = classify.run_batched(api, "vision_1000", _pages(3), cache=cache,
                                    doc_hashes={FIXTURE: "abc"})
    assert sum(len(b) for b in api.messages.batches.submitted) == 2
    assert len(attempts) == 3
    assert attempts["1493418-0-1"].cached is True
    assert attempts["1493418-0-3"].cached is False
