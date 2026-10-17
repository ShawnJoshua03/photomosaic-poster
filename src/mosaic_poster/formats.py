"""Reading photos from anywhere: every common image format, camera RAW, video frames,
and photos inside .zip files (how Google Drive and iCloud hand over big downloads)."""
import hashlib
import io
import logging
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger("mosaic_poster")

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HAVE_HEIF = True
except ImportError:  # pragma: no cover - pillow-heif is a normal dependency
    HAVE_HEIF = False

try:
    import rawpy
except ImportError:
    rawpy = None

try:
    import av
except ImportError:
    av = None

# Phone panoramas reach ~100 MP; anything far beyond that is a "decompression bomb"
# (a tiny file claiming billions of pixels) and is refused instead of eating all memory.
Image.MAX_IMAGE_PIXELS = 400_000_000
MAX_FILE_BYTES = 2_000_000_000  # skip absurdly large files (and zip members) outright
MAX_IN_MEMORY = 400_000_000     # bigger photos/videos are decoded from disk, not RAM

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".gif", ".bmp", ".dib",
    ".tif", ".tiff", ".heic", ".heif", ".hif", ".avif", ".jp2", ".j2k", ".jpx", ".jpf",
    ".psd", ".tga", ".ppm", ".pgm", ".pbm", ".pnm", ".pcx", ".qoi", ".ico", ".icns",
    ".sgi", ".rgb", ".dds",
}
RAW_EXTS = {
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf",
    ".orf", ".rw2", ".pef", ".srw", ".x3f", ".3fr", ".erf", ".kdc", ".mrw", ".raw", ".iiq",
}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".3gp", ".mts", ".m2ts"}
ARCHIVE_EXTS = {".zip"}
# Junk that zip files and phones add, never worth a warning.
_JUNK = ("__MACOSX/", "/.", ".DS_Store", "Thumbs.db", "desktop.ini")


@dataclass(frozen=True)
class PhotoRef:
    """One photo, either a file on disk or a member of a zip archive."""
    name: str          # display name
    kind: str          # "image", "raw" or "video"
    path: str          # file on disk (the zip itself for archive members)
    member: str = ""   # name inside the zip, if any
    size: int = 0

    @property
    def key(self):
        return f"{self.path}|{self.member}|{self.size}"

    def open(self):
        """A binary file object for the photo (read straight from the zip if needed)."""
        if self.member:
            z = zipfile.ZipFile(self.path)
            f = z.open(self.member)
            f._owner_zip = z  # keep the archive open as long as the member is
            return f
        return open(self.path, "rb")

    def read_bytes(self):
        if self.size > MAX_IN_MEMORY:
            raise ValueError(f"too large to load ({self.size / 1e6:.0f} MB)")
        with self.open() as f:
            return f.read()

    def digest(self):
        """Content hash (for spotting duplicates), read in chunks."""
        h = hashlib.md5(usedforsecurity=False)  # duplicate detection, not security
        with self.open() as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()


def _kind(name):
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in RAW_EXTS:
        return "raw"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def scan(sources, include_videos=False):
    """Find every photo in `sources` (folders, files or .zip files, searched recursively).

    Returns (photos, skipped) where skipped counts what was left out and why, so the
    user can be told about RAW files that need rawpy, videos, and so on.
    """
    photos, skipped = [], Counter()

    def consider(name, size, path, member=""):
        if any(j in name for j in _JUNK):
            return
        kind = _kind(name)
        if kind is None:
            skipped["not a photo"] += 1
        elif size > MAX_FILE_BYTES:
            skipped["file over 2 GB"] += 1
        elif kind == "raw" and rawpy is None:
            skipped["camera RAW (pip install rawpy)"] += 1
        elif kind == "video" and not include_videos:
            skipped["video (use --include-videos)"] += 1
        elif kind == "video" and av is None:
            skipped["video (pip install av)"] += 1
        else:
            photos.append(PhotoRef(Path(name).name, kind, str(path), member, size))

    def visit(p):
        if p.suffix.lower() in ARCHIVE_EXTS:
            try:
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        if not info.is_dir():
                            consider(info.filename, info.file_size, p, info.filename)
            except zipfile.BadZipFile:
                skipped["damaged zip"] += 1
        else:
            consider(p.name, p.stat().st_size, p)

    for src in sources:
        src = Path(src)
        if src.is_dir():
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    visit(p)
        elif src.is_file():
            visit(src)
        else:
            raise FileNotFoundError(f"photo source not found: {src}")
    photos.sort(key=lambda r: (r.path, r.member))
    return photos, skipped


def open_photo(source, draft=None):
    """Open any supported photo as an upright RGB image.

    source: a PhotoRef, a path, or raw bytes. draft: (w, h) hint so big JPEGs and RAW
    files can be decoded at reduced size, which is much faster for small tiles.
    """
    if not isinstance(source, PhotoRef):
        p = Path(source)
        source = PhotoRef(p.name, _kind(p.name) or "image", str(p), "", p.stat().st_size)
    # Files on disk are handed to the decoders by path (videos can be gigabytes);
    # zip members are read into memory, within MAX_IN_MEMORY.
    src = source.path if not source.member else io.BytesIO(source.read_bytes())
    if source.kind == "raw":
        return _open_raw(src, draft)
    if source.kind == "video":
        return _open_video(src)
    return _to_rgb(_open_image(src, draft), source.name)


def _open_image(src, draft):
    im = Image.open(src)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)  # animated GIF/WebP, multi-page TIFF: use the first frame
    if draft and im.format == "JPEG":
        im.draft("RGB", draft)
    im.load()
    return ImageOps.exif_transpose(im)  # phones store rotation in EXIF


def _to_rgb(im, name=""):
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))  # transparency -> white paper
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        im = im.point(lambda v: v / 256).convert("L")  # 16-bit scans and PNGs
    return im.convert("RGB")


_RAW_FLIP = {3: Image.Transpose.ROTATE_180, 5: Image.Transpose.ROTATE_90,
             6: Image.Transpose.ROTATE_270}


def _open_raw(src, draft):
    if rawpy is None:
        raise RuntimeError("camera RAW needs: pip install rawpy")
    with rawpy.imread(src) as raw:
        flip = raw.sizes.flip
        if draft:
            # The embedded preview JPEG is plenty for a tile and ~50x faster to decode.
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    im = Image.open(io.BytesIO(thumb.data))
                    im.load()
                    if im.getexif().get(274, 1) == 1 and flip in _RAW_FLIP:
                        im = im.transpose(_RAW_FLIP[flip])
                    else:
                        im = ImageOps.exif_transpose(im)
                    return im.convert("RGB")
                return Image.fromarray(thumb.data).convert("RGB")
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                pass
        rgb = raw.postprocess(use_camera_wb=True, half_size=bool(draft), output_bps=8)
        return Image.fromarray(rgb)  # postprocess already applies the camera rotation


def _open_video(src):
    """A frame from the middle of a video (phone videos, Live Photo clips)."""
    if av is None:
        raise RuntimeError("video frames need: pip install av")
    with av.open(src) as container:
        stream = container.streams.video[0]
        if stream.duration and stream.time_base:
            container.seek(int(stream.duration // 2), stream=stream)
        for frame in container.decode(stream):
            im = frame.to_image()
            rotation = getattr(frame, "rotation", 0) or 0  # phones record sideways
            if rotation % 360:
                im = im.rotate(rotation, expand=True)
            return im.convert("RGB")
    raise RuntimeError("no video frames")
