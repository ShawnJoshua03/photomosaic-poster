import re
import struct

import numpy as np
import pytest
from PIL import Image

from mosaic_poster import PosterOptions, PreflightError, make_poster, preflight
from mosaic_poster.color import find_cmyk_profile
from mosaic_poster.plan import auto_cols


def _opts(target, photos, tmp_path, **kw):
    base = dict(target=str(target), tile_dirs=[str(photos)], width_in=6, height_in=9,
                dpi=40, cols=12, cache_dir=str(tmp_path / "cache"), preview=False)
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
    band = np.asarray(Image.open(out))[-60:]
    assert (band.max(axis=2) < 10).mean() > 0.5
    assert (band.min(axis=2) > 245).any()


def test_cmyk_jpeg_is_standard_adobe_cmyk(target, photos, tmp_path):
    out = tmp_path / "c.jpg"
    make_poster(_opts(target, photos, tmp_path, output=str(out), cmyk=True))
    im = Image.open(out)
    assert im.mode == "CMYK" and im.info["dpi"] == (40, 40)
    assert b"Adobe" in out.read_bytes()[:200]


def test_cmyk_pdf_has_print_sized_page(target, photos, tmp_path):
    out = tmp_path / "c.pdf"
    make_poster(_opts(target, photos, tmp_path, output=str(out), cmyk=True))
    pdf = out.read_bytes()
    box = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf)
    assert (float(box[1]), float(box[2])) == (6 * 72, 9 * 72)
    assert b"/DeviceCMYK" in pdf and b"/Decode [ 1 0 1 0 1 0 1 0 ]" in pdf


@pytest.mark.parametrize("ext", [".tif", ".webp"])
def test_other_output_formats(target, photos, tmp_path, ext):
    out = tmp_path / f"o{ext}"
    make_poster(_opts(target, photos, tmp_path, output=str(out)))
    assert Image.open(out).size == (240, 360)


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
        markers.append(d[i + 1])
        if d[i + 1] == 0xDA:
            break
        i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    assert 0xC0 in markers and 0xC2 not in markers


def test_panels_split_with_overlap(target, photos, tmp_path):
    out = tmp_path / "long.png"
    files = make_poster(_opts(target, photos, tmp_path, output=str(out), panels=3,
                              overlap_in=0.5)).outputs
    assert [f.name for f in files] == [f"long_part{i}of3.png" for i in (1, 2, 3)]
    assert sum(Image.open(f).height for f in files) == 9 * 40 + 2 * 20
    assert all(Image.open(f).width == 6 * 40 for f in files)


def test_test_strip_and_fallbacks(target, photos, tmp_path):
    out = tmp_path / "poster.pdf"
    res = make_poster(_opts(target, photos, tmp_path, output=str(out), cmyk=True,
                            test_strip=True, strip_height_in=2, fallbacks=True))
    names = {p.name for p in res.outputs}
    assert "poster.test-strip.pdf" in names
    assert "poster.alt-rgb.jpg" in names           # the format plotters' USB readers like
    pdf = (tmp_path / "poster.test-strip.pdf").read_bytes()
    box = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf)
    assert (float(box[1]), float(box[2])) == (6 * 72, 2 * 72)


def test_report_and_previews(target, photos, tmp_path):
    out = tmp_path / "r.pdf"
    res = make_poster(_opts(target, photos, tmp_path, output=str(out), preview=True,
                            printer="plotter-bond", cmyk=True, max_mb=5, dpi=300,
                            width_in=6, height_in=9))
    html = res.report.read_text(encoding="utf-8")
    for text in ("On paper, from across the room", "Up close, actual size",
                 "Checks and recommendations", "bond", "100% scale"):
        assert text in html
    assert (tmp_path / "r.preview.jpg").exists()
    titles = [f.title for f in res.findings]
    if find_cmyk_profile():
        assert res.gamut_pct is not None  # CMYK round trip measured
    else:  # e.g. Linux/macOS CI: the user is told how to get accurate CMYK
        assert "No CMYK color profile found on this computer" in titles


def test_printer_rules_stop_impossible_jobs(target, photos, tmp_path):
    opt = _opts(target, photos, tmp_path, output=str(tmp_path / "x.pdf"),
                printer="plotter-bond", width_in=48, height_in=36)
    with pytest.raises(PreflightError) as e:
        make_poster(opt)
    err = [f for f in e.value.findings if f.level == "error"]
    assert err and "--size 36x48" in err[0].fix  # suggests rotating it


def test_preflight_advice(target, photos, tmp_path):
    opt = _opts(target, photos, tmp_path, output=str(tmp_path / "x.jpg"),
                printer="plotter-bond", cmyk=True, width_in=36, height_in=54, dpi=300,
                cols=200)
    plan, findings, _ = preflight(opt)
    titles = " | ".join(f.title for f in findings)
    assert "CMYK JPEGs are often rejected" in titles
    assert "would appear" in titles           # too many tiles for 81 photos
    assert "Files must be under 75 MB" in titles
    assert "too small" not in titles or plan.tile_in < 0.3


def test_png_cannot_be_cmyk(target, photos, tmp_path):
    with pytest.raises(ValueError):
        make_poster(_opts(target, photos, tmp_path, output=str(tmp_path / "x.png"), cmyk=True))


def test_auto_cols():
    assert auto_cols(36, 54, 3000) == 72
    assert auto_cols(36, 54, 100) < 20
    assert auto_cols(36, 54, 1) == 8
