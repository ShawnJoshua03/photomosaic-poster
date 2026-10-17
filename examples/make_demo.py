"""Build the README demo from synthetic images only (no real photos in the repo).

    python examples/make_demo.py

Writes examples/demo_input/ (a target picture and 600 generated "photos") and the
images in docs/. Takes about a minute.
"""
import colorsys
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mosaic_poster import PosterOptions, make_poster  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "examples" / "demo_input"
DOCS = ROOT / "docs"


def hsv(h, s, v):
    return tuple(int(255 * c) for c in colorsys.hsv_to_rgb(h % 1, s, v))


def fake_photo(rng, size=(400, 300)):
    """A little postcard scene: sky, sun, hills and a few 'people'."""
    w, h = size
    hue = rng.random()
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    top, bottom = hsv(hue, rng.uniform(0.3, 0.9), rng.uniform(0.3, 1)), \
        hsv(hue + rng.uniform(-0.15, 0.15), rng.uniform(0.2, 0.8), rng.uniform(0.4, 1))
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    sx, sy, sr = rng.uniform(0, w), rng.uniform(0, h * 0.5), rng.uniform(15, 45)
    d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=hsv(rng.uniform(0.05, 0.15), 0.6, 1))
    ground = hsv(hue + 0.3 + rng.uniform(-0.1, 0.1), rng.uniform(0.3, 0.8), rng.uniform(0.15, 0.8))
    pts = [(0, h)] + [(x, h * 0.6 + 25 * math.sin(x / rng.uniform(30, 80) + rng.uniform(0, 6)))
                      for x in range(0, w + 20, 20)] + [(w, h)]
    d.polygon(pts, fill=ground)
    for _ in range(int(rng.integers(1, 5))):  # stick-figure "friends"
        x, y = rng.uniform(40, w - 40), h * rng.uniform(0.62, 0.8)
        c = hsv(rng.random(), rng.uniform(0.4, 1), rng.uniform(0.2, 1))
        d.ellipse((x - 9, y - 50, x + 9, y - 32), fill=(240, 200, 170))
        d.rectangle((x - 11, y - 32, x + 11, y), fill=c)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def target_picture(size=(900, 1200)):
    """A big, simple picture that reads well as a mosaic: a heart at sunset."""
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        c = (int(255 - 60 * t), int(150 - 90 * t), int(90 + 80 * t))
        d.line([(0, y), (w, y)], fill=c)
    d.ellipse((w * 0.35, h * 0.08, w * 0.65, h * 0.31), fill=(255, 225, 140))
    heart = [(w / 2 + 16 * math.sin(t) ** 3 * w / 40,
              h * 0.55 - (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t)
                          - math.cos(4 * t)) * w / 40)
             for t in np.linspace(0, 2 * math.pi, 200)]
    d.polygon(heart, fill=(200, 20, 60))
    d.polygon([(0, h), (0, h * 0.8), (w * 0.3, h * 0.72), (w * 0.6, h * 0.85),
               (w, h * 0.75), (w, h)], fill=(40, 25, 60))
    return im


def main():
    rng = np.random.default_rng(23)
    (INPUT / "photos").mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    for i in range(600):
        fake_photo(rng).save(INPUT / "photos" / f"photo_{i:03d}.jpg", quality=88)
    target_picture().save(INPUT / "target.jpg", quality=92)

    out = INPUT / "demo_poster.png"
    make_poster(PosterOptions(target=str(INPUT / "target.jpg"),
                              tile_dirs=[str(INPUT / "photos")], output=str(out),
                              width_in=18, height_in=24, dpi=200, cols=40,
                              cache_dir=str(INPUT / ".cache")))
    poster = Image.open(out)
    poster.resize((750, 1000), Image.LANCZOS).save(DOCS / "demo.jpg", quality=88)
    target_picture().resize((300, 400), Image.LANCZOS).save(DOCS / "demo-target.jpg", quality=88)
    cx, cy = poster.width // 2, int(poster.height * 0.45)
    poster.crop((cx - 450, cy - 300, cx + 450, cy + 300)).save(DOCS / "demo-closeup.jpg",
                                                                quality=88)
    print("wrote docs/demo.jpg, docs/demo-target.jpg, docs/demo-closeup.jpg")


if __name__ == "__main__":
    main()
