"""Color math: Lab conversion for matching, and the print-finishing step."""
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

log = logging.getLogger("mosaic_poster")

LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

# Common places a CMYK ICC profile already lives on each OS.
_CMYK_PROFILE_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "System32/spool/drivers/color/RSWOP.icm"),
    "/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc",
    "/Library/Application Support/Adobe/Color/Profiles/Recommended/USWebCoatedSWOP.icc",
    "/usr/share/color/icc/ghostscript/default_cmyk.icc",
    "/usr/share/color/icc/colord/FOGRA39L_coated.icc",
]


def srgb_to_lab(rgb):
    """rgb: (..., 3) values in 0-255 -> CIE Lab (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = (c @ m.T) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def find_cmyk_profile():
    """Return the path of a CMYK ICC profile installed on this machine, or None."""
    for p in _CMYK_PROFILE_CANDIDATES:
        if Path(p).is_file():
            return p
    return None


def make_finisher(brightness=1.0, contrast=1.0, saturation=1.0, gray_mean=128.0,
                  cmyk=False, cmyk_profile=None):
    """Return f(RGB image) -> image with print tweaks applied and, optionally, in CMYK.

    Everything here is per-pixel, so the poster can be finished one strip at a time and
    the strips still match. gray_mean is the whole poster's mean brightness (after the
    brightness tweak); it is the pivot for contrast, as in PIL.ImageEnhance.Contrast.
    """
    transform = None
    if cmyk:
        if cmyk_profile:
            transform = ImageCms.buildTransform(
                ImageCms.createProfile("sRGB"), ImageCms.getOpenProfile(cmyk_profile),
                "RGB", "CMYK", renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
        else:
            log.warning("No CMYK ICC profile found; using a basic RGB->CMYK conversion. "
                        "Pass --cmyk-profile for print-accurate color.")
    tweak = (brightness, contrast, saturation) != (1.0, 1.0, 1.0)

    def finish(img):
        if tweak:
            a = np.asarray(img, dtype=np.float32) * brightness
            a = gray_mean + contrast * (a - gray_mean)
            gray = (a @ LUMA)[..., None]
            a = gray + saturation * (a - gray)
            img = Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))
        if transform:
            return ImageCms.applyTransform(img, transform)
        return img.convert("CMYK") if cmyk else img

    return finish
