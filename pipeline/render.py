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
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

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
