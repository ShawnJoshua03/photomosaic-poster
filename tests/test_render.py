import re
import struct

import numpy as np
import pytest
from PIL import Image

from mosaic_poster import PosterOptions, make_poster
from mosaic_poster.cli import main
from mosaic_poster.render import auto_cols


def _opts(target, photos, tmp_path, **kw):
    base = dict(target=str(target), tile_dirs=[str(photos)], width_in=6, height_in=9,
                dpi=40, cols=12, cache_dir=str(tmp_path / "cache"))
    base.update(kw)
    return PosterOptions(**base)


def test_png_is_exact_print_size_and_full_bleed(target, photos, tmp_path):
    out = tmp_path / "p.png"
    make_poster(_opts(target, photos, tmp_path, output=str(out), width_in=6.3, height_in=9.1))
    im = Image.open(out)
    assert im.size == (round(6.3 * 40), round(9.1 * 40))
    assert round(im.info["dpi"][0]) == 40
    a = np.asarray(im)
    for edge in (a[0], a[-1], a[:, 0], a[:, -1]):  # tiles reach every edge
        assert edge.std() > 5


def test_banner(target, photos, tmp_path):
    out = tmp_path / "b.png"
    make_poster(_opts(target, photos, tmp_path, output=str(out), text="HAPPY BIRTHDAY",
                      text_height_in=1.5, bg=(0, 0, 0), fg=(255, 255, 255)))
    a = np.asarray(Image.open(out))
    band = a[-60:]
    assert (band.max(axis=2) < 10).mean() > 0.5   # mostly banner color
    assert (band.min(axis=2) > 245).any()          # some white text


def test_cmyk_jpeg_is_standard_adobe_cmyk(target, photos, tmp_path):
    out = tmp_path / "c.jpg"
    make_poster(_opts(target, photos, tmp_path, output=str(out), cmyk=True))
    im = Image.open(out)
    assert im.mode == "CMYK" and im.info["dpi"] == (40, 40)
    data = out.read_bytes()[:200]
    assert b"Adobe" in data  # marks the inverted-CMYK convention print software expects


def test_cmyk_pdf_has_print_sized_page(target, photos, tmp_path):
    out = tmp_path / "c.pdf"
    make_poster(_opts(target, photos, tmp_path, output=str(out), cmyk=True))
    pdf = out.read_bytes()
    box = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf)
    assert (float(box[1]), float(box[2])) == (6 * 72, 9 * 72)
    assert b"/DeviceCMYK" in pdf and b"/Decode [ 1 0 1 0 1 0 1 0 ]" in pdf


def test_max_mb_is_respected(target, photos, tmp_path):
    out = tmp_path / "s.jpg"
    make_poster(_opts(target, photos, tmp_path, output=str(out), dpi=100, max_mb=0.15,
                      jpeg_quality=95))
    assert out.stat().st_size <= 0.15e6


def test_plain_jpeg_is_baseline(target, photos, tmp_path):
    out = tmp_path / "plain.jpg"
    make_poster(_opts(target, photos, tmp_path, output=str(out), optimize=False))
    d = out.read_bytes()
    i, markers = 2, []
    while d[i] == 0xFF:
        m = d[i + 1]
        markers.append(m)
        if m == 0xDA:
            break
        i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    assert 0xC0 in markers and 0xC2 not in markers  # baseline, not progressive


def test_panels_split_with_overlap(target, photos, tmp_path):
    out = tmp_path / "long.png"
    opt = _opts(target, photos, tmp_path, output=str(out), panels=3, overlap_in=0.5)
    files = make_poster(opt)
    assert [f.name for f in files] == [f"long_part{i}of3.png" for i in (1, 2, 3)]
    heights = [Image.open(f).height for f in files]
    assert sum(heights) == 9 * 40 + 2 * 20  # whole poster plus two overlaps
    assert all(Image.open(f).width == 6 * 40 for f in files)


def test_png_cannot_be_cmyk(target, photos, tmp_path):
    with pytest.raises(ValueError):
        make_poster(_opts(target, photos, tmp_path, output=str(tmp_path / "x.png"), cmyk=True))


def test_auto_cols():
    assert auto_cols(36, 54, 3000) == 72          # plenty of photos: ~0.5 inch tiles
    assert auto_cols(36, 54, 100) < 20            # few photos: fewer, bigger tiles
    assert auto_cols(36, 54, 1) == 8              # never absurdly coarse


def test_cli_end_to_end(target, photos, tmp_path):
    out = tmp_path / "cli.jpg"
    main([str(target), str(photos), "-o", str(out), "--size", "4x6", "--dpi", "30",
          "--cache-dir", str(tmp_path / "cc"), "-q"])
    assert Image.open(out).size == (120, 180)
