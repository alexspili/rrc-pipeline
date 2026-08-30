"""Tier 1: the downscale must not eat ink. Pure, in-memory, no files.

Corpus pages are 1-bit CCITT at 300 dpi. Reducing 2537x3279 to a 1568 long
edge is a 0.48x resample, and on a bilevel source a nearest-neighbour filter
does not average: it picks one source pixel per output pixel, so a hairline
either survives whole or vanishes. The page still looks like a page, so the
failure surfaces as a bad classification with no error raised.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from pipeline import render


def _hairline_page(width=2000, height=2600, period=20) -> Image.Image:
    img = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(img)
    for y in range(period, height, period):
        draw.line([(0, y), (width, y)], fill=0, width=1)
    return img


def _ink(img: Image.Image) -> float:
    """Mean darkness in [0, 1]."""
    grey = img.convert("L")
    values = grey.get_flattened_data()
    return 1.0 - (sum(values) / (255.0 * len(values)))


def _midtone_fraction(img: Image.Image) -> float:
    """Share of pixels that are neither near-white nor near-black.

    This is the signature of an averaging filter. A bilevel source contains
    only 0 and 255, so nearest-neighbour output contains only 0 and 255 too:
    a stroke it lands on is kept at full strength and a stroke it misses is
    gone entirely. An area filter turns a partially-covered pixel into grey,
    which is how a sub-pixel stroke survives a 0.4x reduction at all.
    """
    grey = img.convert("L")
    values = grey.get_flattened_data()
    mid = sum(1 for value in values if 24 < value < 231)
    return mid / len(values)


def test_downscale_averages_rather_than_samples():
    source = _hairline_page()
    ours = render.downscale_image(source, cap=1000)
    naive = source.resize((ours.width, ours.height), Image.NEAREST)

    assert _midtone_fraction(naive) < 0.01, (
        "the nearest-neighbour control produced midtones, so it is no longer "
        "the thing this test contrasts against")
    # A 20px period reduces to 7.7 output rows, and each hairline spreads its
    # ink across one or two of them: 13-26% of rows should carry partial ink.
    # The floor is set at the bottom of that range, still fifteen times the
    # nearest-neighbour control.
    assert _midtone_fraction(ours) > 0.15, (
        f"only {_midtone_fraction(ours):.1%} of the downscaled page carries "
        "partial ink; strokes are being kept or dropped whole, which means "
        "the resample is not averaging")


def test_downscale_preserves_total_ink():
    source = _hairline_page()
    ours = render.downscale_image(source, cap=1000)
    assert abs(_ink(ours) - _ink(source)) < 0.02, (
        f"downscale changed ink from {_ink(source):.3f} to {_ink(ours):.3f}")


def test_strokes_below_the_sampling_limit_survive_as_grey():
    """A 4px period reduces to 1.5px, under Nyquist. Averaging turns the block
    grey and keeps the mark; sampling turns it into a moire of solid rows.
    """
    source = _hairline_page(period=4)
    ours = render.downscale_image(source, cap=1000)
    naive = source.resize((ours.width, ours.height), Image.NEAREST)
    assert _midtone_fraction(ours) > 0.80
    assert _midtone_fraction(naive) < 0.01


def test_downscale_returns_a_resampleable_mode():
    """PIL cannot area-filter mode '1'. If the conversion to L is dropped the
    resize silently degrades rather than failing.
    """
    assert render.downscale_image(_hairline_page(), cap=1000).mode == "L"


def test_downscale_leaves_small_pages_untouched():
    small = Image.new("1", (800, 1000), 1)
    assert render.downscale_image(small, cap=1568) is small
