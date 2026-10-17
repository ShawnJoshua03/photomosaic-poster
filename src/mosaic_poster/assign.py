"""Choosing which photo goes in which cell."""
import logging
import math

import numpy as np

from .color import srgb_to_lab

log = logging.getLogger("mosaic_poster")

# Soft pressure toward under-used photos (squared-Lab units per prior use).
SPREAD_PENALTY = 15.0
# Random picks must be within this squared-Lab distance of the best match
# (widened automatically by the tint, which corrects part of any color miss).
VARIETY_TOLERANCE = 60.0


def assign_tiles(cell_rgb, tile_rgb, *, max_repeats=0, seed=1, spacing=5, variety=16,
                 groups=None, tint=0.0, use_all=True):
    """Pick a photo for every cell. Returns a (rows, cols) array of tile indices.

    cell_rgb: (rows, cols, 3) average colors of the target image's cells.
    tile_rgb: (n, 3) average colors of the photos.
    max_repeats: cap on uses of any one photo (0 = automatic).
    spacing: a photo, or any look-alike of it, can't reappear within this many cells.
    variety: choose randomly among this many near-best photos, so flat areas (sky,
        walls) don't fill up with the same few pictures.
    groups: look-alike group id per photo (see tiles.visual_groups).
    use_all: afterwards, make sure every distinct photo appears at least once.
    """
    rows, cols, _ = cell_rgb.shape
    n = len(tile_rgb)
    total = rows * cols
    need = math.ceil(total / n)
    if max_repeats <= 0:
        max_repeats = max(need + 1, math.ceil(1.5 * total / n))
    elif max_repeats < need:
        log.warning(f"{n} photos can't fill {total} cells with at most {max_repeats} "
                    f"repeats; raising the cap to {need}. Add photos or use fewer --cols.")
        max_repeats = need
    log.info(f"{total} cells, {n} photos, each used at most {max_repeats}x "
             f"(average {total / n:.1f}x)")

    cell_lab = srgb_to_lab(cell_rgb).reshape(-1, 3)
    tile_lab = srgb_to_lab(tile_rgb)
    grid = -np.ones((rows, cols), dtype=np.int64)
    uses = np.zeros(n, dtype=np.int64)
    if groups is None:
        groups = np.arange(n)
    group_uses = np.zeros(groups.max() + 1, dtype=np.int64)
    group_cap = math.ceil(1.5 * max_repeats)  # a look-alike set counts as ~1.5 photos
    tolerance = VARIETY_TOLERANCE / max(1 - min(tint, 0.9), 0.1) ** 2
    rng = np.random.default_rng(seed)

    def nearby(r, c, radius):
        win = grid[max(0, r - radius):r + radius + 1, max(0, c - radius):c + radius + 1]
        near = np.unique(groups[win[win >= 0]])
        return np.isin(groups, near)  # every look-alike of a nearby photo is off limits

    for flat in rng.permutation(total):  # random order avoids directional bias
        r, c = divmod(int(flat), cols)
        cost = ((tile_lab - cell_lab[flat]) ** 2).sum(axis=1) + SPREAD_PENALTY * uses
        over_cap = (uses >= max_repeats) | (group_uses[groups] >= group_cap)
        # Strictest rule first; relax only if no photo is left (very few photos).
        for radius, use_cap in ((spacing, True), (1, True), (1, False), (0, False)):
            banned = over_cap.copy() if use_cap else np.zeros(n, dtype=bool)
            if radius:
                banned |= nearby(r, c, radius)
            if not banned.all():
                break
        cost[banned] = np.inf
        k = min(variety, int((~banned).sum()))
        pool = np.argpartition(cost, k - 1)[:k] if k < n else np.arange(n)
        pool = pool[cost[pool] <= cost[pool].min() + tolerance]
        best = int(rng.choice(pool))
        grid[r, c] = best
        uses[best] += 1
        group_uses[groups[best]] += 1

    if use_all:
        # People look for their own photos: give every distinct photo at least one
        # spot, swapped in where it costs the least color accuracy, replacing only
        # photos that already appear somewhere else.
        flat = grid.reshape(-1)
        current = ((tile_lab[flat] - cell_lab) ** 2).sum(axis=1)
        missing = [np.flatnonzero(groups == g) for g in range(groups.max() + 1)
                   if group_uses[g] == 0]
        placed = 0
        for members in missing:
            costs = ((cell_lab[None] - tile_lab[members][:, None]) ** 2).sum(axis=2)
            delta = np.where(uses[flat] > 1, costs - current, np.inf)
            m, cidx = np.unravel_index(np.argmin(delta), delta.shape)
            if not np.isfinite(delta[m, cidx]):
                break  # more distinct photos than cells
            t = members[m]
            uses[flat[cidx]] -= 1
            flat[cidx] = t
            uses[t] += 1
            current[cidx] = costs[m, cidx]
            placed += 1
        if placed:
            log.info(f"placed {placed} otherwise-unused photos so every distinct photo appears")

    log.info(f"most-used photo appears {uses.max()}x; {int((uses == 0).sum())} files unused")
    return grid
