"""Tier 2 for the overlay drawing: assertions on pixels, not on intent.

DEFECTS #33 was a box that was drawn and could not be seen. The only honest
test of that is to draw one and look at the pixels. Synthetic images only, so
this runs without the git-ignored corpus.
"""

from __future__ import annotations

from PIL import Image

from pipeline import render


def canvas(colour=(255, 255, 255), size=(800, 600)):
    return Image.new("RGB", size, colour)


def test_a_nested_box_is_still_visible_after_the_big_one_is_drawn():
    """The defect itself. Box 2 sits entirely inside box 1."""
    image = canvas()
    render.draw_numbered_boxes(
        image, [(1, (0.10, 0.10, 0.90, 0.90)),
                (2, (0.40, 0.40, 0.60, 0.60))])
    inner = render.box_colour(2)
    pixels = image.load()
    edge_y = int(0.40 * 600)
    found = any(pixels[x, y] == inner
                for x in range(int(0.40 * 800), int(0.60 * 800))
                for y in range(edge_y - 3, edge_y + 4))
    assert found, "the nested box's outline was painted over"


def test_two_labels_never_share_a_pixel():
    image = canvas()
    placed = render.draw_numbered_boxes(
        image, [(n, (0.30 + 0.001 * n, 0.30, 0.50, 0.50))
                for n in range(1, 7)])
    chips = [chip for _, chip in placed]
    for index, first in enumerate(chips):
        for second in chips[index + 1:]:
            assert not render._overlap(first, second), (first, second)


def test_the_label_chip_is_legible_over_ink():
    image = canvas((0, 0, 0))
    placed = render.draw_numbered_boxes(image, [(1, (0.2, 0.2, 0.8, 0.8))])
    chip = placed[0][1]
    pixels = image.load()
    whites = sum(1 for x in range(chip[0], chip[2])
                 for y in range(chip[1], chip[3])
                 if pixels[x, y] == (255, 255, 255))
    assert whites > 0, "the number would be invisible on a dark scan"


def test_boxes_at_the_image_edges_do_not_raise():
    image = canvas()
    render.draw_numbered_boxes(
        image, [(1, (0.0, 0.0, 1.0, 1.0)), (2, (0.0, 0.0, 0.02, 0.02)),
                (3, (0.98, 0.98, 1.0, 1.0))])


def test_every_box_gets_exactly_one_label():
    image = canvas()
    placed = render.draw_numbered_boxes(
        image, [(n, (0.1 * n, 0.1, 0.1 * n + 0.05, 0.2))
                for n in range(1, 6)])
    assert sorted(n for n, _ in placed) == [1, 2, 3, 4, 5]
