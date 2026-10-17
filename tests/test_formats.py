import zipfile

import numpy as np
import pytest
from PIL import Image

from mosaic_poster.formats import open_photo, scan
from mosaic_poster.tiles import load_tiles

RED = (220, 30, 30)


def _save_all_formats(folder):
    """One red picture saved in every format Pillow can write here."""
    base = Image.new("RGB", (80, 60), RED)
    made = {}
    for ext, kw in [(".jpg", {}), (".png", {}), (".webp", {}), (".bmp", {}), (".tif", {}),
                    (".gif", {}), (".jp2", {}), (".tga", {}), (".ppm", {}), (".qoi", {})]:
        p = folder / f"red{ext}"
        try:
            base.save(p, **kw)
        except (OSError, KeyError, ValueError):
            continue  # codec not built into this Pillow
        made[ext] = p
    try:
        base.save(folder / "red.avif")
        made[".avif"] = folder / "red.avif"
    except (OSError, KeyError, ValueError):
        pass
    import pillow_heif  # noqa: F401
    base.save(folder / "red.heic")
    made[".heic"] = folder / "red.heic"
    return made


def test_every_common_format_opens_as_rgb(tmp_path):
    made = _save_all_formats(tmp_path)
    assert {".jpg", ".png", ".webp", ".tif", ".heic"} <= set(made)
    for ext, p in made.items():
        im = open_photo(p)
        assert im.mode == "RGB", ext
        r, g, b = np.asarray(im).reshape(-1, 3).mean(axis=0)
        assert r > 150 and g < 90 and b < 90, ext


def test_transparent_png_lands_on_white_paper(tmp_path):
    im = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    im.save(tmp_path / "clear.png")
    assert np.asarray(open_photo(tmp_path / "clear.png")).min() == 255


def test_16bit_png_and_animated_gif(tmp_path):
    Image.fromarray(np.full((30, 30), 60000, np.uint16)).save(tmp_path / "deep.png")
    assert np.asarray(open_photo(tmp_path / "deep.png")).mean() > 200
    frames = [Image.new("RGB", (30, 30), c) for c in (RED, (0, 0, 255))]
    frames[0].save(tmp_path / "anim.gif", save_all=True, append_images=frames[1:])
    assert np.asarray(open_photo(tmp_path / "anim.gif"))[..., 0].mean() > 150  # first frame


def test_photos_inside_zip_files_are_used(tmp_path):
    Image.new("RGB", (50, 50), RED).save(tmp_path / "a.jpg")
    with zipfile.ZipFile(tmp_path / "drive-download-1.zip", "w") as z:
        z.write(tmp_path / "a.jpg", "Folder/a.jpg")
        z.writestr("Folder/b.png", _png_bytes((0, 0, 255)))
        z.writestr("__MACOSX/._a.jpg", b"junk")
    (tmp_path / "a.jpg").unlink()
    refs, skipped = scan([tmp_path])
    assert sorted(r.name for r in refs) == ["a.jpg", "b.png"]
    assert not skipped  # mac junk is ignored silently
    names, tiles, _ = load_tiles([tmp_path / "drive-download-1.zip"], 10)
    assert len(names) == 2


def _png_bytes(color):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, "PNG")
    return buf.getvalue()


def test_decompression_bombs_are_refused(tmp_path):
    # A tiny PNG that claims to be 30,000 x 30,000 pixels (900 MP).
    import struct
    import zlib
    w = h = 30000
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    chunk = lambda t, d: (struct.pack(">I", len(d)) + t + d
                          + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b""))
    (tmp_path / "bomb.png").write_bytes(data)
    Image.new("RGB", (40, 40), RED).save(tmp_path / "ok.jpg")
    names, _, skipped = load_tiles([tmp_path], 8)
    assert names == ["ok.jpg"]                   # the bomb is skipped...
    assert skipped["unreadable or damaged"] == 1  # ...and reported, not loaded


def test_skipped_files_are_explained(tmp_path):
    (tmp_path / "clip.mov").write_bytes(b"\0" * 10)
    (tmp_path / "notes.txt").write_text("hi")
    _, skipped = scan([tmp_path])
    assert any("video" in k for k in skipped)
    assert skipped["not a photo"] == 1


def test_video_frame(tmp_path):
    av = pytest.importorskip("av")
    path = tmp_path / "clip.mp4"
    with av.open(str(path), "w") as out:
        s = out.add_stream("mpeg4", rate=10)
        s.width, s.height, s.pix_fmt = 64, 48, "yuv420p"
        for _ in range(10):
            frame = av.VideoFrame.from_image(Image.new("RGB", (64, 48), RED))
            for pkt in s.encode(frame):
                out.mux(pkt)
        for pkt in s.encode():
            out.mux(pkt)
    refs, _ = scan([tmp_path], include_videos=True)
    im = open_photo(refs[0])
    assert im.size == (64, 48)
    assert np.asarray(im)[..., 0].mean() > 150


def test_raw_needs_rawpy_or_is_explained(tmp_path):
    (tmp_path / "IMG_0001.CR2").write_bytes(b"\0" * 100)
    refs, skipped = scan([tmp_path])
    try:
        import rawpy  # noqa: F401
        assert len(refs) == 1  # found; this fake file then fails to decode gracefully
        _, _, more = load_tiles([tmp_path], 8)
        assert more["unreadable or damaged"] == 1
    except ImportError:
        assert any("rawpy" in k for k in skipped)
