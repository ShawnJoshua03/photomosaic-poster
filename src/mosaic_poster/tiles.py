"""Decoding, caching and de-duplicating the tile photos."""
import hashlib
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .formats import open_photo, scan

log = logging.getLogger("mosaic_poster")


def load_tiles(sources, tile_px, cache=None, include_videos=False):
    """Load every photo as an upright, center-cropped tile_px square (uint8 RGB).

    sources: folders, files or .zip files. Returns (names, tiles, report) with tiles
    shaped (n, tile_px, tile_px, 3); report is a Counter of what was skipped and why.
    Exact duplicate files are dropped. Decoded tiles are cached in `cache` so that
    re-rendering with different settings skips the slow decode.
    """
    refs, skipped = scan(sources, include_videos)
    sig = hashlib.md5(("\n".join(r.key for r in refs) + f"|{tile_px}").encode()).hexdigest()
    if cache and Path(cache).exists():
        with np.load(cache, allow_pickle=False) as z:
            if str(z["sig"]) == sig:
                log.info(f"Using cached tiles from {cache}")
                skipped = Counter(dict(zip(z["skip_reason"].tolist(),
                                           z["skip_count"].tolist())))
                return list(z["names"]), z["tiles"], skipped
    names, tiles, more = decode_tiles(refs, tile_px)
    skipped.update(more)
    if cache and names:
        np.savez(cache, sig=sig, names=np.array(names), tiles=tiles,
                 skip_reason=np.array(list(skipped), dtype=str),
                 skip_count=np.array(list(skipped.values()), dtype=np.int64))
    return names, tiles, skipped


def _decode_one(ref, tile_px):
    data = ref.read_bytes()
    digest = hashlib.md5(data).hexdigest()
    im = open_photo(ref, draft=(tile_px * 2, tile_px * 2))
    # Slightly above center: people's faces usually sit in the upper half.
    im = ImageOps.fit(im, (tile_px, tile_px), Image.LANCZOS, centering=(0.5, 0.4))
    return digest, np.asarray(im, dtype=np.uint8)


def decode_tiles(refs, tile_px, workers=4):
    """Decode refs in parallel (HEIC and RAW decoding release the GIL)."""
    tiles, names, seen, skipped = [], [], set(), Counter()

    def job(ref):
        try:
            return ref, _decode_one(ref, tile_px), None
        except Exception as e:  # corrupt or unreadable file
            return ref, None, e

    with ThreadPoolExecutor(workers) as pool:
        for i, (ref, result, err) in enumerate(pool.map(job, refs), 1):
            if err is not None:
                skipped["unreadable or damaged"] += 1
                log.warning(f"  skipped {ref.name}: {err}")
            else:
                digest, tile = result
                if digest in seen:  # the same file uploaded twice
                    skipped["exact duplicate"] += 1
                else:
                    seen.add(digest)
                    tiles.append(tile)
                    names.append(ref.name)
            if i % 250 == 0:
                log.info(f"  decoded {i}/{len(refs)} files")
    if not tiles:
        return [], np.empty((0, tile_px, tile_px, 3), dtype=np.uint8), skipped
    return names, np.stack(tiles), skipped


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
