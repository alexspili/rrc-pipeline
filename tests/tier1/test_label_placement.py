"""Tier 1 for the overlay's two decisions: draw order and label placement.

Origin: DEFECTS #33. A box nested inside another was invisible, and the
grader graded it on a stated assumption. The painting is not pure and is not
tested here; the two decisions that caused the defect are, because the seam
between them is the font, which the caller measures and passes in as plain
integers.
"""

import pytest

from pipeline import render


def test_an_uncontested_label_does_not_move():
    """The first candidate is the old behaviour, so existing overlays are
    unchanged wherever nothing collided."""
    at = render.place_label((100, 100, 200, 140), (20, 16), (800, 600), [])
    assert at == (100, 100 - 16 - 2)


def test_a_colliding_label_takes_the_next_candidate():
    box = (100, 100, 200, 140)
    first = render.place_label(box, (20, 16), (800, 600), [])
    taken = [(first[0], first[1], first[0] + 20, first[1] + 16)]
    second = render.place_label(box, (20, 16), (800, 600), taken)
    assert second != first
    assert not render._overlap(
        (second[0], second[1], second[0] + 20, second[1] + 16), taken[0])


@pytest.mark.parametrize("box", [(0, 0, 60, 40), (760, 0, 800, 40),
                                 (0, 560, 60, 600), (760, 560, 800, 600)])
def test_a_label_at_any_corner_stays_inside_the_image(box):
    x, y = render.place_label(box, (20, 16), (800, 600), [])
    assert 0 <= x <= 800 - 20 and 0 <= y <= 600 - 16


def test_a_label_is_still_placed_when_every_candidate_collides():
    taken = [(0, 0, 800, 600)]
    at = render.place_label((100, 100, 200, 140), (20, 16), (800, 600), taken)
    assert at is not None
    assert 0 <= at[0] <= 800 - 20 and 0 <= at[1] <= 600 - 16


def test_the_candidate_order_is_the_declared_one():
    """Makes the order a contract rather than an accident of the dict."""
    box = (300, 300, 400, 340)
    canvas = (800, 600)
    taken = []
    seen = []
    for _ in render.LABEL_CANDIDATES:
        at = render.place_label(box, (20, 16), canvas, taken)
        seen.append(at)
        taken.append((at[0], at[1], at[0] + 20, at[1] + 16))
    assert len(set(seen)) == len(render.LABEL_CANDIDATES)


def test_boxes_are_drawn_largest_first():
    small = (2, (0.20, 0.20, 0.25, 0.22))
    big = (1, (0.10, 0.10, 0.90, 0.90))
    assert render.overlay_order([small, big]) == [big, small]


def test_ties_in_area_are_broken_by_the_number():
    a = (5, (0.1, 0.1, 0.2, 0.2))
    b = (3, (0.5, 0.5, 0.6, 0.6))
    assert [n for n, _ in render.overlay_order([a, b])] == [3, 5]


def test_the_colour_cycles_by_the_number_the_grader_sees():
    assert render.box_colour(1) != render.box_colour(2)
    assert render.box_colour(1) == render.box_colour(
        1 + len(render.BOX_COLOURS))


def test_the_colour_does_not_depend_on_size_source_or_draw_order():
    """The blind test. On the stage-four sheet a text-layer box is one word
    and a template region is a form cell, so a colour keyed to size would
    encode the mechanism and end the blind through the back door."""
    tiny = [(n, (0.1, 0.1, 0.1 + 0.001 * n, 0.11)) for n in range(1, 8)]
    huge = [(n, (0.0, 0.0, 0.9 - 0.01 * n, 0.9)) for n in range(1, 8)]
    for arrangement in (tiny, huge, list(reversed(tiny))):
        drawn = {n: render.box_colour(n) for n, _ in
                 render.overlay_order(arrangement)}
        assert drawn == {n: render.box_colour(n) for n in range(1, 8)}


def test_the_palette_is_distinct_and_never_near_white():
    """The chip behind a number is white, so a near-white outline vanishes."""
    assert len(set(render.BOX_COLOURS)) == len(render.BOX_COLOURS)
    for colour in render.BOX_COLOURS:
        assert sum(colour) < 600
