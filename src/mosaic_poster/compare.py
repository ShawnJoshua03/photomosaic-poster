"""Compare candidate target photos side by side before committing to a full render."""
import logging
import random

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .assign import assign_tiles
from .formats import open_photo, scan
from .plan import analyze_target, make_plan
from .render import _find_font
from .tiles import decode_tiles, tile_mean_colors, visual_groups

log = logging.getLogger("mosaic_poster")


def score_target(stats):
    """0-100: how well a photo is likely to work as the big picture.

    It can't see faces, so it scores what it can measure: resolution for the print
    size, contrast, sharpness, sensible brightness, and how little gets cropped off.
    """
    parts = {
        "resolution": min(1.0, stats.ppi / 40),
        "contrast": min(1.0, stats.contrast / 60),
        "sharpness": min(1.0, stats.sharpness / 12),
        "brightness": 1 - min(1.0, abs(stats.brightness - 128) / 110),
        "fit": 1 - stats.crop_loss,
    }
    weights = {"resolution": 0.2, "contrast": 0.3, "sharpness": 0.2, "brightness": 0.15,
               "fit": 0.15}
    return round(100 * sum(parts[k] * w for k, w in weights.items())), parts


def compare_targets(targets, sources, out_path, width_in=24, height_in=36, sample=400,
                    tile_px=24, overlay=0.3, tint=0.5, seed=1):
    """Render a quick mosaic of each candidate and save them side by side.

    Uses a random sample of the photos so it takes seconds, not minutes.
    Returns [(target, score, parts, stats)] best first.
    """
    refs, _ = scan(sources)
    if not refs:
        raise SystemExit("No photos found.")
    rng = random.Random(seed)  # nosec B311
    pick = refs if len(refs) <= sample else rng.sample(refs, sample)
    log.info(f"Decoding a sample of {len(pick)} of {len(refs)} photos for previews...")
    _, tiles, _ = decode_tiles(pick, tile_px)
    groups, means = visual_groups(tiles), tile_mean_colors(tiles)

    plan = make_plan(width_in, height_in, 10, 0, len(refs))
    cols, rows = min(plan.cols, 60), max(1, round(min(plan.cols, 60) * height_in / width_in))
    results, panels = [], []
    for t in targets:
        img = open_photo(t)
        stats = analyze_target(img, width_in, height_in)
        score, parts = score_target(stats)
        base = ImageOps.fit(img, (cols * tile_px, rows * tile_px), Image.LANCZOS,
                            centering=(0.5, 0.4))
        cells = np.asarray(base.resize((cols, rows), Image.BOX), dtype=np.float32)
        grid = assign_tiles(cells, means, groups=groups, tint=tint, spacing=2, seed=seed)
        mean_all = tiles.mean(axis=(1, 2))
        mosaic = Image.new("RGB", (cols * tile_px, rows * tile_px))
        for r in range(rows):
            for c in range(cols):
                i = grid[r, c]
                tile = np.clip(tiles[i] + tint * (cells[r, c] - mean_all[i]), 0, 255)
                mosaic.paste(Image.fromarray(tile.astype(np.uint8)), (c * tile_px, r * tile_px))
        if overlay:
            mosaic = Image.blend(mosaic, base, overlay)
        results.append((t, score, parts, stats))
        panels.append((t, score, mosaic))

    _contact_sheet(panels, out_path)
    return sorted(results, key=lambda x: -x[1])


def _contact_sheet(panels, out_path, height=900):
    thumbs = [(t, s, ImageOps.contain(m, (height, height))) for t, s, m in panels]
    label_h = 56
    W = sum(m.width for _, _, m in thumbs) + 24 * (len(thumbs) + 1)
    sheet = Image.new("RGB", (W, height + label_h + 48), (246, 245, 242))
    d = ImageDraw.Draw(sheet)
    font, small = _find_font(26), _find_font(20)
    x = 24
    best = max(s for _, s, _ in thumbs)
    for t, s, m in thumbs:
        sheet.paste(m, (x, 24))
        name = str(t).replace("\\", "/").rsplit("/", 1)[-1]
        d.text((x, 24 + m.height + 10), name, fill=(29, 29, 31), font=font)
        d.text((x, 24 + m.height + 42), f"score {s}/100" + ("  - best" if s == best else ""),
               fill=(46, 125, 50) if s == best else (107, 107, 112), font=small)
        x += m.width + 24
    sheet.save(out_path)
