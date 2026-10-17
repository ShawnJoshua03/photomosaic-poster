"""Turning a target photo plus folders of photos into print-ready poster files."""
import io
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageFont, ImageOps

from .advice import advise
from .assign import assign_tiles
from .color import LUMA, find_cmyk_profile, make_finisher
from .formats import open_photo, scan
from .plan import analyze_target, make_plan
from .printers import PAPERS, PRINTERS
from .proof import detail_focus, gamut_loss, make_previews, simulate
from .tiles import load_tiles, tile_mean_colors, visual_groups

log = logging.getLogger("mosaic_poster")

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
FORMATS = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".pdf": "pdf", ".tif": "tif",
           ".tiff": "tif", ".webp": "webp"}


class PreflightError(Exception):
    """The poster breaks a printer rule; .findings says what and how to fix it."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f.title for f in findings if f.level == "error"))


@dataclass
class PosterOptions:
    target: str
    tile_dirs: list               # folders, files or .zip files
    output: str = "mosaic_poster.png"
    width_in: float = 24.0
    height_in: float = 36.0
    dpi: float = 150.0
    cols: int = 0                 # 0 = choose from print size and photo count
    tint: float = 0.5
    overlay: float = 0.3
    # target photo prep
    crop: tuple = None            # (left, top, right, bottom) as fractions 0-1
    focus_y: float = 0.4
    gamma: float = 1.0
    autolevel: float = 0.0
    save_target: str = ""
    # photos
    include_videos: bool = False
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
    # printer, paper and color
    printer: str = None           # key from printers.PRINTERS
    paper: str = None             # key from printers.PAPERS (defaults to the printer's)
    printer_profile: str = None   # ICC profile of printer+paper, for exact previews
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    cmyk: bool = False
    cmyk_profile: str = None      # None = look for one installed on this machine
    embed_icc: bool = True
    # files
    jpeg_quality: int = 90
    max_mb: float = 0.0
    optimize: bool = True
    panels: int = 1
    overlap_in: float = 0.0
    test_strip: bool = False
    strip_height_in: float = 3.0
    fallbacks: bool = False
    preview: bool = True          # write <name>.report.html with print previews
    force: bool = False           # render even if a printer rule is broken
    cache_dir: str = ".mosaic-cache"


@dataclass
class RenderResult:
    plan: object
    files: list = field(default_factory=list)      # (path, jpeg quality or None, MB)
    n_photos: int = 0
    n_distinct: int = 0
    max_uses: int = 0
    unused: int = 0
    skipped: dict = field(default_factory=dict)
    gamut_pct: float = None
    findings: list = field(default_factory=list)
    report: Path = None

    @property
    def outputs(self):
        return [p for p, _, _ in self.files]


def resolve_printer(opt):
    printer = PRINTERS[opt.printer] if opt.printer else None
    paper_key = opt.paper or (printer.paper if printer else None)
    return printer, PAPERS[paper_key] if paper_key else None


def load_target(opt):
    target = open_photo(opt.target)
    if opt.crop:
        l, t, r, b = opt.crop
        target = target.crop((int(l * target.width), int(t * target.height),
                              int(r * target.width), int(b * target.height)))
    if opt.autolevel > 0:
        target = ImageOps.autocontrast(target, cutoff=opt.autolevel)
    if opt.gamma != 1.0:
        lut = [round(255 * (i / 255) ** opt.gamma) for i in range(256)]
        target = target.point(lut * 3)
    return target


def preflight(opt):
    """Check the plan against the printer and photos without rendering anything.

    Returns (plan, findings, context) where context holds what make_poster reuses.
    """
    out_ext = Path(opt.output).suffix.lower()
    if out_ext not in FORMATS:
        raise ValueError(f"output must be one of: {', '.join(sorted(set(FORMATS)))}")
    if opt.cmyk and FORMATS[out_ext] in ("png", "webp"):
        raise ValueError("PNG and WebP can't hold CMYK; save CMYK as .pdf, .jpg or .tif")
    if not 0 <= opt.tint <= 1 or not 0 <= opt.overlay <= 1:
        raise ValueError("tint and overlay must be between 0 and 1")
    printer, paper = resolve_printer(opt)
    refs, skipped = scan(opt.tile_dirs, opt.include_videos)
    target = load_target(opt)
    plan = make_plan(opt.width_in, opt.height_in, opt.dpi, opt.cols, len(refs),
                     opt.text_height_in if opt.text else 0)
    stats = analyze_target(target, opt.width_in, plan.mosaic_h / opt.dpi)
    findings = advise(opt, plan, printer, paper, stats, len(refs), skipped)
    return plan, findings, dict(printer=printer, paper=paper, target=target, skipped=skipped)


def make_poster(opt: PosterOptions):
    """Render the poster. Returns a RenderResult (files written, stats, findings)."""
    plan, findings, ctx = preflight(opt)
    for fnd in findings:
        (log.warning if fnd.level in ("error", "warn") else log.info)(str(fnd))
    if any(x.level == "error" for x in findings) and not opt.force:
        raise PreflightError(findings)
    printer, paper = ctx["printer"], ctx["paper"]
    W, H, cols, rows = plan.W, plan.H, plan.cols, plan.rows
    xe = np.rint(np.linspace(0, W, cols + 1)).astype(int)  # exact edge-to-edge tiling
    ye = np.rint(np.linspace(0, plan.mosaic_h, rows + 1)).astype(int)
    cell = math.ceil(W / cols)
    log.info(f"Canvas {W}x{H}px ({opt.width_in:g}x{opt.height_in:g} in @ {opt.dpi:g} DPI), "
             f"{cols}x{rows} = {plan.cells} tiles of {plan.tile_in:.2f} in")

    # Keep the target at about its own resolution; strips are upscaled when drawn.
    target = ctx["target"]
    K = max(1, int(min(target.width / cols, target.height / rows)))
    base = ImageOps.fit(target, (cols * K, rows * K), Image.LANCZOS,
                        centering=(0.5, opt.focus_y))
    if opt.save_target:
        base.save(opt.save_target)
    cell_rgb = np.asarray(base.resize((cols, rows), Image.BOX), dtype=np.float32)

    log.info("Loading photos...")
    cache = None
    if opt.cache_dir:
        Path(opt.cache_dir).mkdir(parents=True, exist_ok=True)
        cache = str(Path(opt.cache_dir) / f"tiles_{cell}px.npz")
    names, tiles, skipped = load_tiles(opt.tile_dirs, cell, cache, opt.include_videos)
    if not names:
        raise SystemExit("No usable photos found.")
    groups = visual_groups(tiles)
    log.info(f"Loaded {len(names)} photos, {groups.max() + 1} visually distinct")
    grid = assign_tiles(cell_rgb, tile_mean_colors(tiles), max_repeats=opt.max_repeats,
                        seed=opt.seed, spacing=opt.spacing, variety=opt.variety,
                        groups=groups, tint=opt.tint, use_all=opt.use_all)
    uses = np.bincount(grid.ravel(), minlength=len(names))

    gray_mean = float((cell_rgb @ LUMA).mean()) * opt.brightness
    finish = make_finisher(opt.brightness, opt.contrast, opt.saturation, gray_mean)
    poster = _draw(opt, plan, tiles, grid, cell_rgb, base, K, xe, ye, cell, finish)

    cmyk_profile = None
    if opt.cmyk or opt.fallbacks:
        cmyk_profile = opt.cmyk_profile or find_cmyk_profile()
    result = RenderResult(plan, n_photos=len(names), n_distinct=int(groups.max() + 1),
                          max_uses=int(uses.max()), unused=int((uses == 0).sum()),
                          skipped=dict(skipped))

    out_path = Path(opt.output)
    for path, (y0, y1) in _panel_ranges(out_path, H, opt.panels, round(opt.overlap_in * opt.dpi)):
        img = poster if (y0, y1) == (0, H) else poster.crop((0, y0, W, y1))
        result.files.append(_save(img, path, opt, opt.cmyk, cmyk_profile))
    focus = detail_focus(base)
    if opt.test_strip:
        sh = min(H, round(opt.strip_height_in * opt.dpi))
        y0 = min(max(0, round(focus[1] * plan.mosaic_h - sh / 2)), H - sh)
        path = out_path.with_name(f"{out_path.stem}.test-strip{out_path.suffix}")
        result.files.append(_save(poster.crop((0, y0, W, y0 + sh)), path, opt, opt.cmyk,
                                  cmyk_profile))
    if opt.fallbacks:
        for ext, cmyk in _fallback_formats(out_path.suffix.lower(), opt.cmyk, printer):
            path = out_path.with_name(f"{out_path.stem}.alt-{'cmyk' if cmyk else 'rgb'}.{ext}")
            result.files.append(_save(poster, path, opt, cmyk, cmyk_profile, plain=True))
    for path, q, mb in result.files:
        log.info(f"Saved {path}" + (f" ({mb:.1f} MB, quality {q})" if q else ""))

    if opt.preview:
        proof_cmyk = cmyk_profile if opt.cmyk else None
        previews = make_previews(poster, (opt.width_in, opt.height_in), focus, paper,
                                 opt.printer_profile, proof_cmyk)
        result.gamut_pct = gamut_loss(previews["screen"][2], paper, opt.printer_profile,
                                      proof_cmyk)
        previews["printed"][2].save(out_path.with_name(f"{out_path.stem}.preview.jpg"),
                                    quality=90)
    stats = analyze_target(target, opt.width_in, plan.mosaic_h / opt.dpi)
    result.findings = advise(opt, plan, printer, paper, stats, len(names), skipped, result)
    if opt.preview:
        from .report import write_report
        result.report = out_path.with_name(f"{out_path.stem}.report.html")
        write_report(result.report, opt, result, printer, paper, previews)
        log.info(f"Preview and recommendations: {result.report}")
    return result


def _draw(opt, plan, tiles, grid, cell_rgb, base, K, xe, ye, cell, finish):
    """Draw the RGB poster a few tile-rows at a time (a 175 MP print fits in RAM)."""
    W, H, cols, rows = plan.W, plan.H, plan.cols, plan.rows
    poster = Image.new("RGB", (W, H))
    mean_all = tiles.mean(axis=(1, 2))
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
            # A faint, sharpened copy of the target restores eye/mouth/hair detail a
            # coarse grid can't carry. Padding rows keep the sharpen filter from leaving
            # seams where strips meet.
            p0, p1 = max(0, r0 - pad), min(rows, r1 + pad)
            region = base.crop((0, p0 * K, cols * K, p1 * K)).resize(
                (W, ye[p1] - ye[p0]), Image.LANCZOS)
            region = region.filter(ImageFilter.UnsharpMask(radius=cell / 3, percent=150,
                                                           threshold=2))
            strip = Image.blend(strip, region.crop((0, y0 - ye[p0], W, y1 - ye[p0])),
                                opt.overlay)
        poster.paste(finish(strip), (0, y0))
    if plan.band_h:
        band = Image.new("RGB", (W, plan.band_h), tuple(opt.bg))
        _draw_banner(band, opt.text, tuple(opt.fg))
        poster.paste(finish(band), (0, plan.mosaic_h))
    return poster


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


def _fallback_formats(primary_ext, cmyk, printer):
    """Alternative files to try if a printer rejects the main one."""
    primary = (FORMATS[primary_ext], cmyk)
    options = [("pdf", cmyk), ("jpg", False), ("pdf", not cmyk)]
    allowed = set(printer.formats) if printer else None
    seen, out = {primary}, []
    for o in options:
        if o not in seen and (allowed is None or o[0] in allowed):
            seen.add(o)
            out.append(o)
    return out


def _to_cmyk(img, profile):
    """RGB -> CMYK in strips (bounded memory), with an ICC profile when available."""
    t = None
    if profile:
        t = ImageCms.buildTransform(
            ImageCms.createProfile("sRGB"), ImageCms.getOpenProfile(profile), "RGB", "CMYK",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    else:
        log.warning("No CMYK ICC profile found; using a basic conversion. "
                    "Pass --cmyk-profile for print-accurate color.")
    out = Image.new("CMYK", img.size)
    for y in range(0, img.height, 1024):
        strip = img.crop((0, y, img.width, min(img.height, y + 1024)))
        out.paste(ImageCms.applyTransform(strip, t) if t else strip.convert("CMYK"), (0, y))
    return out


def _save(img, path, opt, cmyk, cmyk_profile, plain=False):
    """Write one file. Returns (path, JPEG quality used or None, MB)."""
    kind = FORMATS[path.suffix.lower()]
    if cmyk:
        img = _to_cmyk(img, cmyk_profile)
    optimize = opt.optimize and not plain
    icc = Path(cmyk_profile).read_bytes() if (cmyk and cmyk_profile and opt.embed_icc
                                              and not plain) else None
    if kind in ("png", "tif"):
        img.save(path, dpi=(opt.dpi, opt.dpi),
                 **({"compression": "tiff_lzw"} if kind == "tif" else {}))
        return path, None, path.stat().st_size / 1e6
    if kind == "webp" and max(img.size) > 16383:
        raise ValueError("WebP can't be larger than 16383 px; use .jpg or lower --dpi")

    def encode(q):
        buf = io.BytesIO()
        if kind == "pdf":
            # One page at exactly the print size; the image is stored as JPEG.
            img.save(buf, "PDF", resolution=opt.dpi, quality=q, optimize=optimize)
        elif kind == "webp":
            img.save(buf, "WEBP", quality=q, dpi=(opt.dpi, opt.dpi))
        else:
            img.save(buf, "JPEG", quality=q, optimize=optimize, dpi=(round(opt.dpi),) * 2,
                     **({"icc_profile": icc} if icc else {}))
        return buf, buf.tell() / 1e6

    if not opt.max_mb:
        q = opt.jpeg_quality
        buf, mb = encode(q)
    else:
        # The highest quality that fits under the size limit (binary search).
        lo, hi, best = 30, opt.jpeg_quality, None
        while lo <= hi:
            q = (lo + hi) // 2
            buf, mb = encode(q)
            log.debug(f"  {path.name}: quality {q} -> {mb:.1f} MB")
            if mb <= opt.max_mb:
                best, lo = (q, buf, mb), q + 1
            else:
                hi = q - 1
        if best is None:
            raise SystemExit(f"Can't get {path.name} under {opt.max_mb} MB even at quality "
                             f"30: lower --dpi or use --panels.")
        q, buf, mb = best
    path.write_bytes(buf.getbuffer())
    return path, q, mb


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


__all__ = ["PosterOptions", "RenderResult", "PreflightError", "make_poster", "preflight",
           "simulate"]
