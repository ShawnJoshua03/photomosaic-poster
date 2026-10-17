"""Recommendations: checks against the printer's rules and advice on the poster itself.

Every lesson from making real posters lives here as a check with a concrete fix.
"""
from dataclasses import dataclass

from .plan import auto_cols

LEVELS = ("error", "warn", "tip", "ok")


@dataclass
class Finding:
    level: str      # "error" stops the render (unless --force); "warn", "tip", "ok"
    title: str
    detail: str = ""
    fix: str = ""   # command-line change that addresses it

    def __str__(self):
        mark = {"error": "X", "warn": "!", "tip": "*", "ok": "+"}[self.level]
        s = f"[{mark}] {self.title}"
        if self.detail:
            s += f"\n      {self.detail}"
        if self.fix:
            s += f"\n      fix: {self.fix}"
        return s


def _size(w, h):
    return f"{w:g}x{h:g}"


def advise(opt, plan, printer=None, paper=None, target=None, n_files=0, skipped=None,
           result=None):
    """All findings for this poster, most important first."""
    f = []
    ext = opt.output.rsplit(".", 1)[-1].lower().replace("jpeg", "jpg").replace("tiff", "tif")

    # ---- printer rules ---------------------------------------------------------------
    if printer:
        mw, mh = printer.max_width_in, printer.max_height_in
        if mw and plan.width_in > mw:
            if plan.height_in <= mw and (not mh or plan.width_in <= mh):
                f.append(Finding("error", f"{plan.width_in:g} in is wider than this printer's "
                                 f"{mw:g} in maximum",
                                 "Rotate the poster: the same picture fits the other way round.",
                                 f"--size {_size(plan.height_in, plan.width_in)}"))
            else:
                h = round(plan.height_in * mw / plan.width_in, 1)
                f.append(Finding("error", f"{plan.width_in:g} in is wider than this printer's "
                                 f"{mw:g} in maximum", "Scale the poster down to fit.",
                                 f"--size {_size(mw, h)}"))
        if mh and plan.height_in > mh and not (mw and plan.width_in > mw):
            f.append(Finding("error", f"{plan.height_in:g} in is taller than this printer's "
                             f"{mh:g} in maximum", "Print a section with --test-strip, or "
                             "split the poster.", f"--panels {int(-(-plan.height_in // mh))}"))
        if ext not in printer.formats:
            f.append(Finding("error", f".{ext} files aren't accepted by this printer",
                             f"It takes: {', '.join(printer.formats).upper()}.",
                             f"-o poster.{printer.formats[0]}"))
        if printer.color == "cmyk" and not opt.cmyk:
            f.append(Finding("warn", "This printer asks for CMYK files",
                             "RGB often works too, but follow the shop's rule unless it fails.",
                             "--cmyk"))
        if printer.color == "rgb" and opt.cmyk:
            f.append(Finding("warn", "This printer expects RGB, not CMYK",
                             "CMYK files can print dull or with shifted colors at photo labs.",
                             "drop --cmyk"))
        if opt.cmyk and ext == "jpg" and not printer.cmyk_jpeg_ok:
            f.append(Finding("warn", "CMYK JPEGs are often rejected when printing from USB",
                             "On HP DesignJets this shows as 'File contains format errors' "
                             "(61:08.2). The same picture as a CMYK PDF prints fine.",
                             "-o poster.pdf"))
        if plan.dpi < printer.dpi:
            f.append(Finding("warn", f"{plan.dpi:g} DPI is below the {printer.dpi} DPI this "
                             "printer wants", fix=f"--dpi {printer.dpi}"))
        if printer.max_mb and not opt.max_mb and ext in ("jpg", "pdf"):
            f.append(Finding("warn", f"Files must be under {printer.max_mb:g} MB",
                             fix=f"--max-mb {printer.max_mb * 0.99:.1f}"))
        if printer.max_mb and ext == "tif":
            raw_mb = plan.W * plan.H * (4 if opt.cmyk else 3) / 1e6
            if raw_mb * 0.6 > printer.max_mb:
                f.append(Finding("warn", "A TIFF this size will be far over the file-size limit",
                                 f"~{raw_mb:.0f} MB uncompressed.", "-o poster.pdf"))
        if printer.edge_margin_in:
            f.append(Finding("tip", f"The outer {printer.edge_margin_in:g} in may not print "
                             "(or wraps around the frame)",
                             "Keep the face away from the edges; background tiles there are fine."))

    # ---- the photos --------------------------------------------------------------------
    if n_files == 0:
        f.append(Finding("error", "No photos found",
                         "Check the folder paths. Folders, single files and .zip files all work."))
    else:
        uses = plan.cells / n_files
        if uses > 5:
            better = auto_cols(plan.width_in, plan.mosaic_h / plan.dpi, n_files)
            f.append(Finding("warn", f"Each photo would appear ~{uses:.1f} times",
                             "Above about 4-5 uses the repeats are easy to spot.",
                             f"--cols {better}  (or collect more photos: mosaic-poster collect)"))
        else:
            f.append(Finding("ok", f"{n_files} photos for {plan.cells} tiles "
                             f"(~{uses:.1f} uses each)"))
    if plan.tile_in < 0.3:
        f.append(Finding("warn", f"Tiles are only {plan.tile_in:.2f} in across",
                         "People won't be able to recognise the photos in them.",
                         f"--cols {max(8, round(plan.width_in / 0.5))}"))
    elif plan.tile_in > 1.2:
        f.append(Finding("tip", f"Tiles are {plan.tile_in:.2f} in across",
                         "The photos are easy to see, but the big picture will look blocky; "
                         "raise --overlay or add columns if the face is hard to read."))
    for reason, count in sorted((skipped or {}).items()):
        if "rawpy" in reason or "av)" in reason or "--include-videos" in reason:
            f.append(Finding("tip", f"{count} file(s) skipped: {reason}",
                             "Install the extra decoder or flag to include them."))
        elif reason in ("unreadable or damaged", "damaged zip"):
            f.append(Finding("warn", f"{count} file(s) couldn't be read ({reason})",
                             "Re-download or re-export them."))

    # ---- the target photo ------------------------------------------------------------
    if target:
        if target.ppi < 30:
            f.append(Finding("warn", f"The target photo is only {target.width} px wide for "
                             f"{plan.width_in:g} in", "Fine detail (eyes, hair) will look soft. "
                             "Use the original from the phone or camera, not one sent through "
                             "a chat app, or lower --overlay so the tiles carry the picture."))
        if target.brightness < 85:
            f.append(Finding("tip", "The target photo is dark",
                             "Dark areas get dark photos, which repeat more and look muddy.",
                             "--gamma 0.7"))
        if target.contrast < 35:
            f.append(Finding("tip", "The target photo is low-contrast",
                             "Strong light and dark shapes read best from a distance.",
                             "--autolevel 1"))
        if target.sharpness < 6:
            f.append(Finding("tip", "The target photo looks soft or blurry",
                             "A sharper photo makes a crisper poster."))
        if target.crop_loss > 0.25:
            portrait_t = target.height > target.width
            portrait_p = plan.height_in > plan.width_in
            detail = f"About {target.crop_loss:.0%} of the photo is cut off to fit."
            fix = "--crop / --focus-y to choose what's kept"
            if portrait_t != portrait_p:
                detail += " The photo and poster face different ways."
                fix = f"--size {_size(plan.height_in, plan.width_in)}  (or {fix})"
            f.append(Finding("tip", "The poster shape doesn't match the photo", detail, fix))

    # ---- paper and output ------------------------------------------------------------
    if paper and paper.finish and (opt.brightness, opt.contrast, opt.saturation) == (1, 1, 1):
        tweak = " ".join(f"--{k} {v:g}" for k, v in paper.finish.items())
        f.append(Finding("tip", f"{paper.name}: pre-compensate the color", paper.notes, tweak))
    if plan.megapixels > 120:
        f.append(Finding("tip", f"Big job: {plan.megapixels:.0f} megapixels",
                         "Print a test strip first to check the file is accepted and the "
                         "colors and tiles look right; if a printer stops partway, split it.",
                         "--test-strip   /   --panels 2 --overlap 0.5"))
    if result:
        for path, q, mb in result.files:
            if q is not None and q < 60:
                f.append(Finding("tip", f"{path.name} needed JPEG quality {q} to fit the "
                                 "size limit", "Fine on most paper. For more headroom split it "
                                 "(each part gets the full limit) or use RGB, which compresses "
                                 "far better than CMYK.", "--panels 2"))
        if result.gamut_pct is not None and result.gamut_pct > 15:
            f.append(Finding("tip", f"{result.gamut_pct:.0f}% of the picture changes color "
                             "noticeably in print", "Vivid blues, greens and neon colors can't "
                             "be printed exactly; compare the 'on paper' and 'on screen' previews."))
        f.append(Finding("ok", f"{result.n_distinct} distinct photos used; most-used photo "
                         f"appears {result.max_uses}x"))

    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    return sorted(f, key=lambda x: order[x.level])


PRINT_CHECKLIST = [
    "Print at 100% scale with 'fit to page' off, so the poster is its true size.",
    "Choose Best / high quality, not Normal: the small photos are the point.",
    "Check the printer's preview shows the whole poster, upright.",
    "Send one file at a time.",
    "Let ink dry before rolling; uncoated paper smudges in dark areas.",
]
