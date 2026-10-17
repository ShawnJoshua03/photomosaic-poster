import numpy as np
from PIL import Image

from mosaic_poster.formats import scan
from mosaic_poster.tiles import load_tiles, visual_groups


def test_finds_photos_recursively_and_ignores_other_files(photos):
    names = {r.name for r in scan([photos])[0]}
    assert "deep.png" in names
    assert "notes.txt" not in names


def test_skips_duplicates_and_corrupt_files(photos):
    names, tiles, _ = load_tiles([photos], 16)
    assert "broken.jpg" not in names
    assert ("img_000.jpg" in names) != ("img_000_copy.jpg" in names)  # only one copy kept
    assert tiles.shape == (len(names), 16, 16, 3)
    assert tiles.dtype == np.uint8


def test_exif_rotation_is_applied(tmp_path):
    # Stored pixels: red top half, blue bottom half. EXIF orientation 6 means "rotate
    # 90 degrees clockwise to display", so the displayed photo is blue left, red right.
    a = np.zeros((100, 100, 3), np.uint8)
    a[:50] = (255, 0, 0)
    a[50:] = (0, 0, 255)
    im = Image.fromarray(a)
    exif = im.getexif()
    exif[274] = 6
    im.save(tmp_path / "phone.jpg", exif=exif, quality=95)
    _, tiles, _ = load_tiles([tmp_path], 20)
    left, right = tiles[0][:, :5].mean(axis=(0, 1)), tiles[0][:, -5:].mean(axis=(0, 1))
    assert left[2] > 200 and left[0] < 60      # blue on the left
    assert right[0] > 200 and right[2] < 60    # red on the right


def test_heic_photos_load(tmp_path):
    import pillow_heif  # noqa: F401  (registers the HEIC opener)
    Image.new("RGB", (64, 48), (10, 200, 30)).save(tmp_path / "phone.heic")
    names, tiles, _ = load_tiles([tmp_path], 8)
    assert names == ["phone.heic"]
    assert tiles[0].mean(axis=(0, 1))[1] > 150


def test_cache_is_reused_and_invalidated(photos, tmp_path):
    cache = tmp_path / "c.npz"
    n1, t1, _ = load_tiles([photos], 12, str(cache))
    assert cache.exists()
    n2, t2, _ = load_tiles([photos], 12, str(cache))
    assert n1 == n2 and np.array_equal(t1, t2)
    _, t3, _ = load_tiles([photos], 10, str(cache))  # different tile size -> re-decoded
    assert t3.shape[1] == 10


def test_look_alikes_are_grouped(photos):
    _, tiles, _ = load_tiles([photos], 32)
    burst = np.concatenate([tiles[:1], np.clip(tiles[:1].astype(int) + 6, 0, 255)
                            .astype(np.uint8), tiles[1:4]])
    g = visual_groups(burst)
    assert g[0] == g[1]           # a slightly brighter copy is the same photo
    assert len(set(g[2:])) == 3   # different photos stay separate
