"""Command-line entry point: `mosaic-poster TARGET PHOTO_DIR [PHOTO_DIR ...] -o poster.png`."""
import argparse
import logging
import sys

from . import __version__
from .render import PosterOptions, make_poster


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


def build_parser():
    ap = argparse.ArgumentParser(
        prog="mosaic-poster",
        description="Make a printable photo mosaic poster: one big picture built from "
                    "hundreds or thousands of smaller photos.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("target", help="the big picture (e.g. a photo of the birthday person)")
    ap.add_argument("tile_dirs", nargs="+", metavar="PHOTO_DIR",
                    help="folders of photos to build it from (searched recursively; "
                         "JPEG, PNG, HEIC, WebP, TIFF)")
    ap.add_argument("-o", "--output", default="mosaic_poster.png",
                    help="output file: .png, .jpg, .pdf or .tif")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    g = ap.add_argument_group("size and grid")
    g.add_argument("--size", type=_size, default=(24.0, 36.0),
                   help="print size in inches, WIDTHxHEIGHT")
    g.add_argument("--dpi", type=float, default=150, help="print resolution")
    g.add_argument("--cols", type=int, default=0,
                   help="tiles across; 0 = pick from the print size and number of photos")

    g = ap.add_argument_group("look")
    g.add_argument("--tint", type=float, default=0.5,
                   help="0-1: how far each photo's color is pulled toward its spot in the "
                        "picture (higher = clearer picture, less natural photos)")
    g.add_argument("--overlay", type=float, default=0.3,
                   help="0-1: faint sharp copy of the target over the top for crisp "
                        "features (higher = sharper face, less visible photos)")
    g.add_argument("--crop", type=_crop, help="crop the target first: left,top,right,bottom "
                                              "as fractions, e.g. 0.1,0.15,0.9,0.75")
    g.add_argument("--focus-y", type=float, default=0.4,
                   help="where to center the target when it's cropped to the poster shape "
                        "(0 = top, 1 = bottom)")
    g.add_argument("--gamma", type=float, default=1.0,
                   help="brighten a dark target photo (<1 brightens; try 0.7)")
    g.add_argument("--autolevel", type=float, default=0.0,
                   help="stretch the target's contrast, clipping this percent at each end")
    g.add_argument("--save-target", metavar="FILE", default="",
                   help="also save the prepared target, to check the crop")

    g = ap.add_argument_group("photo choice")
    g.add_argument("--max-repeats", type=int, default=0,
                   help="most times one photo may appear; 0 = automatic")
    g.add_argument("--spacing", type=int, default=5,
                   help="a photo (or a look-alike) can't repeat within this many tiles")
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

    g = ap.add_argument_group("printing")
    g.add_argument("--brightness", type=float, default=1.0,
                   help="final tweak; uncoated/bond paper prints dark, try 1.05")
    g.add_argument("--contrast", type=float, default=1.0, help="final tweak; try 1.1 for bond")
    g.add_argument("--saturation", type=float, default=1.0,
                   help="final tweak; try 1.15 for bond")
    g.add_argument("--cmyk", action="store_true",
                   help="CMYK output for print shops that ask for it (.jpg, .pdf or .tif)")
    g.add_argument("--cmyk-profile", metavar="ICC",
                   help="CMYK ICC profile; default: one already installed on this computer")
    g.add_argument("--no-icc", action="store_true", help="don't embed the ICC profile")
    g.add_argument("--quality", type=int, default=90, help="JPEG/PDF quality (max when --max-mb)")
    g.add_argument("--max-mb", type=float, default=0,
                   help="JPEG/PDF: use the highest quality that fits under this many MB")
    g.add_argument("--no-optimize", action="store_true",
                   help="plainest possible JPEG encoding, for picky printer firmware")
    g.add_argument("--panels", type=int, default=1,
                   help="split the poster into this many horizontal pieces (files)")
    g.add_argument("--overlap", type=float, default=0.0,
                   help="inches of overlap between panels, for trimming and joining")

    g = ap.add_argument_group("other")
    g.add_argument("--cache-dir", default=".mosaic-cache",
                   help="where decoded photos are cached so re-renders are fast")
    g.add_argument("--no-cache", action="store_true", help="don't cache decoded photos")
    g.add_argument("-q", "--quiet", action="store_true", help="only print warnings")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    opt = PosterOptions(
        target=args.target, tile_dirs=args.tile_dirs, output=args.output,
        width_in=args.size[0], height_in=args.size[1], dpi=args.dpi, cols=args.cols,
        tint=args.tint, overlay=args.overlay, crop=args.crop, focus_y=args.focus_y,
        gamma=args.gamma, autolevel=args.autolevel, save_target=args.save_target,
        max_repeats=args.max_repeats, spacing=args.spacing, variety=args.variety,
        use_all=not args.allow_unused, seed=args.seed,
        text=args.text, text_height_in=args.text_height, bg=args.bg, fg=args.fg,
        brightness=args.brightness, contrast=args.contrast, saturation=args.saturation,
        cmyk=args.cmyk, cmyk_profile=args.cmyk_profile, embed_icc=not args.no_icc,
        jpeg_quality=args.quality, max_mb=args.max_mb, optimize=not args.no_optimize,
        panels=args.panels, overlap_in=args.overlap,
        cache_dir="" if args.no_cache else args.cache_dir)
    try:
        make_poster(opt)
    except ValueError as e:
        build_parser().error(str(e))


if __name__ == "__main__":
    main()
