"""Tier 2: extraction through the Batch API, against a stubbed batches client.

No network. What is covered is everything around the call, which for a batch is
where the risk lives: results come back keyed only by custom_id in arbitrary
order, a document can be missing from them entirely, and a document that
errored must come back saying so rather than vanishing.

The classifier has run batched since the census (tests/tier2/test_batch.py).
Extraction has not, and it is the expensive half: 238 completion faces at the
standard rate against half that batched. CLAUDE.md rule 7 makes batch the
default; this is extraction catching up with the rule.

The cached-truncation test is DEFECTS #47 and is not about batching. It is here
because the guard it pins is the guard the batch path had to share.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pipeline import classify
from pipeline import extractor

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pages.pdf"

GOOD = json.dumps({
    "document": {"form_class": "w2",
                 "form_revision": {"status": "present", "value": "Rev. 6/30/75",
                                   "raw": "Rev. 6/30/75", "page": 1,
                                   "box": [0.7, 0.02, 0.95, 0.05]}},
    "identity": {"lease_name": {"status": "present", "value": "Fleck",
                                "raw": "Fleck", "page": 1,
                                "box": [0.1, 0.2, 0.3, 0.25],
                                "found_in": "5. Lease Name"}},
})


# ----------------------------------------------------------- stub batches API

@dataclass
class _Usage:
    input_tokens: int = 4200
    output_tokens: int = 5100


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Message:
    content: list
    usage: _Usage = field(default_factory=_Usage)
    stop_reason: str = "end_turn"


@dataclass
class _Result:
    type: str
    message: _Message | None = None


@dataclass
class _Entry:
    custom_id: str
    result: _Result


@dataclass
class _Batch:
    id: str
    processing_status: str = "ended"
    request_counts: object = None


class _Batches:
    """Answers every request, in reversed order, unless told otherwise."""

    def __init__(self, *, body=GOOD, drop=(), errored=(),
                 stop_reason="end_turn"):
        self.body, self.drop = body, set(drop)
        self.errored, self.stop_reason = set(errored), stop_reason
        self.submitted: list[list[dict]] = []
        self._entries: dict[str, list[_Entry]] = {}

    def create(self, *, requests):
        self.submitted.append(requests)
        bid = f"batch_{len(self.submitted)}"
        rows = []
        for request in reversed(requests):          # order is never position
            cid = request["custom_id"]
            if cid in self.drop:
                continue
            if cid in self.errored:
                rows.append(_Entry(cid, _Result("errored")))
                continue
            rows.append(_Entry(cid, _Result("succeeded", _Message(
                content=[_Block(self.body)],
                stop_reason=self.stop_reason))))
        self._entries[bid] = rows
        return _Batch(bid)

    def retrieve(self, bid):
        return _Batch(bid)

    def results(self, bid):
        return iter(self._entries[bid])


class _Stream:
    """The SDK's streaming context manager, reduced to what is used."""

    def __init__(self, message, seen):
        self._message, self._seen = message, seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        self._seen.append("streamed")
        return self._message


class _Messages:
    def __init__(self, batches, live=None):
        self.batches = batches
        self.live = live
        self.calls: list[str] = []

    def create(self, **kwargs):                     # pragma: no cover
        raise AssertionError(
            "extraction streams; a plain create() can outlast the timeout")

    def stream(self, **kwargs):
        if self.live is None:
            raise AssertionError("this path must not make a live call")
        self.calls.append("stream")
        return _Stream(self.live, self.calls)


class _Api:
    def __init__(self, batches, live=None):
        self.messages = _Messages(batches, live)


def _docs():
    return [{"custom_id": "1493495-0-9", "record_id": "1493495",
             "file_index": 0, "pdf": FIXTURE, "pages": (1,)},
            {"custom_id": "1493495-0-11", "record_id": "1493495",
             "file_index": 0, "pdf": FIXTURE, "pages": (2,)}]


# --------------------------------------------------------------- the batch path

def test_a_document_is_matched_by_custom_id_and_never_by_position():
    """The stub answers in reversed order on purpose. Anything that reads
    results positionally pairs each document with the other one's values.
    """
    batches = _Batches()
    out = extractor.run_batched(_Api(batches), _docs(), cache=None)
    assert set(out) == {"1493495-0-9", "1493495-0-11"}
    assert all(r.report is not None for r in out.values())
    assert out["1493495-0-9"].pages == (1,)
    assert out["1493495-0-11"].pages == (2,)


def test_a_document_absent_from_the_results_comes_back_saying_so():
    """A dropped document must be a loud hole, not a quiet one. Standing rule
    9: the residue gets counted.
    """
    batches = _Batches(drop=["1493495-0-11"])
    out = extractor.run_batched(_Api(batches), _docs(), cache=None)
    assert set(out) == {"1493495-0-9", "1493495-0-11"}
    missing = out["1493495-0-11"]
    assert missing.report is None
    assert "no result" in missing.error


def test_a_failed_document_carries_the_failure_not_a_report():
    batches = _Batches(errored=["1493495-0-9"])
    out = extractor.run_batched(_Api(batches), _docs(), cache=None)
    assert out["1493495-0-9"].report is None
    assert "errored" in out["1493495-0-9"].error
    assert out["1493495-0-11"].report is not None


def test_a_cached_document_never_becomes_a_request(tmp_path):
    """CLAUDE.md rule 7. This is what makes a died-halfway run resumable for
    nothing, and it is the whole reason the corpus run is affordable twice.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    docs = _docs()
    key = extractor.cache_key(cache, docs[0]["pdf"], docs[0]["pages"])
    cache.put(key, {"body": GOOD, "input_tokens": 10, "output_tokens": 20,
                    "stop_reason": "end_turn"})

    batches = _Batches()
    out = extractor.run_batched(_Api(batches), docs, cache=cache)
    submitted = [r["custom_id"] for chunk in batches.submitted for r in chunk]
    assert submitted == ["1493495-0-11"]
    assert out["1493495-0-9"].cached is True
    assert out["1493495-0-9"].input_tokens == 10


def test_nothing_is_submitted_when_everything_is_cached(tmp_path):
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    for doc in _docs():
        cache.put(extractor.cache_key(cache, doc["pdf"], doc["pages"]),
                  {"body": GOOD, "input_tokens": 1, "output_tokens": 2,
                   "stop_reason": "end_turn"})
    batches = _Batches()
    out = extractor.run_batched(_Api(batches), _docs(), cache=cache)
    assert batches.submitted == []
    assert all(r.cached for r in out.values())


def test_a_request_carries_the_prompt_that_is_shipping():
    """DEFECTS #45: a probe measured one prompt and the run shipped another.
    The batch path builds its own request body, which is a second place for
    the two to drift apart.
    """
    batches = _Batches()
    extractor.run_batched(_Api(batches), _docs(), cache=None)
    request = batches.submitted[0][0]
    assert request["params"]["system"] == extractor.SYSTEM
    assert request["params"]["model"] == extractor.MODEL
    assert request["params"]["max_tokens"] == extractor.MAX_TOKENS


def test_a_batch_is_split_under_the_documented_ceilings():
    """One extraction request is several hundred KB of page images. The
    classifier's chunker is reused rather than copied; this pins that it is
    actually applied here.
    """
    batches = _Batches()
    extractor.run_batched(_Api(batches), _docs(), cache=None,
                          max_requests=1)
    assert [len(chunk) for chunk in batches.submitted] == [1, 1]


def test_a_batched_truncation_is_a_truncation_and_is_not_cached(tmp_path):
    """The guard that DEFECTS #14 and the max_tokens raise put on the live
    path. A batch that hits the cap must not store the fragment: the cache key
    does not include max_tokens, so a stored truncation outlives the cap.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    batches = _Batches(body='{"document": {"form_cla',
                       stop_reason="max_tokens")
    out = extractor.run_batched(_Api(batches), _docs(), cache=cache)
    assert all(r.report is None for r in out.values())
    assert all("truncated" in r.error for r in out.values())
    assert cache.get(extractor.cache_key(
        cache, FIXTURE, (1,))) is None


# ------------------------------------------------------- DEFECTS #47, the guard

def test_a_cached_truncation_is_still_a_truncation(tmp_path):
    """DEFECTS #47. `extract_document` says it shares one guard between the
    cached and the fresh path and it did not: the truncation check sat below
    the cache-hit return, so a truncation stored before the guard existed came
    back forever as malformed JSON.

    Four such entries are in data/extract/cache_smoke.jsonl right now, all at
    the old 8000-token cap.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    key = extractor.cache_key(cache, FIXTURE, (1,))
    cache.put(key, {"body": '{"document": {"form_cla', "input_tokens": 4000,
                    "output_tokens": 8000, "stop_reason": "max_tokens"})

    result = extractor.extract_document(
        _Api(_Batches()), FIXTURE, (1,), record_id="1493495", file_index=0,
        cache=cache)
    assert result.report is None
    assert "truncated" in result.error
    assert "8000 output tokens" in result.error


def test_a_cached_document_that_completed_is_untouched_by_that_guard(tmp_path):
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    cache.put(extractor.cache_key(cache, FIXTURE, (1,)),
              {"body": GOOD, "input_tokens": 10, "output_tokens": 20,
               "stop_reason": "end_turn"})
    result = extractor.extract_document(
        _Api(_Batches()), FIXTURE, (1,), record_id="1493495", file_index=0,
        cache=cache)
    assert result.error is None
    assert result.report.form_class == "w2"


def test_an_old_cache_entry_with_no_stop_reason_still_parses(tmp_path):
    """Entries written before stop_reason was recorded carry no such key. The
    guard must read that as "not a truncation", not blow up on it.
    """
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    cache.put(extractor.cache_key(cache, FIXTURE, (1,)),
              {"body": GOOD, "input_tokens": 10, "output_tokens": 20})
    result = extractor.extract_document(
        _Api(_Batches()), FIXTURE, (1,), record_id="1493495", file_index=0,
        cache=cache)
    assert result.error is None


# ------------------------------------------------------------------- the price

def test_batching_is_half_price():
    """The reason any of this exists. Pinned so the discount cannot drift
    away from the number the run was budgeted on (DEFECTS #21 is the same
    lesson about a price nobody checked).
    """
    from pipeline.extractor import Extraction
    one = Extraction(report=None, record_id="x", pages=(1,),
                     input_tokens=1_000_000, output_tokens=1_000_000,
                     cached=False)
    assert one.cost_usd() == pytest.approx(12.00)
    assert one.cost_usd(batched=True) == pytest.approx(6.00)


# ------------------------------------------- the cap, and what it is guarding

def test_the_cap_clears_the_worst_document_the_smoke_run_produced():
    """13,122 output tokens is the worst of the 20 smoke documents, and it is
    not a big document: it returned 5,607 characters of JSON, roughly 1,600
    tokens. The rest is adaptive thinking, which claude-sonnet-5 runs whenever
    no thinking parameter is passed, and which is billed and counted against
    this cap without appearing in the response.

    So the cap is bounding how long the model thinks, not how much document
    there is, and snug headroom is the wrong shape for that. Pinned at 2x the
    worst observed rather than at a round number.
    """
    worst_observed = 13_122
    assert extractor.MAX_TOKENS >= 2 * worst_observed


def test_the_live_path_streams():
    """A response permitted to run to 32,000 tokens can outlast the SDK's
    request timeout on a plain create(). The stub refuses create() for exactly
    that reason, so this fails loudly rather than intermittently in a run.
    """
    message = _Message(content=[_Block(GOOD)])
    api = _Api(_Batches(), live=message)
    result = extractor.extract_document(
        api, FIXTURE, (1,), record_id="1493495", file_index=0)
    assert api.messages.calls[0] == "stream"
    assert result.report.form_class == "w2"


def test_a_streamed_truncation_is_caught_by_the_same_guard(tmp_path):
    cache = classify.ResultCache(tmp_path / "c.jsonl",
                                 prompt_hash=extractor.PROMPT_HASH)
    message = _Message(content=[_Block('{"document": {"form_cla')],
                       stop_reason="max_tokens")
    result = extractor.extract_document(
        _Api(_Batches(), live=message), FIXTURE, (1,), record_id="1493495",
        file_index=0, cache=cache)
    assert result.report is None
    assert "truncated" in result.error
    assert cache.get(extractor.cache_key(cache, FIXTURE, (1,))) is None
