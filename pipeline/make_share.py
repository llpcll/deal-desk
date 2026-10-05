#!/usr/bin/env python3
"""Share images (1200x630, for Open Graph and Twitter cards) and the favicon set, in the
cover's style: a brass-framed tombstone on slate (see DESIGN.md).

Used by build_site.py; images are only redrawn when their text changes.

    python pipeline/make_share.py    # redraw the favicons
"""
import hashlib, os, textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "pipeline", "fonts")
GROUND, FACE, INK, INK2, BRASS, BRASS_TEXT = "#11171A", "#1C262B", "#ECE6DA", "#BCC3C4", "#B98935", "#DDB872"
W, H = 1200, 630


def font(italic, size, weight, opsz=72):
    f = ImageFont.truetype(os.path.join(FONTS, "Newsreader-Italic[opsz,wght].ttf" if italic
                                        else "Newsreader[opsz,wght].ttf"), size)
    f.set_variation_by_axes([weight, opsz])  # axis order in the file: weight, optical size
    return f


def _frame(d):
    d.rectangle([40, 40, W - 40, H - 40], fill=FACE, outline=BRASS, width=4)
    d.rectangle([58, 58, W - 58, H - 58], outline=BRASS, width=2)


def _save_if_changed(im, out, key):
    stamp = out + ".key"
    if os.path.exists(out) and os.path.exists(stamp) and open(stamp).read() == key:
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, optimize=True)
    open(stamp, "w").write(key)


def episode_image(num, title, out):
    key = hashlib.sha1(f"v1|{num}|{title}".encode()).hexdigest()
    im = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(im)
    _frame(d)
    d.text((110, 110), "The Deal Desk", font=font(False, 40, 600), fill=INK)
    d.rectangle([110, 168, 190, 171], fill=BRASS)
    d.text((110, 200), f"Episode {num}", font=font(True, 40, 450, 36), fill=BRASS_TEXT)
    f = font(False, 64, 520)
    lines = textwrap.wrap(title, 30)[:3]
    y = 270
    for line in lines:
        d.text((110, y), line, font=f, fill=INK)
        y += 78
    d.text((110, H - 125), "AI-voiced corporate finance, one real deal a day", font=font(False, 28, 420, 24), fill=INK2)
    _save_if_changed(im, out, key)


def home_image(out):
    key = hashlib.sha1(b"home-v1").hexdigest()
    im = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(im)
    _frame(d)
    for text, f, y, fill in (("A daily corporate finance podcast", font(True, 40, 450, 36), 150, BRASS_TEXT),
                             ("The Deal Desk", font(False, 120, 560), 215, INK),
                             ("One concept, one real deal, every day. AI-voiced.", font(False, 34, 420, 24), 400, INK2)):
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=fill)
    d.rectangle([W / 2 - 50, 372, W / 2 + 50, 375], fill=BRASS)
    _save_if_changed(im, out, key)


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="8" fill="#11171A"/>
<rect x="8" y="8" width="48" height="48" fill="#1C262B" stroke="#B98935" stroke-width="3"/>
<text x="32" y="43" text-anchor="middle" font-family="Georgia, serif" font-size="28" font-weight="600" fill="#ECE6DA">DD</text>
</svg>
"""


def favicons(site):
    open(os.path.join(site, "favicon.svg"), "w", encoding="utf-8").write(FAVICON_SVG)
    s = 180
    im = Image.new("RGB", (s, s), GROUND)
    d = ImageDraw.Draw(im)
    d.rectangle([22, 22, s - 22, s - 22], fill=FACE, outline=BRASS, width=6)
    f = font(False, 60, 600)
    w = d.textlength("DD", font=f)
    d.text(((s - w) / 2, 54), "DD", font=f, fill=INK)
    im.save(os.path.join(site, "apple-touch-icon.png"), optimize=True)


if __name__ == "__main__":
    favicons(os.path.join(ROOT, "site"))
    print("favicons written")
