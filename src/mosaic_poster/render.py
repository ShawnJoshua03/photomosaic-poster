"""Turning a target photo plus a folder of photos into a print-ready poster file."""
import io
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .assign import assign_tiles
from .color import LUMA, find_cmyk_profile, make_finisher
from .tiles import find_photos, load_tiles, tile_mean_colors, visual_groups

log = logging.getLogger("mosaic_poster")

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
RASTER_EXTS = {".png", ".tif", ".tiff"}
JPEG_EXTS = {".jpg", ".jpeg"}


@dataclass
class PosterOptions:
    target: str
    tile_dirs: list
    output: str = "mosaic_poster.png"
    width_in: float = 24.0
    height_in: float = 36.0
    dpi: float = 150.0
    cols: int = 0  # 0 = choose automatically from print size and photo count
    tint: float = 0.5
    overlay: float = 0.3
    # target photo prep
    crop: tuple = None  # (left, top, right, bottom) as fractions 0-1
    focus_y: float = 0.4
    gamma: float = 1.0
    autolevel: float = 0.0
    save_target: str = ""
    # tile choice
    max_repeats: int = 0
    spacing: int = 5
    variety: int = 16
    use_all: bool = True
    seed: int = 1
    # banner
    text: str = ""
    text_height_in: float = 3.0
    bg: tuple = (17, 17, 17)
    fg: tuple = (255, 255, 255)
    # print finishing and file format
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    cmyk: bool = False
    cmyk_profile: str = None  # None = look for one installed on this machine
    jpeg_quality: int = 90
    max_mb: float = 0.0
    optimize: bool = True
    embed_icc: bool = True
    panels: int = 1
    overlap_in: float = 0.0
    cache_dir: str = ".mosaic-cache"  # "" disables the decoded-tile cache
    outputs: list = field(default_factory=list)  # filled in with the files written


def auto_cols(width_in, mosaic_height_in, n_photos, tile_in=0.5, target_uses=3.0):
    """Columns giving ~0.5 inch tiles, but no more cells than ~3 uses per photo."""
    by_size = width_in / tile_in
    by_photos = math.sqrt(target_uses * max(n_photos, 1) * width_in / mosaic_height_in)
    return max(8, int(round(min(by_size, by_photos))))


def make_poster(opt: PosterOptions):
    """Render the poster described by `opt`. Returns the list of files written."""
    out_path = Path(opt.output)
    ext = out_path.suffix.lower()
    if ext not in RASTER_EXTS | JPEG_EXTS | {".pdf"}:
        raise ValueError("output must be .png, .jpg, .pdf or .tif")
    if opt.cmyk and ext == ".png":
        raise ValueError("PNG can't hold CMYK; save CMYK as .jpg, .pdf or .tif")
    if not 0 <= opt.tint <= 1 or not 0 <= opt.overlay <= 1:
        raise ValueError("tint and overlay must be between 0 and 1")

    W, H = round(opt.width_in * opt.dpi), round(opt.height_in * opt.dpi)
    band_h = round(opt.text_height_in * opt.dpi) if opt.text else 0
    mosaic_h = H - band_h
    cols = opt.cols
    if not cols:
        n = len(find_photos(opt.tile_dirs))
        cols = auto_cols(opt.width_in, mosaic_h / opt.dpi, n)
        log.info(f"--cols auto: {cols} columns for {n} photo files")
    rows = round(mosaic_h * cols / W)
    if rows < 1:
        raise ValueError("too many columns or banner too tall: no room for tiles")
    # Tile edges split the page exactly (neighbouring tiles may differ by 1 px), so the
    # mosaic always fills the whole page, edge to edge, at any size and DPI.
    xe = np.rint(np.linspace(0, W, cols + 1)).astype(int)
    ye = np.rint(np.linspace(0, mosaic_h, rows + 1)).astype(int)
    cell = math.ceil(W / cols)
    log.info(f"Canvas {W}x{H}px ({opt.width_in:g}x{opt.height_in:g} in @ {opt.dpi:g} DPI), "
             f"grid {cols}x{rows} = {cols * rows} tiles of ~{opt.width_in / cols:.2f} in")

    base, cell_rgb, K = _prepare_target(opt, cols, rows)

    log.info("Loading tile photos...")
    cache = None
    if opt.cache_dir:
        Path(opt.cache_dir).mkdir(parents=True, exist_ok=True)
        cache = str(Path(opt.cache_dir) / f"tiles_{cell}px.npz")
    names, tiles = load_tiles(opt.tile_dirs, cell, cache)
    if not names:
        raise SystemExit("No usable photos found in the tile folders.")
    groups = visual_groups(tiles)
    log.info(f"Loaded {len(names)} photos, {groups.max() + 1} visually distinct")
    grid = assign_tiles(cell_rgb, tile_mean_colors(tiles), max_repeats=opt.max_repeats,
                        seed=opt.seed, spacing=opt.spacing, variety=opt.variety,
                        groups=groups, tint=opt.tint, use_all=opt.use_all)

    profile = None
    if opt.cmyk:
        profile = opt.cmyk_profile or find_cmyk_profile()
        log.info(f"CMYK profile: {profile or 'none found (basic conversion)'}")
    gray_mean = float((cell_rgb @ LUMA).mean()) * opt.brightness
    finish = make_finisher(opt.brightness, opt.contrast, opt.saturation, gray_mean,
                           cmyk=opt.cmyk, cmyk_profile=profile)

    out = Image.new("CMYK" if opt.cmyk else "RGB", (W, H))
    mean_all = tiles.mean(axis=(1, 2))
    # Build the poster a few tile-rows at a time so even a 175-megapixel print fits in RAM.
    strip_rows, pad = 4, 2
    for r0 in range(0, rows, strip_rows):
        r1 = min(rows, r0 + strip_rows)
        y0, y1 = ye[r0], ye[r1]
        strip = Image.new("RGB", (W, y1 - y0))
        for r in range(r0, r1):
            for c in range(cols):
                i = grid[r, c]
                # Shift the photo's average color toward the cell's; keeps its detail.
                t = tiles[i].astype(np.float32) + opt.tint * (cell_rgb[r, c] - mean_all[i])
                tile = Image.fromarray(np.clip(t, 0, 255).astype(np.uint8))
                size = (xe[c + 1] - xe[c], ye[r + 1] - ye[r])
                if tile.size != size:
                    tile = tile.resize(size, Image.LANCZOS)
                strip.paste(tile, (xe[c], ye[r] - y0))
        if opt.overlay > 0:
            # A faint, sharpened copy of the target on top restores eye/mouth/hair detail
            # a coarse grid can't carry. The padding rows keep the sharpen filter from
            # leaving seams where strips meet.
            p0, p1 = max(0, r0 - pad), min(rows, r1 + pad)
            region = base.crop((0, p0 * K, cols * K, p1 * K)).resize(
                (W, ye[p1] - ye[p0]), Image.LANCZOS)
            region = region.filter(ImageFilter.UnsharpMask(radius=cell / 3, percent=150,
                                                           threshold=2))
            strip = Image.blend(strip, region.crop((0, y0 - ye[p0], W, y1 - ye[p0])),
                                opt.overlay)
        out.paste(finish(strip), (0, y0))
        log.debug(f"  rendered rows {r1}/{rows}")

    if band_h:
        strip = Image.new("RGB", (W, band_h), tuple(opt.bg))
        _draw_banner(strip, opt.text, tuple(opt.fg))
        out.paste(finish(strip), (0, mosaic_h))

    icc = Path(profile).read_bytes() if (profile and opt.embed_icc) else None
    opt.outputs = []
    for path, (y0, y1) in _panel_ranges(out_path, H, opt.panels,
                                        round(opt.overlap_in * opt.dpi)):
        img = out if (y0, y1) == (0, H) else out.crop((0, y0, W, y1))
        _save(img, path, opt, icc)
        log.info(f"Saved {path} ({W / opt.dpi:g} x {(y1 - y0) / opt.dpi:g} in)")
        opt.outputs.append(path)
    return opt.outputs


def _prepare_target(opt, cols, rows):
    target = ImageOps.exif_transpose(Image.open(opt.target)).convert("RGB")
    if opt.crop:
        l, t, r, b = opt.crop
        target = target.crop((int(l * target.width), int(t * target.height),
                              int(r * target.width), int(b * target.height)))
    if opt.autolevel > 0:
        target = ImageOps.autocontrast(target, cutoff=opt.autolevel)
    if opt.gamma != 1.0:
        lut = [round(255 * (i / 255) ** opt.gamma) for i in range(256)]
        target = target.point(lut * 3)
    # Keep the target at about its own resolution; strips are upscaled when drawn.
    K = max(1, int(min(target.width / cols, target.height / rows)))
    base = ImageOps.fit(target, (cols * K, rows * K), Image.LANCZOS,
                        centering=(0.5, opt.focus_y))
    if opt.save_target:
        base.save(opt.save_target)
    cell_rgb = np.asarray(base.resize((cols, rows), Image.BOX), dtype=np.float32)
    return base, cell_rgb, K


def _panel_ranges(out_path, H, panels, overlap):
    """(path, (y0, y1)) for each horizontal panel; one panel = the whole poster."""
    if panels <= 1:
        return [(out_path, (0, H))]
    step = (H - overlap) / panels
    ranges = []
    for i in range(panels):
        y0 = round(i * step)
        y1 = H if i == panels - 1 else round((i + 1) * step + overlap)
        name = out_path.with_name(f"{out_path.stem}_part{i + 1}of{panels}{out_path.suffix}")
        ranges.append((name, (y0, y1)))
    return ranges


def _save(img, path, opt, icc):
    ext = path.suffix.lower()
    if ext in RASTER_EXTS:
        extra = {"compression": "tiff_lzw"} if ext != ".png" else {}
        img.save(path, dpi=(opt.dpi, opt.dpi), **extra)
        return

    def encode(q):
        buf = io.BytesIO()
        if ext == ".pdf":
            # One page sized to the print, with the image stored as JPEG (DCTDecode).
            img.save(buf, "PDF", resolution=opt.dpi, quality=q, optimize=opt.optimize)
        else:
            img.save(buf, "JPEG", quality=q, optimize=opt.optimize,
                     dpi=(round(opt.dpi),) * 2, **({"icc_profile": icc} if icc else {}))
        mb = buf.tell() / 1e6
        log.info(f"  quality {q}: {mb:.1f} MB")
        return buf, mb

    if not opt.max_mb:
        buf, _ = encode(opt.jpeg_quality)
    else:
        # The highest quality that fits under the size limit (binary search).
        lo, hi, best = 30, opt.jpeg_quality, None
        while lo <= hi:
            q = (lo + hi) // 2
            buf, mb = encode(q)
            if mb <= opt.max_mb:
                best, lo = (q, buf, mb), q + 1
            else:
                hi = q - 1
        if best is None:
            raise SystemExit(f"Can't get under {opt.max_mb} MB even at quality 30: "
                             f"lower --dpi or use --panels.")
        q, buf, mb = best
        log.info(f"  using quality {q} ({mb:.1f} MB)")
    path.write_bytes(buf.getbuffer())


def _find_font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    log.warning("No bold TrueType font found; banner text will be small.")
    return ImageFont.load_default()


def _draw_banner(canvas, text, fg):
    """Center `text` on the canvas, as large as fits."""
    draw = ImageDraw.Draw(canvas)
    max_w, max_h = int(canvas.width * 0.92), int(canvas.height * 0.6)
    size = max_h
    while True:
        font = _find_font(size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if (r - l <= max_w and b - t <= max_h) or size <= 10:
            break
        size -= max(2, size // 20)
    x = (canvas.width - (r - l)) // 2 - l
    y = (canvas.height - (b - t)) // 2 - t
    draw.text((x, y), text, font=font, fill=fg)
