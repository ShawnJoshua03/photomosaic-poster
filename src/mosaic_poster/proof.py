"""Print previews: what the poster will look like on a given paper and printer.

Two levels of accuracy:
* With an ICC profile for the printer + paper (most print shops publish them), the
  preview is an ICC soft proof, the same technique Photoshop's "Proof Colors" uses.
* Without one, a paper model approximates it: paper white instead of pure white, the
  paper's deepest black, darker midtones from ink spreading (dot gain), less vivid
  color, and slight softening of fine detail.
If the file is CMYK, colors are also round-tripped through the CMYK profile, so colors
that CMYK can't hold show up the way they will print.
"""
import numpy as np
from PIL import Image, ImageCms, ImageFilter

from .color import LUMA, srgb_to_lab

DISPLAY_PPI = 96  # "actual size" previews assume a typical monitor


def _srgb():
    return ImageCms.createProfile("sRGB")


def cmyk_roundtrip(img, cmyk_profile):
    """sRGB -> CMYK -> sRGB: what a CMYK file can actually hold."""
    prof = ImageCms.getOpenProfile(cmyk_profile)
    to = ImageCms.buildTransform(_srgb(), prof, "RGB", "CMYK",
                                 renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                 flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    back = ImageCms.buildTransform(prof, _srgb(), "CMYK", "RGB",
                                   renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
    return ImageCms.applyTransform(ImageCms.applyTransform(img, to), back)


def simulate(img, paper=None, proof_profile=None, cmyk_profile=None, ppi=None):
    """Return an sRGB image approximating `img` printed on `paper`.

    ppi: how many preview pixels per printed inch, used to scale ink spread.
    """
    img = img.convert("RGB")
    if cmyk_profile:
        img = cmyk_roundtrip(img, cmyk_profile)
    if proof_profile:
        t = ImageCms.buildProofTransform(
            _srgb(), _srgb(), ImageCms.getOpenProfile(proof_profile), "RGB", "RGB",
            renderingIntent=ImageCms.Intent.PERCEPTUAL,
            proofRenderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC,  # shows paper white
            flags=ImageCms.Flags.SOFTPROOFING)
        img = ImageCms.applyTransform(img, t)
    elif paper is not None:
        a = np.asarray(img, dtype=np.float32) / 255.0
        gray = (a @ LUMA)[..., None]
        a = np.clip(gray + paper.saturation * (a - gray), 0, 1) ** paper.dot_gain
        white, black = np.array(paper.white, np.float32), np.array(paper.black, np.float32)
        img = Image.fromarray(np.clip(black + a * (white - black) + 0.5, 0, 255).astype(np.uint8))
    if paper is not None and ppi and paper.spread_in * ppi >= 0.3:
        img = img.filter(ImageFilter.GaussianBlur(paper.spread_in * ppi))
    return img


def gamut_loss(img, paper=None, proof_profile=None, cmyk_profile=None):
    """Percent of the picture whose color visibly changes in print (delta-E > 6).

    Only meaningful when a CMYK or printer profile is involved; returns None otherwise.
    """
    if not (cmyk_profile or proof_profile):
        return None
    small = img.convert("RGB").resize((200, int(200 * img.height / img.width)))
    before = srgb_to_lab(np.asarray(small, dtype=np.float64))
    after_img = small
    if cmyk_profile:
        after_img = cmyk_roundtrip(after_img, cmyk_profile)
    if proof_profile:
        # Relative intent: ignore the paper's tint, count only colors it can't reach.
        t = ImageCms.buildProofTransform(
            _srgb(), _srgb(), ImageCms.getOpenProfile(proof_profile), "RGB", "RGB",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            proofRenderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            flags=ImageCms.Flags.SOFTPROOFING)
        after_img = ImageCms.applyTransform(after_img, t)
    after = srgb_to_lab(np.asarray(after_img, dtype=np.float64))
    de = np.sqrt(((before - after) ** 2).sum(axis=-1))
    return float((de > 6).mean() * 100)


def make_previews(poster, poster_in, focus, paper=None, proof_profile=None, cmyk_profile=None):
    """Build the preview set from the finished RGB poster.

    poster: the full-resolution RGB poster; poster_in: (width, height) in inches;
    focus: (x, y) fractions of the most detailed area (usually the face).
    Returns {name: (title, caption, image)} in display order.
    """
    W, H = poster.size
    dpi = W / poster_in[0]
    fit = min(1400 / H, 1100 / W, 1.0)
    screen = poster.resize((max(1, round(W * fit)), max(1, round(H * fit))), Image.LANCZOS)
    print_ppi = screen.width / poster_in[0]
    out = {
        "printed": ("On paper, from across the room",
                    "The whole poster as it should look printed.",
                    simulate(screen, paper, proof_profile, cmyk_profile, print_ppi)),
        "screen": ("On screen", "The same file on a monitor, before printing.", screen),
    }

    def crop(w_in, h_in):
        cw, ch = min(W, round(w_in * dpi)), min(H, round(h_in * dpi))
        x = min(max(0, round(focus[0] * W - cw / 2)), W - cw)
        y = min(max(0, round(focus[1] * H - ch / 2)), H - ch)
        return poster.crop((x, y, x + cw, y + ch))

    actual = crop(6, 4).resize((6 * DISPLAY_PPI, 4 * DISPLAY_PPI), Image.LANCZOS)
    out["actual"] = ("Up close, actual size",
                     "A 6 x 4 inch patch at about real size on a typical monitor: this is "
                     "what someone standing at the poster sees.",
                     simulate(actual, paper, proof_profile, cmyk_profile, DISPLAY_PPI))
    zoom = crop(2, 4 / 3).resize((6 * DISPLAY_PPI, 4 * DISPLAY_PPI), Image.LANCZOS)
    out["zoom"] = ("Magnified 3x",
                   "A 2 x 1.3 inch patch enlarged, to judge how sharp each photo prints.",
                   simulate(zoom, paper, proof_profile, cmyk_profile, DISPLAY_PPI * 3))
    return out


def detail_focus(base, prior_y=0.4):
    """(x, y) fractions of where the face most likely is, for the close-up previews.

    Combines detail (edges), skin-colored pixels (a YCbCr range that covers light to
    dark skin) and a mild preference for the upper middle, where portraits put faces.
    Busy backgrounds like surf or foliage have edges but no skin, so they lose out.
    """
    w = 96
    h = max(1, round(w * base.height / base.width))
    small = base.convert("RGB").resize((w, h))
    edges = np.asarray(small.convert("L").filter(ImageFilter.FIND_EDGES)
                       .filter(ImageFilter.BoxBlur(6)), dtype=np.float32)
    _, cb, cr = (np.asarray(c, dtype=np.float32) for c in small.convert("YCbCr").split())
    skin = ((cb > 77) & (cb < 127) & (cr > 133) & (cr < 173)).astype(np.uint8) * 255
    skin = np.asarray(Image.fromarray(skin).filter(ImageFilter.BoxBlur(6)), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    prior = np.exp(-(((xx / w - 0.5) / 0.35) ** 2 + ((yy / h - prior_y) / 0.35) ** 2))
    score = (edges / (edges.max() + 1e-6) + 0.3) * (skin / 255 + 0.15) * prior
    y, x = np.unravel_index(np.argmax(score), score.shape)
    return (x + 0.5) / w, (y + 0.5) / h
