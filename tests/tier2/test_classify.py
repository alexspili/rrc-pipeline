"""Tier 2: request construction, caching and cost arithmetic.

No network. The model call is stubbed; what is checked here is everything
around it, which is where the money and the silent errors are. The one thing
that cannot be checked offline, whether output_config.format binds on this
model, is exactly what scripts/probe_haiku.py exists to answer.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from pipeline import classify
from pipeline import pageclass as pc

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pages.pdf"

GOOD = ('{"form_class":"g1","part":"face","orientation":"up",'
        '"confidence":"high","alt_class":null,"form_number_legible":true}')


# ------------------------------------------------------------------ stub client

@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Response:
    content: list
    usage: _Usage


class StubMessages:
    def __init__(self, body: str):
        self.body = body
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.last = kwargs
        return _Response([_Block(self.body)], _Usage(2540, 32))


class StubClient:
    def __init__(self, body: str = GOOD):
        self.messages = StubMessages(body)


# --------------------------------------------------------------------- prompt

def test_prompt_names_every_class_in_the_vocabulary():
    """A class the prompt never mentions cannot be predicted, but the parser
    would still accept it. The two vocabularies must not drift apart.
    """
    for page_class in pc.PageClass:
        assert page_class.value in classify.SYSTEM, page_class.value
    for part in pc.Part:
        assert part.value in classify.SYSTEM, part.value
    for orientation in pc.Orientation:
        assert orientation.value in classify.SYSTEM, orientation.value


def test_prompt_hash_tracks_the_prompt():
    assert classify.PROMPT_HASH == pc.prompt_hash(classify.SYSTEM)


def test_prompt_is_too_short_for_anthropic_prompt_caching():
    """HANDOFF records that our (doc_hash, prompt_hash) result cache is not
    Anthropic prompt caching. The minimum cacheable prefix is thousands of
    tokens; this prompt is nowhere near it, so no prompt-cache discount may be
    claimed for it.
    """
    assert len(classify.SYSTEM) < 8000


# ------------------------------------------------------------- request content

def test_image_arm_sends_a_base64_png_capped_at_the_arm_size():
    content, sent = classify.build_content("vision_1000", FIXTURE, 1)
    assert max(sent) == 1000
    image = next(b for b in content if b["type"] == "image")
    assert image["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(image["source"]["data"])[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_two_vision_arms_differ_only_in_resolution():
    _, small = classify.build_content("vision_1000", FIXTURE, 1)
    _, large = classify.build_content("vision_1568", FIXTURE, 1)
    assert max(small) == 1000 and max(large) == 1568
    assert small[0] / small[1] == pytest.approx(large[0] / large[1], abs=0.01)


def test_text_arm_sends_no_image_and_survives_a_page_with_no_text_layer():
    """Two of 249 files have no OCR layer. The arm must still produce a
    request for those pages, or it cannot be scored on them.
    """
    content, sent = classify.build_content("text", FIXTURE, 1)
    assert sent is None
    assert all(block["type"] == "text" for block in content)
    assert "no embedded text layer" in content[0]["text"]


# ---------------------------------------------------------------------- cache

def test_cache_returns_the_stored_label_without_calling_the_model(tmp_path):
    """CLAUDE.md rule 7. A second run over an unchanged corpus should cost
    nothing, which only holds if the cache is consulted before the request is
    built.
    """
    cache = classify.ResultCache(tmp_path / "cache.jsonl")
    api = StubClient()

    first = classify.classify_page(api, "vision_1000", FIXTURE, 1,
                                   record_id="1501720", file_index=0,
                                   cache=cache, doc_hash="abc123")
    second = classify.classify_page(api, "vision_1000", FIXTURE, 1,
                                    record_id="1501720", file_index=0,
                                    cache=cache, doc_hash="abc123")

    assert api.messages.calls == 1
    assert first.cached is False and second.cached is True
    assert first.label == second.label


def test_cache_key_separates_arms_and_pages_and_prompts(tmp_path):
    key = classify.ResultCache(tmp_path / "c.jsonl").key
    assert key("abc", 1, "vision_1000") != key("abc", 2, "vision_1000")
    assert key("abc", 1, "vision_1000") != key("abc", 1, "vision_1568")
    assert key("abc", 1, "vision_1000") != key("xyz", 1, "vision_1000")
    assert classify.PROMPT_HASH in key("abc", 1, "vision_1000")


def test_a_second_prompt_cannot_read_the_first_prompts_cache(tmp_path):
    """Extraction reuses this cache with its own prompt. CLAUDE.md rule 7 keys
    on (document, prompt); sharing a file must not mean sharing an answer.
    """
    classifier = classify.ResultCache(tmp_path / "c.jsonl")
    extractor = classify.ResultCache(tmp_path / "c.jsonl",
                                     prompt_hash="0123456789abcdef")
    assert classifier.key("abc", 1, "vision_1000") != \
        extractor.key("abc", 1, "vision_1000")


def test_cache_survives_a_reopen(tmp_path):
    path = tmp_path / "cache.jsonl"
    api = StubClient()
    classify.classify_page(api, "text", FIXTURE, 1, record_id="1", file_index=0,
                           cache=classify.ResultCache(path), doc_hash="abc")
    again = classify.classify_page(api, "text", FIXTURE, 1, record_id="1",
                                   file_index=0,
                                   cache=classify.ResultCache(path),
                                   doc_hash="abc")
    assert again.cached is True
    assert api.messages.calls == 1


# ------------------------------------------------------------- result handling

def test_a_malformed_response_is_recorded_not_raised():
    """One unparseable page must not abort a 3,689-page run. It comes back as
    an Attempt carrying the error, and the census reports how many.
    """
    attempt = classify.classify_page(
        StubClient("I think this is a G-1?"), "vision_1000", FIXTURE, 1,
        record_id="1501720", file_index=0)
    assert attempt.label is None
    assert "no JSON object" in attempt.error


def test_the_oversize_flag_comes_from_geometry_not_from_the_model():
    """Origin: DEFECTS #1. The guard is arithmetic on the page dimensions. A
    model that failed to notice a fold-out must not be able to clear the flag.
    """
    attempt = classify.classify_page(
        StubClient(), "vision_1000", FIXTURE, 3,     # page 3 is AR 3.33
        record_id="1495350", file_index=0)
    assert attempt.label.oversize is True
    assert attempt.label.extraction_eligible is False


def test_cost_is_computed_from_list_prices_and_halved_by_batch():
    attempt = classify.Attempt(label=None, arm="vision_1568", sent_px=(1215, 1568),
                               input_tokens=1_000_000, output_tokens=1_000_000,
                               cached=False)
    assert attempt.cost_usd() == pytest.approx(6.00)
    assert attempt.cost_usd(batched=True) == pytest.approx(3.00)


def test_client_refuses_to_run_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        classify.client()
    assert ".env" in str(exc.value)


def test_a_cached_malformed_response_behaves_like_a_fresh_one(tmp_path):
    """Origin: DEFECTS #14. The live path catches a parse failure and records
    it on the Attempt; the cache-hit path called the same parser with no
    guard. So a run that tolerated 9 bad pages on the way out died on the
    first one on the way back, and re-reporting from cache was impossible
    without re-spending.

    A cached result must be indistinguishable from a fresh one.
    """
    cache = classify.ResultCache(tmp_path / "cache.jsonl")
    api = StubClient("I think this is a G-1?")

    fresh = classify.classify_page(api, "text", FIXTURE, 1, record_id="1",
                                   file_index=0, cache=cache, doc_hash="abc")
    cached = classify.classify_page(api, "text", FIXTURE, 1, record_id="1",
                                    file_index=0, cache=cache, doc_hash="abc")

    assert api.messages.calls == 1
    assert cached.cached is True
    assert fresh.label is None and cached.label is None
    assert fresh.error == cached.error
    assert cached.input_tokens == fresh.input_tokens


def test_a_cached_out_of_vocabulary_class_does_not_raise(tmp_path):
    """The commonest real failure: the model answers with a `part` value in
    the form_class field.
    """
    cache = classify.ResultCache(tmp_path / "cache.jsonl")
    body = ('{"form_class":"back_instructions","part":"face",'
            '"orientation":"up","confidence":"high","alt_class":null,'
            '"form_number_legible":true}')
    api = StubClient(body)
    classify.classify_page(api, "text", FIXTURE, 1, record_id="1",
                           file_index=0, cache=cache, doc_hash="abc")
    again = classify.classify_page(api, "text", FIXTURE, 1, record_id="1",
                                   file_index=0, cache=cache, doc_hash="abc")
    assert again.label is None
    assert "back_instructions" in again.error


def test_a_cached_result_is_reconciled_like_a_fresh_one(tmp_path, monkeypatch):
    """DEFECTS #14's bug class, applied to the correction added for #19. A
    deterministic fix that runs on fresh results and not on cached ones makes
    the cache change the answer, which is the one thing a cache must never do.
    """
    from pipeline import classify, pageclass as pc

    body = ('{"form_class":"w2","part":"face","orientation":"up",'
            '"confidence":"high","alt_class":null,"form_number_legible":true}')
    monkeypatch.setattr(classify.render, "page_text",
                        lambda pdf, page: "FORM W-15 CEMENTING REPORT")
    monkeypatch.setattr(classify.render, "page_dimensions",
                        lambda pdf: [(1000, 1300)])
    monkeypatch.setattr(classify, "build_content",
                        lambda arm, pdf, page: ([], (775, 1000)))

    class FakeAPI:
        class messages:
            @staticmethod
            def create(**kw):
                class R:
                    content = [type("B", (), {"type": "text", "text": body})()]
                    usage = type("U", (), {"input_tokens": 10,
                                           "output_tokens": 5})()
                return R()

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    cache = classify.ResultCache(tmp_path / "cache.jsonl")
    fresh = classify.classify_page(FakeAPI(), "vision_1000", pdf, 1,
                                   record_id="1", file_index=0, cache=cache)
    replayed = classify.classify_page(FakeAPI(), "vision_1000", pdf, 1,
                                      record_id="1", file_index=0, cache=cache)

    assert fresh.label.form_class is pc.PageClass.W15
    assert replayed.cached and not fresh.cached
    assert replayed.label.form_class == fresh.label.form_class
    assert replayed.label.resolution == fresh.label.resolution == pc.RESOLVED_HEADER
