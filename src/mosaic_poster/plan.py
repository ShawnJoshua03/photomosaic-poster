"""Poster layout math, shared by the pre-flight check and the renderer."""
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps


@dataclass
class Plan:
    width_in: float
    height_in: float
    dpi: float
    W: int            # pixels
    H: int
    band_h: int       # banner height in pixels (0 = no banner)
    cols: int
    rows: int

    @property
    def mosaic_h(self):
        return self.H - self.band_h

    @property
    def cells(self):
        return self.cols * self.rows

    @property
    def tile_in(self):
        return self.width_in / self.cols

    @property
    def megapixels(self):
        return self.W * self.H / 1e6


def auto_cols(width_in, mosaic_height_in, n_photos, tile_in=0.5, target_uses=3.0):
    """Columns giving ~0.5 inch tiles, but no more cells than ~3 uses per photo."""
    by_size = width_in / tile_in
    by_photos = math.sqrt(target_uses * max(n_photos, 1) * width_in / mosaic_height_in)
    return max(8, int(round(min(by_size, by_photos))))


def make_plan(width_in, height_in, dpi, cols, n_photos, text_height_in=0.0):
    W, H = round(width_in * dpi), round(height_in * dpi)
    band_h = round(text_height_in * dpi)
    mosaic_h = H - band_h
    if mosaic_h <= 0:
        raise ValueError("the banner is taller than the poster")
    if not cols:
        cols = auto_cols(width_in, mosaic_h / dpi, n_photos)
    rows = round(mosaic_h * cols / W)
    if rows < 1:
        raise ValueError("too many columns or banner too tall: no room for tiles")
    return Plan(width_in, height_in, dpi, W, H, band_h, cols, rows)


@dataclass
class TargetStats:
    width: int          # pixels after --crop
    height: int
    ppi: float          # target pixels per printed inch
    brightness: float   # mean luminance 0-255
    contrast: float     # luminance standard deviation
    sharpness: float    # edge strength; low = blurry or tiny
    crop_loss: float    # fraction of the target cut off to fit the poster shape


def analyze_target(img, poster_w_in, poster_h_in):
    """Quick measurements of the target photo used for recommendations."""
    g = np.asarray(ImageOps.contain(img.convert("L"), (800, 800)), dtype=np.float32)
    lap = np.asarray(Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.FIND_EDGES),
                     dtype=np.float32)
    a_img, a_poster = img.width / img.height, poster_w_in / poster_h_in
    loss = 1 - min(a_img, a_poster) / max(a_img, a_poster)
    return TargetStats(img.width, img.height, img.width / poster_w_in, float(g.mean()),
                       float(g.std()), float(lap.mean()), loss)
