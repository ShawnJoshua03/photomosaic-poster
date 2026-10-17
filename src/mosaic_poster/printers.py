"""Printer and paper presets: file rules, color behaviour and finishing tweaks.

Paper numbers are typical values used to *approximate* how a print will look (paper
white, deepest black, dot gain, color range). For an exact preview, pass the printer
or paper ICC profile your print shop publishes (--printer-profile).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paper:
    key: str
    name: str
    white: tuple          # color of blank paper (sRGB)
    black: tuple          # deepest black the paper can hold (sRGB)
    dot_gain: float       # >1 darkens midtones (ink spreads into the paper)
    saturation: float     # <1: the paper can't show colors as vivid as a screen
    spread_in: float      # how far ink bleeds, in inches (softens fine detail)
    finish: dict          # brightness/contrast/saturation that pre-compensate
    notes: str = ""


PAPERS = {p.key: p for p in [
    Paper("glossy", "Glossy photo paper", (250, 250, 248), (14, 14, 16), 1.0, 1.0, 0.0015,
          {}, "Most detail and the deepest blacks. Shows glare under room lights."),
    Paper("luster", "Luster / satin / semi-gloss photo paper", (248, 247, 244), (20, 20, 22),
          1.02, 0.97, 0.002, {"saturation": 1.03},
          "The usual photo-lab poster paper: rich color, little glare."),
    Paper("matte", "Matte poster / photo paper", (246, 245, 241), (34, 33, 35), 1.05, 0.9,
          0.003, {"contrast": 1.05, "saturation": 1.07},
          "No glare; blacks are softer, so a little extra contrast helps."),
    Paper("bond", "Uncoated bond / plotter paper", (243, 242, 236), (58, 56, 58), 1.15, 0.78,
          0.006, {"brightness": 1.05, "contrast": 1.1, "saturation": 1.15},
          "Cheap and huge, but it soaks up ink: prints come out darker, flatter and a "
          "little soft. Pre-brightening and boosting contrast compensates."),
    Paper("canvas", "Canvas", (238, 234, 224), (42, 40, 40), 1.08, 0.88, 0.004,
          {"contrast": 1.05, "saturation": 1.08},
          "Warm white and a woven texture that hides fine detail; prefer bigger tiles."),
    Paper("plain", "Plain office paper", (244, 244, 240), (52, 52, 54), 1.12, 0.8, 0.005,
          {"brightness": 1.04, "contrast": 1.08, "saturation": 1.12},
          "Fine for test prints of a section; not for the real poster."),
]}


@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    paper: str
    dpi: int                       # what to send
    formats: tuple                 # accepted file types, best first
    color: str = "rgb"             # "rgb", "cmyk" or "either"
    max_width_in: float = 0        # 0 = no limit known
    max_height_in: float = 0
    max_mb: float = 0              # 0 = no limit known
    edge_margin_in: float = 0.0    # area the machine can't print
    cmyk_jpeg_ok: bool = True      # some printers' USB readers reject CMYK JPEGs
    notes: tuple = field(default_factory=tuple)


PRINTERS = {p.key: p for p in [
    Printer(
        "plotter-bond", "Wide-format plotter on bond paper (e.g. HP DesignJet, 36-inch roll)",
        paper="bond", dpi=300, formats=("pdf", "tif", "jpg"), color="cmyk",
        max_width_in=36, max_mb=75, edge_margin_in=0.2, cmyk_jpeg_ok=False,
        notes=("Width is limited by the roll, but length can be almost anything: a 36-inch "
               "roll prints 36x54 happily.",
               "Printing straight from USB: some plotters reject CMYK JPEGs with "
               "'File contains format errors' (HP 61:08.2). A CMYK PDF works.",
               "If the printer stops partway through a long print, use --panels 2.",
               "Set print quality to Best; Normal visibly blurs the small photos.")),
    Printer(
        "photo-lab", "Photo lab poster (online or in-store, luster or glossy)",
        paper="luster", dpi=300, formats=("jpg",), color="rgb",
        notes=("Labs expect an sRGB JPEG; don't send CMYK.",
               "Upload limits vary (often 25-100 MB); set --max-mb to your lab's limit.",
               "Order the exact size you rendered so nothing gets cropped.")),
    Printer(
        "print-shop", "Print shop large-format poster (matte or satin, inkjet)",
        paper="matte", dpi=300, formats=("pdf", "tif", "jpg"), color="either",
        edge_margin_in=0.125,
        notes=("Ask whether they want RGB or CMYK and if they have an ICC profile for "
               "the paper; pass it with --printer-profile for an exact preview.",)),
    Printer(
        "canvas", "Canvas print service", paper="canvas", dpi=200, formats=("jpg", "tif"),
        color="rgb", edge_margin_in=1.5,
        notes=("Gallery wraps fold about 1.5 inches around the frame: nothing important "
               "near the edges.",)),
    Printer(
        "office-inkjet", "Home or office inkjet (letter / A4) - test prints",
        paper="plain", dpi=300, formats=("pdf", "png", "jpg"), color="rgb",
        max_width_in=8.5, max_height_in=14, edge_margin_in=0.25,
        notes=("Use --test-strip to print a slice of the real poster and check tile size "
               "and color before paying for the big print.",)),
]}


def describe():
    """Text listing of the presets, for `mosaic-poster printers`."""
    lines = ["Printers (--printer):"]
    for p in PRINTERS.values():
        lim = []
        if p.max_width_in:
            lim.append(f"max width {p.max_width_in:g} in")
        if p.max_mb:
            lim.append(f"files under {p.max_mb:g} MB")
        lines.append(f"  {p.key:14s} {p.name}")
        lines.append(f"  {'':14s} paper: {p.paper}; send {', '.join(p.formats).upper()} "
                     f"{p.color.upper()} at {p.dpi} DPI" + (f"; {'; '.join(lim)}" if lim else ""))
    lines.append("")
    lines.append("Papers (--paper, to override the printer's):")
    for p in PAPERS.values():
        lines.append(f"  {p.key:14s} {p.name}")
    return "\n".join(lines)
