#!/usr/bin/env python3
"""Build tests/fixtures/pages.pdf: a synthetic stand-in for a scanned RRC file.

Deliberately synthetic. A real page would have to be redacted before it could
be committed (CLAUDE.md rule 3: fetched PDFs carry surface owners' names,
addresses and phone numbers), and a redacted scan is a worse fixture than a
drawn one because the redaction changes the pixels the test is about.

Three pages, matching the shapes measured in the corpus:
  1. 1200x1600 portrait, the modal page shape
  2. 1600x1200 landscape, 17.5% of corpus images are landscape
  3. 3000x900  aspect ratio 3.33, an oversize fold-out (DEFECTS #1)

Mode "1" throughout, so Pillow writes CCITT G4 and the fixture matches the
encoding every real page uses.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages.pdf"
SIZES = [(1200, 1600), (1600, 1200), (3000, 900)]


def page(width: int, height: int) -> Image.Image:
    img = Image.new("1", (width, height), 1)          # 1 = white
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline=0, width=3)
    # Hairlines: the thing a nearest-neighbour downscale destroys.
    for y in range(80, height - 40, 20):
        draw.line([(60, y), (width - 60, y)], fill=0, width=1)
    for x in range(60, width - 40, 120):
        draw.line([(x, 60), (x, height - 60)], fill=0, width=1)
    return img


def main() -> None:
    pages = [page(w, h) for w, h in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=300)
    print(f"{OUT}: {OUT.stat().st_size:,} bytes, {len(pages)} pages")


if __name__ == "__main__":
    main()
