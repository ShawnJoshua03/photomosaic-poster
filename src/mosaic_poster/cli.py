"""The `mosaic-poster` command.

    mosaic-poster TARGET PHOTOS... [options]     make a poster (same as `make`)
    mosaic-poster check TARGET PHOTOS...         check printer rules and get advice, no render
    mosaic-poster compare A.jpg B.jpg --photos PHOTOS...   which target photo works best
    mosaic-poster collect [FOLDER]               upload page for friends' photos
    mosaic-poster proof FILE --printer ...       preview an existing file as printed
    mosaic-poster printers                       list printer and paper presets
"""
import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .printers import PAPERS, PRINTERS, describe
from .render import PosterOptions, PreflightError, make_poster, preflight

COMMANDS = ("make", "check", "compare", "collect", "proof", "printers")


def _color(s):
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("color must be hex like 111111 or #ffffff")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _size(s):
    try:
        w, h = (float(v) for v in s.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("size must look like 24x36 (inches, width x height)")
    return w, h


def _crop(s):
    try:
        box = tuple(float(v) for v in s.split(","))
    except ValueError:
        box = ()
    if len(box) != 4 or not all(0 <= v <= 1 for v in box) or box[0] >= box[2] or box[1] >= box[3]:
        raise argparse.ArgumentTypeError("crop must be left,top,right,bottom fractions, "
                                         "e.g. 0.1,0.2,0.9,0.8")
    return box


def _poster_args(ap):
    ap.add_argument("target", help="the big picture (e.g. a photo of the birthday person); "
                                   "any image format, including HEIC and camera RAW")
    ap.add_argument("tile_dirs", nargs="+", metavar="PHOTOS",
                    help="folders, photos or .zip files to build it from (searched "
                         "recursively)")
    ap.add_argument("-o", "--output", help="output file: .pdf, .jpg, .png, .tif or .webp "
                                           "(default: what the printer prefers, else .png)")

    g = ap.add_argument_group("printer and paper")
    g.add_argument("--printer", choices=sorted(PRINTERS),
                   help="apply a printer preset: its file rules, DPI, color mode and paper "
                        "(see `mosaic-poster printers`)")
    g.add_argument("--paper", choices=sorted(PAPERS),
                   help="paper to preview and compensate for (default: the printer's)")
    g.add_argument("--printer-profile", metavar="ICC",
                   help="the print shop's ICC profile, for an exact preview")
    g.add_argument("--force", action="store_true", help="render even if a printer rule is broken")

    g = ap.add_argument_group("size and grid")
    g.add_argument("--size", type=_size, default=(24.0, 36.0),
                   help="print size in inches, WIDTHxHEIGHT (default 24x36)")
    g.add_argument("--dpi", type=float, help="print resolution (default: printer's, else 150)")
    g.add_argument("--cols", type=int, default=0,
                   help="tiles across; 0 = pick from the print size and number of photos")

    g = ap.add_argument_group("look")
    g.add_argument("--tint", type=float, default=0.5,
                   help="0-1: pull each photo's color toward its spot in the picture")
    g.add_argument("--overlay", type=float, default=0.3,
                   help="0-1: faint sharp copy of the target on top, for crisp features")
    g.add_argument("--crop", type=_crop, help="crop the target: left,top,right,bottom fractions")
    g.add_argument("--focus-y", type=float, default=0.4,
                   help="where to center the target when cropping it to the poster shape")
    g.add_argument("--gamma", type=float, default=1.0, help="brighten a dark target (try 0.7)")
    g.add_argument("--autolevel", type=float, default=0.0,
                   help="stretch the target's contrast, clipping this percent at each end")
    g.add_argument("--save-target", metavar="FILE", default="",
                   help="also save the prepared target, to check the crop")

    g = ap.add_argument_group("photo choice")
    g.add_argument("--include-videos", action="store_true",
                   help="use a frame from each video too (needs: pip install av)")
    g.add_argument("--max-repeats", type=int, default=0, help="most uses of one photo; 0 = auto")
    g.add_argument("--spacing", type=int, default=5,
                   help="a photo (or look-alike) can't repeat within this many tiles")
    g.add_argument("--variety", type=int, default=16,
                   help="pick randomly among this many near-best photos per tile")
    g.add_argument("--allow-unused", action="store_true",
                   help="don't force every distinct photo onto the poster at least once")
    g.add_argument("--seed", type=int, default=1, help="change to reshuffle the layout")

    g = ap.add_argument_group("banner text (optional)")
    g.add_argument("--text", default="", help='e.g. "HAPPY BIRTHDAY SAM"')
    g.add_argument("--text-height", type=float, default=3.0, help="banner height in inches")
    g.add_argument("--bg", type=_color, default=_color("111111"), help="banner color")
    g.add_argument("--fg", type=_color, default=_color("ffffff"), help="text color")

    g = ap.add_argument_group("color and files")
    g.add_argument("--brightness", type=float, help="final tweak (default: paper's)")
    g.add_argument("--contrast", type=float, help="final tweak (default: paper's)")
    g.add_argument("--saturation", type=float, help="final tweak (default: paper's)")
    cm = g.add_mutually_exclusive_group()
    cm.add_argument("--cmyk", action="store_true", help="CMYK file (default: printer's)")
    cm.add_argument("--rgb", action="store_true", help="RGB file, even if the printer says CMYK")
    g.add_argument("--cmyk-profile", metavar="ICC",
                   help="CMYK ICC profile; default: one installed on this computer")
    g.add_argument("--no-icc", action="store_true", help="don't embed the ICC profile")
    g.add_argument("--quality", type=int, default=90, help="JPEG/PDF quality (max with --max-mb)")
    g.add_argument("--max-mb", type=float,
                   help="JPEG/PDF/WebP: best quality under this many MB (default: printer's)")
    g.add_argument("--no-optimize", action="store_true",
                   help="plainest possible JPEG encoding, for picky printer firmware")
    g.add_argument("--panels", type=int, default=1,
                   help="split into this many horizontal pieces, for printers that stall")
    g.add_argument("--overlap", type=float, default=0.0,
                   help="inches of overlap between panels, for trimming and joining")
    g.add_argument("--test-strip", action="store_true",
                   help="also write a strip of the poster through the face to test-print")
    g.add_argument("--strip-height", type=float, default=3.0, help="test strip height, inches")
    g.add_argument("--fallbacks", action="store_true",
                   help="also write the same poster in other formats, in case the printer "
                        "rejects the first one")
    g.add_argument("--no-preview", action="store_true",
                   help="skip the HTML report with print previews")

    g = ap.add_argument_group("other")
    g.add_argument("--cache-dir", default=".mosaic-cache",
                   help="where decoded photos are cached so re-renders are fast")
    g.add_argument("--no-cache", action="store_true", help="don't cache decoded photos")
    g.add_argument("-q", "--quiet", action="store_true", help="only print warnings")


def options_from_args(args):
    """Merge: what the user typed > the printer/paper preset > built-in defaults."""
    printer = PRINTERS.get(args.printer) if args.printer else None
    paper = PAPERS.get(args.paper or (printer.paper if printer else ""), None)
    applied = []
    output = args.output
    if not output:
        output = f"poster.{printer.formats[0]}" if printer else "mosaic_poster.png"
        applied.append(f"output {output}")
    dpi = args.dpi or (printer.dpi if printer else 150)
    if not args.dpi and printer:
        applied.append(f"{dpi} DPI")
    cmyk = args.cmyk or (printer is not None and printer.color == "cmyk" and not args.rgb
                         and Path(output).suffix.lower() not in (".png", ".webp"))
    if cmyk and not args.cmyk:
        applied.append("CMYK")
    max_mb = args.max_mb
    if max_mb is None:
        max_mb = round(printer.max_mb * 0.99, 1) if printer and printer.max_mb else 0
        if max_mb:
            applied.append(f"files under {max_mb:g} MB")
    finish = {}
    if paper and all(v is None for v in (args.brightness, args.contrast, args.saturation)):
        finish = dict(paper.finish)
        if finish:
            applied.append(f"{paper.key} paper color compensation")
    if applied:
        logging.getLogger("mosaic_poster").info("Printer preset: " + ", ".join(applied))
    return PosterOptions(
        target=args.target, tile_dirs=args.tile_dirs, output=output,
        width_in=args.size[0], height_in=args.size[1], dpi=dpi, cols=args.cols,
        tint=args.tint, overlay=args.overlay, crop=args.crop, focus_y=args.focus_y,
        gamma=args.gamma, autolevel=args.autolevel, save_target=args.save_target,
        include_videos=args.include_videos, max_repeats=args.max_repeats,
        spacing=args.spacing, variety=args.variety, use_all=not args.allow_unused,
        seed=args.seed, text=args.text, text_height_in=args.text_height, bg=args.bg,
        fg=args.fg, printer=args.printer, paper=args.paper,
        printer_profile=args.printer_profile,
        brightness=args.brightness if args.brightness is not None else finish.get("brightness", 1.0),
        contrast=args.contrast if args.contrast is not None else finish.get("contrast", 1.0),
        saturation=args.saturation if args.saturation is not None else finish.get("saturation", 1.0),
        cmyk=cmyk, cmyk_profile=args.cmyk_profile, embed_icc=not args.no_icc,
        jpeg_quality=args.quality, max_mb=max_mb, optimize=not args.no_optimize,
        panels=args.panels, overlap_in=args.overlap, test_strip=args.test_strip,
        strip_height_in=args.strip_height, fallbacks=args.fallbacks,
        preview=not args.no_preview, force=args.force,
        cache_dir="" if args.no_cache else args.cache_dir)


def _setup_logging(quiet=False):
    logging.basicConfig(level=logging.WARNING if quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr, force=True)


def _print_findings(findings):
    for f in findings:
        print(f, file=sys.stderr)


def cmd_make(argv):
    ap = argparse.ArgumentParser(prog="mosaic-poster", description="Make a printable photo "
                                 "mosaic poster.", epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    _poster_args(ap)
    args = ap.parse_args(argv)
    _setup_logging(args.quiet)
    try:
        opt = options_from_args(args)
        result = make_poster(opt)
    except PreflightError as e:
        print("\nNot rendered - fix these first (or add --force):", file=sys.stderr)
        _print_findings([f for f in e.findings if f.level == "error"])
        return 2
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    print("\nRecommendations:", file=sys.stderr)
    _print_findings([f for f in result.findings if f.level != "ok"] or result.findings)
    print("\nFiles:", file=sys.stderr)
    for p, q, mb in result.files:
        print(f"  {p}  ({mb:.1f} MB{f', quality {q}' if q else ''})", file=sys.stderr)
    if result.report:
        print(f"\nOpen the print preview and checklist: {result.report}", file=sys.stderr)
    return 0


def cmd_check(argv):
    ap = argparse.ArgumentParser(prog="mosaic-poster check",
                                 description="Check a poster plan against the printer and get "
                                             "recommendations, without rendering.")
    _poster_args(ap)
    args = ap.parse_args(argv)
    _setup_logging(True)
    try:
        opt = options_from_args(args)
        plan, findings, _ = preflight(opt)
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    print(f"{plan.width_in:g} x {plan.height_in:g} in at {plan.dpi:g} DPI -> {plan.cols} x "
          f"{plan.rows} tiles of {plan.tile_in:.2f} in, {opt.output}"
          f"{' (CMYK)' if opt.cmyk else ''}\n")
    _print_findings(findings)
    return 2 if any(f.level == "error" for f in findings) else 0


def cmd_compare(argv):
    from .compare import compare_targets
    ap = argparse.ArgumentParser(prog="mosaic-poster compare",
                                 description="Preview several candidate target photos as "
                                             "mosaics side by side, with a score for each.")
    ap.add_argument("targets", nargs="+", help="candidate photos")
    ap.add_argument("--photos", nargs="+", required=True, help="folders/zips of tile photos")
    ap.add_argument("--size", type=_size, default=(24.0, 36.0), help="poster size, WxH inches")
    ap.add_argument("-o", "--output", default="compare.jpg", help="contact sheet image")
    ap.add_argument("--sample", type=int, default=400, help="photos to sample for speed")
    args = ap.parse_args(argv)
    _setup_logging()
    ranked = compare_targets(args.targets, args.photos, args.output, *args.size,
                             sample=args.sample)
    print("\nBest first (scores can't see faces - check the previews):")
    for t, score, parts, stats in ranked:
        weak = [k for k, v in parts.items() if v < 0.6]
        print(f"  {score:3d}/100  {t}" + (f"   weaker on: {', '.join(weak)}" if weak else ""))
    print(f"\nSide by side: {args.output}")
    return 0


def cmd_collect(argv):
    from .collect import serve
    ap = argparse.ArgumentParser(prog="mosaic-poster collect",
                                 description="Run an upload page friends can open on their "
                                             "phones; photos land in FOLDER on this computer.")
    ap.add_argument("folder", nargs="?", default="collected_photos")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--title", default="Send your photos for the poster")
    ap.add_argument("--max-mb", type=float, default=500, help="largest single file accepted")
    ap.add_argument("--key", help="link key (default: random)")
    args = ap.parse_args(argv)
    serve(args.folder, args.port, args.title, args.key, args.max_mb)
    return 0


def cmd_proof(argv):
    from PIL import Image, ImageCms

    from .color import find_cmyk_profile
    from .proof import simulate
    ap = argparse.ArgumentParser(prog="mosaic-poster proof",
                                 description="Preview how an existing image file will look "
                                             "printed on a given paper.")
    ap.add_argument("file", help="the .jpg/.png/.tif you plan to print")
    ap.add_argument("--printer", choices=sorted(PRINTERS))
    ap.add_argument("--paper", choices=sorted(PAPERS))
    ap.add_argument("--printer-profile", metavar="ICC")
    ap.add_argument("--cmyk-profile", metavar="ICC", help="profile the CMYK file was made with")
    ap.add_argument("-o", "--output", help="preview image (default: FILE.proof.jpg)")
    args = ap.parse_args(argv)
    printer = PRINTERS.get(args.printer) if args.printer else None
    paper = PAPERS.get(args.paper or (printer.paper if printer else ""), None)
    if not (paper or args.printer_profile):
        ap.error("choose --printer, --paper or --printer-profile")
    im = Image.open(args.file)
    im.draft("RGB", (2000, 2000))
    if im.mode == "CMYK":
        prof = args.cmyk_profile or find_cmyk_profile()
        im = (ImageCms.applyTransform(im, ImageCms.buildTransform(
            ImageCms.getOpenProfile(prof), ImageCms.createProfile("sRGB"), "CMYK", "RGB"))
            if prof else im.convert("RGB"))
    im.thumbnail((1600, 1600))
    out = args.output or str(Path(args.file).with_suffix("")) + ".proof.jpg"
    simulate(im, paper, args.printer_profile).save(out, quality=90)
    print(f"Preview as printed{f' on {paper.name}' if paper else ''}: {out}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "printers":
        print(describe())
        return 0
    cmd = argv[0] if argv and argv[0] in COMMANDS else "make"
    if argv and argv[0] in COMMANDS:
        argv = argv[1:]
    return {"make": cmd_make, "check": cmd_check, "compare": cmd_compare,
            "collect": cmd_collect, "proof": cmd_proof}[cmd](argv)


if __name__ == "__main__":
    sys.exit(main())
