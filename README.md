# photomosaic-poster

Turn one photo plus hundreds (or thousands) of photos into a **print-ready photo mosaic
poster**. Up close you see every little photo; from across the room you see the big
picture.

It's made for birthday and graduation posters, where friends send in their photos. It
covers the whole job, not just the mosaic:

- **Collecting** photos from friends, with a private upload page.
- **Reading** whatever arrives: every common image format, HEIC and AVIF, camera RAW,
  Drive and iCloud zips, even video frames.
- **Choosing** the best target photo.
- **Matching** the printer's rules: CMYK, DPI, file-size limits and roll width.
- **Previewing** what it will really look like on that paper.
- **Recovering** when a printer rejects the file or stalls halfway.

| Target picture | Poster (600 photos) | Close up |
|---|---|---|
| ![target](https://raw.githubusercontent.com/ShawnJoshua03/photomosaic-poster/main/docs/demo-target.jpg) | ![poster](https://raw.githubusercontent.com/ShawnJoshua03/photomosaic-poster/main/docs/demo.jpg) | ![close up](https://raw.githubusercontent.com/ShawnJoshua03/photomosaic-poster/main/docs/demo-closeup.jpg) |

*The demo is built from generated images. Run `python examples/make_demo.py` to make
it yourself.*

## Install

Requires Python 3.9 or newer.

```bash
pip install "photomosaic-poster[all]"
```

`[all]` adds camera RAW (`rawpy`) and video-frame (`av`) support. Leave it off if you
don't need those.

## The whole workflow

```bash
# 1. Collect: friends open a link on their phones and upload straight to your computer
mosaic-poster collect photos/

# 2. Choose the big picture: scores and side-by-side mosaic previews
mosaic-poster compare beach.jpg graduation.jpg selfie.heic --photos photos/

# 3. Check against your printer before spending time rendering
mosaic-poster check beach.jpg photos/ --printer plotter-bond --size 36x54

# 4. Make it, plus a test strip and backup formats
mosaic-poster beach.jpg photos/ --printer plotter-bond --size 36x54 --test-strip --fallbacks
```

Every render also writes **`poster.report.html`**. It contains:

- **Previews:** the poster as it will look on the chosen paper, from across the room,
  at actual size and magnified, next to the on-screen version.
- **Checks:** every printer rule, plus recommendations with the exact option that
  fixes each one.
- **Checklist:** what to do at the printer.

## Printers and paper

```bash
mosaic-poster printers
```

| `--printer` | For | Sends |
|---|---|---|
| `plotter-bond` | Wide-format plotters on bond paper (e.g. HP DesignJet, 36" roll) | CMYK PDF, 300 DPI, under 75 MB |
| `photo-lab` | Online/in-store photo lab posters | sRGB JPEG, 300 DPI |
| `print-shop` | Print shop large-format inkjet (matte/satin) | PDF/TIFF/JPEG, 300 DPI |
| `canvas` | Canvas print services | sRGB JPEG, 200 DPI, warns about wrap edges |
| `office-inkjet` | Home/office printers (test prints) | Letter/A4 |

A preset fills in the DPI, color mode, file type, size limit and paper color compensation.
Anything you type yourself overrides it. Papers (`--paper`) are glossy, luster, matte,
bond, canvas and plain.

**Exact previews:** paper simulation is an approximation. If your print shop publishes an
ICC profile for the printer and paper, which many do, pass `--printer-profile shop.icc`
for a true soft proof.

Already have a file? `mosaic-poster proof poster.jpg --paper bond` shows how it will print.

## Photos it can read

| Kind | Formats |
|---|---|
| Images | JPEG, PNG, HEIC/HEIF, AVIF, WebP, TIFF, GIF, BMP, JPEG 2000, PSD, TGA, QOI, PPM ... |
| Camera RAW | CR2, CR3, NEF, ARW, DNG, RAF, ORF, RW2, PEF and more (`pip install rawpy`) |
| Video | MOV, MP4, M4V, ... one frame each, opt-in with `--include-videos` (`pip install av`) |
| Archives | `.zip`, read directly: no need to unzip Google Drive or iCloud downloads |

The tool also takes care of the messy parts:

- **Orientation:** phone rotation (EXIF) is applied.
- **Transparency:** see-through areas become white paper.
- **Animations:** animated GIFs use their first frame.
- **Duplicates:** exact duplicate files and Mac zip junk are dropped.
- **Look-alikes:** burst shots are treated as one photo.
- **Skipped files:** anything left out is listed with the reason.

## Common adjustments

| Problem | Option |
|---|---|
| Face not clear enough | `--tint 0.6 --overlay 0.4` |
| Little photos too washed out | `--tint 0.3 --overlay 0.2` |
| Dark target photo | `--gamma 0.7` |
| Wrong part of the photo kept | `--crop 0.1,0.15,0.9,0.75` (check with `--save-target crop.png`) |
| Too many repeats | fewer `--cols`, or collect more photos |
| Printer rejects the file | `--fallbacks` writes PDF/JPEG/RGB/CMYK alternatives |
| Printer stops partway | `--panels 2 --overlap 0.5` |
| File too big | `--max-mb 74` (best quality that fits) |
| Want a caption | `--text "HAPPY BIRTHDAY SAM"` |

## How many photos do I need?

Repeats get noticeable above about 4–5 uses per photo. With the default `--cols 0` the
tool picks the grid for you: tiles about half an inch across, fewer and bigger if you
don't have enough photos.

| Poster | Tiles | Minimum photos | Good | Great |
|---|---|---|---|---|
| 18×24 | ~1,700 | 250 | 500 | 900 |
| 24×36 | ~3,500 | 450 | 900 | 1,800 |
| 36×54 | ~7,800 | 1,000 | 2,000 | 3,900 |

## How it works

1. **Target:** the target photo is cropped to the poster shape and averaged into a grid.
2. **Photos:** every photo is decoded upright, cropped square and cached, so re-renders
   take seconds. Duplicates are dropped and look-alikes grouped with a perceptual hash.
3. **Matching:** each tile gets a photo of similar color, compared in CIE Lab. It caps
   repeats, keeps a photo and its look-alikes apart, picks randomly among near-best
   matches, then makes sure every distinct photo gets a spot.
4. **Tint and overlay:** colors are nudged toward the tile's target color (`--tint`),
   and a faint sharpened copy of the target goes on top (`--overlay`) for fine features.
5. **Drawing:** the poster is drawn in strips, so even 175-megapixel prints fit in memory,
   then converted to CMYK if needed and saved at the best quality under the size limit.
6. **Report:** previews simulate the paper (white point, black depth, dot gain, color
   range, ink spread), or use an ICC soft proof. Findings come from rules learned the
   hard way at real printers.

## Use it from Python

```python
from mosaic_poster import PosterOptions, make_poster

result = make_poster(PosterOptions(target="target.jpg", tile_dirs=["photos"],
                                   output="poster.pdf", width_in=36, height_in=54,
                                   dpi=300, printer="plotter-bond", cmyk=True))
print(result.outputs, result.report)
```

## Docs

- **[Printing guide](https://github.com/ShawnJoshua03/photomosaic-poster/blob/main/docs/printing.md):** printer rules, paper, previews and
  troubleshooting.
- **[Collecting photos](https://github.com/ShawnJoshua03/photomosaic-poster/blob/main/docs/collecting-photos.md):** the upload page, Drive, iCloud
  and choosing the target.

## Privacy

Everything runs on your computer. The upload page sends photos only to your computer,
and the `.gitignore` keeps photos and posters out of git.

## License

MIT
