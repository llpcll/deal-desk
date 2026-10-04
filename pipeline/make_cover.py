#!/usr/bin/env python3
"""Draw the podcast cover art (3000x3000 JPEG, as Spotify and Apple require).

    python pipeline/make_cover.py      # -> site/cover.jpg

The cover is the show's tombstone: a brass-framed deal toy on slate (see DESIGN.md).
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "pipeline", "fonts")
S = 3000

GROUND, FACE, INK, INK2, MUTED, BRASS, BRASS_TEXT = (
    "#11171A", "#1C262B", "#ECE6DA", "#BCC3C4", "#97A3A8", "#B98935", "#DDB872")


def font(italic, size, weight, opsz=72):
    f = ImageFont.truetype(os.path.join(FONTS, "Newsreader-Italic[opsz,wght].ttf" if italic
                                        else "Newsreader[opsz,wght].ttf"), size)
    f.set_variation_by_axes([weight, opsz])  # axis order in the file: weight, optical size
    return f


def centred(d, y, text, f, fill):
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, y), text, font=f, fill=fill)


def main():
    im = Image.new("RGB", (S, S), GROUND)
    d = ImageDraw.Draw(im)

    # The tombstone: outer brass frame, face, inner brass rule.
    x0, y0, x1, y1 = 420, 360, S - 420, S - 360
    d.rectangle([x0, y0, x1, y1], fill=FACE, outline=BRASS, width=10)
    d.rectangle([x0 + 50, y0 + 50, x1 - 50, y1 - 50], outline=BRASS, width=6)

    centred(d, 700, "A daily corporate finance podcast", font(True, 118, 450, 36), BRASS_TEXT)
    centred(d, 960, "The Deal", font(False, 430, 560), INK)
    centred(d, 1400, "Desk", font(False, 430, 560), INK)
    d.rectangle([S / 2 - 150, 1950, S / 2 + 150, 1960], fill=BRASS)
    centred(d, 2060, "One concept, one real deal,", font(False, 120, 450, 24), INK2)
    centred(d, 2210, "every day", font(False, 120, 450, 24), INK2)
    centred(d, 2440, "AI-voiced", font(True, 96, 400, 24), MUTED)

    out = os.path.join(ROOT, "site", "cover.jpg")
    im.save(out, "JPEG", quality=88, optimize=True)
    print(f"  {os.path.relpath(out, ROOT)}: {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
