"""Finding, decoding, caching and de-duplicating the tile photos."""
import hashlib
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HAVE_HEIF = True
except ImportError:  # pragma: no cover - pillow-heif is a normal dependency
    HAVE_HEIF = False

log = logging.getLogger("mosaic_poster")

Image.MAX_IMAGE_PIXELS = None  # phone panoramas can be huge

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}


def find_photos(folders):
    """Every photo file under the given folders (recursive), in a stable order."""
    return sorted(p for f in folders for p in Path(f).rglob("*")
                  if p.is_file() and p.suffix.lower() in PHOTO_EXTS)


def load_tiles(folders, tile_px, cache=None):
    """Load every photo as an upright, center-cropped tile_px square (uint8 RGB).

    Returns (names, tiles) with tiles shaped (n, tile_px, tile_px, 3). Exact duplicate
    files are skipped. Decoded tiles are cached in `cache` (keyed on the file list, file
    sizes and tile_px), so re-rendering with different settings skips the slow decode.
    """
    paths = find_photos(folders)
    sig = hashlib.md5(("\n".join(f"{p}|{p.stat().st_size}" for p in paths)
                       + f"|{tile_px}").encode()).hexdigest()
    if cache and Path(cache).exists():
        with np.load(cache, allow_pickle=False) as z:
            if str(z["sig"]) == sig:
                log.info(f"Using cached tiles from {cache}")
                return list(z["names"]), z["tiles"]
    names, tiles = decode_tiles(paths, tile_px)
    if cache and names:
        np.savez(cache, sig=sig, names=np.array(names), tiles=tiles)
    return names, tiles


def decode_tiles(paths, tile_px):
    if not HAVE_HEIF and any(p.suffix.lower() in (".heic", ".heif") for p in paths):
        log.warning("HEIC files found but pillow-heif is not installed "
                    "(pip install pillow-heif); they will be skipped.")
    tiles, names, seen, dupes = [], [], set(), 0
    for i, p in enumerate(paths, 1):
        try:
            digest = hashlib.md5(p.read_bytes()).hexdigest()
            if digest in seen:  # the same file uploaded twice
                dupes += 1
                continue
            seen.add(digest)
            with Image.open(p) as im:
                if im.format == "JPEG":
                    im.draft("RGB", (tile_px * 2, tile_px * 2))  # fast downscaled decode
                im = ImageOps.exif_transpose(im)  # phone photos store rotation in EXIF
                im = im.convert("RGB")
                # Slightly above center: people's faces usually sit in the upper half.
                im = ImageOps.fit(im, (tile_px, tile_px), Image.LANCZOS, centering=(0.5, 0.4))
                tiles.append(np.asarray(im, dtype=np.uint8))
                names.append(p.name)
        except Exception as e:  # corrupt or unsupported file
            log.warning(f"  skipped {p.name}: {e}")
        if i % 250 == 0:
            log.info(f"  decoded {i}/{len(paths)} files")
    if dupes:
        log.info(f"  skipped {dupes} exact duplicate files")
    if not tiles:
        return [], np.empty((0, tile_px, tile_px, 3), dtype=np.uint8)
    return names, np.stack(tiles)


def tile_mean_colors(tiles):
    """Average color of each tile, ignoring the outer 10% (edges are often junk)."""
    n, h, w, _ = tiles.shape
    m = max(1, int(h * 0.1))
    return tiles[:, m:h - m, m:w - m].reshape(n, -1, 3).mean(axis=1)


def visual_groups(tiles, max_dist=6):
    """Group look-alike photos (burst shots, retakes) with a 64-bit difference hash.

    Returns an int array; photos in the same group look nearly identical, so the
    spacing and repeat rules treat them as one photo.
    """
    bits = []
    for t in tiles:
        g = Image.fromarray(t.mean(axis=2).astype(np.uint8)).resize((9, 8), Image.BILINEAR)
        a = np.asarray(g, dtype=np.int16)
        bits.append((a[:, 1:] > a[:, :-1]).ravel())
    bits = np.array(bits)
    group = -np.ones(len(tiles), dtype=np.int64)
    k = 0
    for i in range(len(tiles)):
        if group[i] < 0:
            close = (bits != bits[i]).sum(axis=1) <= max_dist
            group[close & (group < 0)] = k
            k += 1
    return group
