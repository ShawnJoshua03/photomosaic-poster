import numpy as np

from mosaic_poster.assign import assign_tiles


def _setup(n=60, rows=12, cols=10, seed=0):
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 255, (rows, cols, 3)), rng.uniform(0, 255, (n, 3))


def test_every_cell_filled_and_repeats_capped():
    cells, tiles = _setup()
    grid = assign_tiles(cells, tiles, max_repeats=3, spacing=2)
    assert grid.min() >= 0
    assert np.bincount(grid.ravel()).max() <= 3


def test_no_photo_repeats_within_spacing():
    cells, tiles = _setup(n=80)
    spacing = 2
    grid = assign_tiles(cells, tiles, spacing=spacing)
    rows, cols = grid.shape
    for r in range(rows):
        for c in range(cols):
            win = grid[max(0, r - spacing):r + spacing + 1, max(0, c - spacing):c + spacing + 1]
            assert (win == grid[r, c]).sum() == 1


def test_look_alikes_are_kept_apart():
    cells, tiles = _setup(n=60)
    groups = np.arange(60) // 2  # pairs of look-alike photos
    grid = assign_tiles(cells, tiles, groups=groups, spacing=1)
    g = groups[grid]
    rows, cols = g.shape
    for r in range(rows):
        for c in range(cols):
            win = g[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
            assert (win == g[r, c]).sum() == 1


def test_every_distinct_photo_is_used():
    cells, tiles = _setup(n=60, rows=12, cols=10)  # 120 cells, 60 photos
    grid = assign_tiles(cells, tiles, use_all=True)
    assert set(np.unique(grid)) == set(range(60))


def test_too_few_photos_still_fills_the_grid():
    cells, tiles = _setup(n=3, rows=5, cols=5)
    grid = assign_tiles(cells, tiles, max_repeats=2)  # cap gets raised automatically
    assert grid.min() >= 0


def test_seed_changes_layout_but_is_reproducible():
    cells, tiles = _setup()
    a = assign_tiles(cells, tiles, seed=1)
    assert np.array_equal(a, assign_tiles(cells, tiles, seed=1))
    assert not np.array_equal(a, assign_tiles(cells, tiles, seed=2))
