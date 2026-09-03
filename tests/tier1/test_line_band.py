"""Tier 1 for pipeline.textlayer's display band: pure, no PDFs.

Origin: the 2026-09-03 grading. The box shown for a text-layer match was the
single word that matched, so a reviewer looking up an operator name saw a box
around `SKELLY` and not around `SKELLY OIL COMPANY`. Five of fifteen graded
boxes carried that complaint, and a one-word box also gave the grader nothing
with which to notice a match that had landed in the wrong field (DEFECTS #32).

The load-bearing tests here are the ones about where the run STOPS. A band
that runs on into the next form field is worse than the single word it
replaced, because it looks like it knows something.
"""

import pytest

from pipeline import textlayer as tl


def word(x0, y0, x1, text):
    """One word box, 0.007 tall, which is this corpus's median."""
    return (x0, y0, x1, y0 + 0.007, text)


def contents(words, band):
    return [w[4] for w in words
            if band[0] <= (w[0] + w[2]) / 2 <= band[2]
            and band[1] <= (w[1] + w[3]) / 2 <= band[3] and tl.norm(w[4])]


#: A dense page, so gap_cutoff has its 20 samples and uses the measured
#: median rather than the fallback. Gaps of 0.004, as measured on the paper.
def dense(extra=()):
    filler = []
    for row in range(7):
        y = 0.60 + row * 0.02
        x = 0.05
        for index in range(4):
            filler.append(word(x, y, x + 0.03, f"w{row}{index}"))
            x += 0.034
    return list(extra) + filler


def test_the_run_grows_a_partial_match_to_the_whole_printed_run():
    line = [word(0.10, 0.20, 0.16, "SKELLY"),
            word(0.169, 0.20, 0.20, "OIL"),
            word(0.209, 0.20, 0.26, "COMPANY")]
    band = tl.line_run(dense(line), line[0][:4])
    assert contents(dense(line), band) == ["SKELLY", "OIL", "COMPANY"]


def test_a_gap_wide_enough_to_be_another_field_stops_the_run():
    line = [word(0.10, 0.20, 0.16, "SKELLY"),
            word(0.169, 0.20, 0.20, "OIL"),
            word(0.60, 0.20, 0.66, "County")]
    words = dense(line)
    band = tl.line_run(words, line[0][:4])
    assert contents(words, band) == ["SKELLY", "OIL"]
    # and from the other side, so the rule is symmetric
    band = tl.line_run(words, line[2][:4])
    assert contents(words, band) == ["County"]


def test_the_run_never_leaves_the_anchors_own_line():
    words = dense([word(0.10, 0.200, 0.16, "label"),
                   word(0.10, 0.212, 0.16, "value"),
                   word(0.169, 0.212, 0.22, "more")])
    band = tl.line_run(words, (0.10, 0.212, 0.16, 0.219))
    assert contents(words, band) == ["value", "more"]


def test_the_run_absorbs_a_skewed_baseline():
    """The typed line on the graded page drifts 0.0030 in y end to end,
    while the printed line above it sits 0.012 away. Chaining word to word
    holds the drift; comparing everything to the anchor would truncate it."""
    line = [word(0.10, 0.2000, 0.16, "one"),
            word(0.169, 0.2015, 0.22, "two"),
            word(0.229, 0.2030, 0.28, "three")]
    words = dense(line)
    band = tl.line_run(words, line[0][:4])
    assert contents(words, band) == ["one", "two", "three"]


def test_leader_dots_are_a_gap_and_not_a_bridge():
    """The depth fields are separated by rows of dots that pdftotext emits as
    their own tokens 0.0034 apart. Walking through them joins two different
    fields into one band, which is the failure the cutoff exists to stop."""
    line = [word(0.10, 0.20, 0.14, "8030")]
    x = 0.145
    for _ in range(12):
        line.append(word(x, 0.20, x + 0.003, "."))
        x += 0.0064
    line.append(word(x, 0.20, x + 0.04, "8465"))
    words = dense(line)
    band = tl.line_run(words, line[0][:4])
    assert contents(words, band) == ["8030"]
    assert band[2] < 0.145 + 0.05


def test_the_cutoff_comes_from_the_pages_own_gaps_not_a_constant():
    """The same layout at half scale selects the same words."""
    def build(scale):
        line = [word(0.10 * scale, 0.20 * scale, 0.16 * scale, "a"),
                word(0.169 * scale, 0.20 * scale, 0.20 * scale, "b"),
                word(0.60 * scale, 0.20 * scale, 0.66 * scale, "far")]
        filler = []
        for row in range(7):
            y = 0.60 * scale + row * 0.02 * scale
            x = 0.05 * scale
            for index in range(4):
                filler.append((x, y, x + 0.03 * scale, y + 0.007 * scale,
                               f"w{row}{index}"))
                x += 0.034 * scale
        return line + filler
    for scale in (1.0, 0.5):
        words = build(scale)
        band = tl.line_run(words, words[0][:4])
        assert contents(words, band) == ["a", "b"], scale


def test_a_page_with_too_few_gaps_falls_back_to_the_word_height():
    words = [word(0.10, 0.20, 0.16, "alpha"), word(0.169, 0.20, 0.20, "beta")]
    height = tl.line_height(words)
    assert tl.gap_cutoff(words, height) == pytest.approx(
        tl.GAP_LINES * height)
    band = tl.line_run(words, words[0][:4])
    assert contents(words, band) == ["alpha", "beta"]


def test_an_empty_page_returns_the_box_unchanged():
    box = (0.10, 0.20, 0.16, 0.207)
    assert tl.line_run([], box) == box


def test_a_run_of_one_word_returns_that_word():
    words = dense([word(0.10, 0.20, 0.16, "alone")])
    band = tl.line_run(words, (0.10, 0.20, 0.16, 0.207))
    assert contents(words, band) == ["alone"]


@pytest.mark.parametrize("anchor", [(0.10, 0.20, 0.16, 0.207),
                                    (0.169, 0.20, 0.20, 0.207)])
def test_the_band_always_contains_its_own_anchor(anchor):
    """A display region smaller than the evidence it shows is the silent
    failure this whole change exists to remove."""
    words = dense([word(0.10, 0.20, 0.16, "SKELLY"),
                   word(0.169, 0.20, 0.20, "OIL")])
    band = tl.line_run(words, anchor)
    assert band[0] <= anchor[0] and band[1] <= anchor[1]
    assert band[2] >= anchor[2] and band[3] >= anchor[3]


def test_the_band_stays_inside_the_page():
    words = dense([word(0.90, 0.20, 0.999, "edge")])
    band = tl.line_run(words, (0.90, 0.20, 0.999, 0.207))
    assert 0.0 <= band[0] < band[2] <= 1.0
    assert 0.0 <= band[1] < band[3] <= 1.0


def test_line_height_is_the_median_and_defaults_on_a_page_with_no_height():
    words = [word(0.1, 0.2, 0.2, "a"), word(0.1, 0.3, 0.2, "b"),
             (0.1, 0.4, 0.2, 0.4 + 0.021, "tall")]
    assert tl.line_height(words) == pytest.approx(0.007)
    assert tl.line_height([(0.1, 0.2, 0.2, 0.2, "flat")]) == 0.012
    assert tl.line_height([]) == 0.012


def test_gap_cutoff_ignores_overlaps_and_pairs_on_different_lines():
    words = [word(0.10, 0.20, 0.20, "a"), word(0.15, 0.20, 0.25, "overlap"),
             word(0.10, 0.40, 0.20, "other")]
    assert tl.word_gaps(words, tl.line_height(words)) == []


def test_punctuation_only_tokens_are_not_part_of_a_run():
    words = dense([word(0.10, 0.20, 0.16, "value"),
                   word(0.163, 0.20, 0.17, "...")])
    assert tl._printed(words)[0][4] == "value"
    assert all(w[4] != "..." for w in tl._printed(words))
