#!/usr/bin/env python3
"""Turn a page of a fetched RRC PDF into something a model can read.

Every page in the closed corpus is exactly one CCITT G4 bilevel image, 3,610
of 3,689 at 300 dpi, and the image maps 1:1 onto the page box (3712 px / 300
dpi = 12.37 in = 890.88 pt). So this module extracts the embedded image rather
than rasterising the page: same pixels, no rendering step, and the geometry
comes from the same tool that measured the corpus.

Poppler supplies pdfimages and pdftotext. It is a system dependency and cannot
come from requirements.txt, so preflight() fails with an install hint instead
of letting a FileNotFoundError surface from three frames down.

The downscale converts to grayscale before resizing. The source is 1-bit; a
nearest-neighbour resample at ~0.48x drops whole strokes off a scanned form,
and the failure looks like a bad classification rather than a bad image.

It has a second job, added 2026-09-03: drawing numbered provenance boxes on a
page so a human can grade whether each one landed on its field. That is a
diagnostic rather than a model input, but it starts from the same page image
and it belongs beside it. It lives here rather than in the two scripts that
need it because it was in both of them, separately, and a defect in one copy
(DEFECTS #33) is a defect in a copy nobody is looking at.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline import pageclass as pc

POPPLER_TOOLS = ("pdfimages", "pdftotext")

INSTALL_HINT = (
    "poppler is required for page rendering and is not pip-installable.\n"
    "  macOS:  brew install poppler\n"
    "  Debian: apt-get install poppler-utils\n"
    "See requirements.txt."
)


class PreflightError(RuntimeError):
    pass


class PageNotSingleImage(RuntimeError):
    """A page holding zero or several images.

    None exist in the closed corpus: all 3,689 pages are 1:1. Raised rather
    than silently falling back to rasterisation, because if that assumption
    breaks the census needs to say so out loud.
    """


# ------------------------------------------------------------------- preflight

def preflight() -> None:
    missing = [t for t in POPPLER_TOOLS if shutil.which(t) is None]
    if missing:
        raise PreflightError(f"missing: {', '.join(missing)}\n{INSTALL_HINT}")


def _run(args: list[str]) -> str:
    try:
        done = subprocess.run(args, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise PreflightError(INSTALL_HINT) from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"{args[0]} failed on {args[-1]}: {exc.stderr.strip()[:200]}") from None
    return done.stdout


# -------------------------------------------------------------------- geometry

def page_dimensions(pdf: Path) -> list[tuple[int, int]]:
    """Pixel size of each page's embedded image, in page order.

    Pages carrying anything other than exactly one image get (0, 0); the
    caller decides whether that is fatal. Reading the whole listing once is
    far cheaper than probing pages individually.
    """
    listing = _run(["pdfimages", "-list", str(pdf)])
    per_page: dict[int, list[tuple[int, int]]] = {}
    highest = 0
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        page, width, height = int(parts[0]), int(parts[3]), int(parts[4])
        per_page.setdefault(page, []).append((width, height))
        highest = max(highest, page)
    return [
        per_page[p][0] if len(per_page.get(p, [])) == 1 else (0, 0)
        for p in range(1, highest + 1)
    ]


def doc_hash(pdf: Path) -> str:
    """Half of the result cache key (CLAUDE.md rule 7)."""
    digest = hashlib.sha256()
    with open(pdf, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------- images

def extract_page_image(pdf: Path, page: int) -> Image.Image:
    """The page's embedded image, as grayscale.

    Converted to L here rather than at resize time so every downstream caller
    gets a resampleable image. See the module docstring.
    """
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "p"
        _run(["pdfimages", "-png", "-f", str(page), "-l", str(page),
              str(pdf), str(prefix)])
        produced = sorted(Path(tmp).glob("p-*.png"))
        if len(produced) != 1:
            raise PageNotSingleImage(
                f"{pdf.name} page {page}: {len(produced)} images, expected 1")
        with Image.open(produced[0]) as img:
            return img.convert("L")


def downscale_image(img: Image.Image,
                    cap: int = pc.DEFAULT_LONG_EDGE) -> Image.Image:
    """Cap the long edge, preserving aspect. Never upscales."""
    target = pc.downscale_target(img.width, img.height, cap=cap)
    if target == (img.width, img.height):
        return img
    if img.mode == "1":
        img = img.convert("L")
    return img.resize(target, Image.LANCZOS)


def render_page_png(pdf: Path, page: int,
                    cap: int = pc.DEFAULT_LONG_EDGE) -> tuple[bytes, tuple[int, int]]:
    """PNG bytes for one page plus the size actually sent, which is what the
    token count is computed from.
    """
    img = downscale_image(extract_page_image(pdf, page), cap=cap)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), (img.width, img.height)


# --------------------------------------------------------------------- overlay

#: Outline colours, cycled by the number printed on the box. Red is first, so
#: a page whose boxes do not collide looks exactly as it did before.
BOX_COLOURS = ((220, 0, 0), (0, 90, 220), (0, 150, 60),
               (200, 110, 0), (140, 0, 190))

#: Label positions, tried in this order. The first is the old behaviour, so
#: an uncontested label does not move and the diff against existing overlays
#: is empty wherever nothing collided.
LABEL_CANDIDATES = ("above_left", "below_left", "above_right", "below_right",
                    "left_outside", "right_outside", "inside_left")


def box_colour(number: int) -> tuple[int, int, int]:
    """Keyed to the number a grader sees, and to nothing else.

    Never to size, source or draw order. On a blinded sheet a text-layer box
    is one word and a template region is a form cell, so a colour keyed to
    size would encode the mechanism and end the blind through the back door.
    """
    return BOX_COLOURS[(number - 1) % len(BOX_COLOURS)]


def overlay_order(boxes):
    """Largest first, ties by number, so a nested small box lands on top.

    Origin: DEFECTS #33. Box 1 was a word inside box 15's form cell, drawn
    first and then painted over, and the grader said he could not see it and
    graded it on an assumption.
    """
    def area(box):
        # Rounded, or the tie-break never fires: two boxes built to be the
        # same size differ in the seventeenth decimal and the number ordering
        # is silently unreachable. Nine places is far finer than a pixel on
        # any page this draws.
        return round((box[2] - box[0]) * (box[3] - box[1]), 9)

    return sorted(boxes, key=lambda item: (-area(item[1]), item[0]))


def _overlap(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def place_label(box, size, canvas, taken, pad: int = 2):
    """Top-left pixel for one number chip. Always inside the canvas.

    Pure integer rectangle arithmetic, no PIL, so the decision this defect
    was about is tier-1 testable while the painting is not. The caller
    measures the glyph and passes the size in.
    """
    width, height = size
    canvas_w, canvas_h = canvas
    left, top, right, bottom = box
    options = {
        "above_left": (left, top - height - pad),
        "below_left": (left, bottom + pad),
        "above_right": (right - width, top - height - pad),
        "below_right": (right - width, bottom + pad),
        "left_outside": (left - width - pad, top),
        "right_outside": (right + pad, top),
        "inside_left": (left + pad, top + pad),
    }
    first = None
    for name in LABEL_CANDIDATES:
        x, y = options[name]
        x = min(max(x, 0), max(0, canvas_w - width))
        y = min(max(y, 0), max(0, canvas_h - height))
        chip = (x, y, x + width, y + height)
        if first is None:
            first = (x, y)
        if not any(_overlap(chip, other) for other in taken):
            return x, y
    return first


def draw_numbered_boxes(image, boxes, *, font=None, stroke=None):
    """Draw numbered rectangles on a page image, in place.

    `boxes` is (number, box in page fractions). Returns the chip rectangle
    actually used for each number, so a caller can assert on placement.
    """
    width, height = image.size
    if font is None:
        try:
            font = ImageFont.load_default(size=max(22, width // 60))
        except TypeError:                      # older Pillow
            font = ImageFont.load_default()
    if stroke is None:
        stroke = max(2, width // 700)
    draw = ImageDraw.Draw(image)
    taken, placed = [], []
    for number, box in overlay_order(boxes):
        pixels = (int(box[0] * width), int(box[1] * height),
                  int(box[2] * width), int(box[3] * height))
        colour = box_colour(number)
        draw.rectangle(pixels, outline=colour, width=stroke)
        label = str(number)
        left, top, right, bottom = font.getbbox(label)
        size = (right - left + 6, bottom - top + 4)
        x, y = place_label(pixels, size, (width, height), taken)
        chip = (x, y, x + size[0], y + size[1])
        draw.rectangle(chip, fill=(255, 255, 255), outline=colour)
        draw.text((x + 3 - left, y + 2 - top), label, fill=colour, font=font)
        taken.append(chip)
        placed.append((number, chip))
    return placed


# ------------------------------------------------------------------------ text

def page_text(pdf: Path, page: int) -> str:
    """The embedded OCR layer for one page.

    247 of 249 files carry one, median 21k characters. It is poor OCR: "FORM
    G-1" comes out as "F(R)lC7lbP G(o)IL". It still yields "RAILROAD COMMISSION
    OF TEXAS", "Back Pressure Test" and "API N^ 039-31674", which is why the
    text arm is worth measuring rather than assuming.
    """
    return _run(["pdftotext", "-f", str(page), "-l", str(page),
                 str(pdf), "-"]).strip()


# ------------------------------------------------------------------------ main

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preflight", action="store_true",
                    help="check for poppler and exit")
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--page", type=int, default=1)
    args = ap.parse_args()

    preflight()
    if args.preflight and not args.pdf:
        print("poppler ok: " + ", ".join(
            f"{t} at {shutil.which(t)}" for t in POPPLER_TOOLS))
        return
    if not args.pdf:
        ap.error("--pdf is required unless --preflight is given alone")

    dims = page_dimensions(args.pdf)
    width, height = dims[args.page - 1]
    png, sent = render_page_png(args.pdf, args.page)
    print(f"page {args.page}: {width}x{height} native -> {sent[0]}x{sent[1]} sent, "
          f"{len(png):,} bytes png, oversize={pc.is_oversize(width, height)}, "
          f"~{pc.estimate_image_tokens(*sent):,} tokens (estimate)")


if __name__ == "__main__":
    main()
