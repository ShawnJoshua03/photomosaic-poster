import shutil

import numpy as np
import pytest
from PIL import Image, ImageDraw


def _photo(rng, size=(160, 120)):
    """A distinct, photo-like test image: a random color field with some texture."""
    small = rng.integers(0, 256, (6, 8, 3)).astype(np.uint8)
    im = Image.fromarray(small).resize(size, Image.BICUBIC)
    d = ImageDraw.Draw(im)
    for _ in range(3):
        x, y = rng.integers(0, size[0]), rng.integers(0, size[1])
        r = int(rng.integers(8, 30))
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(v) for v in rng.integers(0, 256, 3)))
    return im


@pytest.fixture(scope="session")
def photos(tmp_path_factory):
    """A folder of 80 synthetic photos plus the awkward cases real folders contain."""
    root = tmp_path_factory.mktemp("photos")
    rng = np.random.default_rng(7)
    for i in range(80):
        _photo(rng).save(root / f"img_{i:03d}.jpg", quality=90)
    sub = root / "nested"
    sub.mkdir()
    _photo(rng).save(sub / "deep.png")
    shutil.copy(root / "img_000.jpg", root / "img_000_copy.jpg")  # exact duplicate
    (root / "broken.jpg").write_bytes(b"not really a jpeg")       # corrupt file
    (root / "notes.txt").write_text("not a photo")                # ignored
    return root


@pytest.fixture(scope="session")
def target(tmp_path_factory):
    path = tmp_path_factory.mktemp("target") / "target.jpg"
    im = Image.new("RGB", (400, 600), (230, 200, 160))
    d = ImageDraw.Draw(im)
    d.ellipse((90, 120, 310, 400), fill=(120, 70, 40))
    d.ellipse((140, 220, 180, 250), fill=(20, 20, 20))
    d.ellipse((220, 220, 260, 250), fill=(20, 20, 20))
    im.save(path, quality=95)
    return path
