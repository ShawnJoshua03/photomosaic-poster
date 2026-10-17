# Printing guide

A mosaic poster has thousands of tiny photos, so getting the file right for the printer
matters more than usual. Start with a preset, check, test, then print.

## 1. Pick a preset (or tell it about your printer)

```bash
mosaic-poster printers
```

| Preset | Paper it assumes | What it sends |
|---|---|---|
| `plotter-bond` | uncoated bond | CMYK PDF, 300 DPI, under 75 MB, max 36 in wide |
| `photo-lab` | luster | sRGB JPEG, 300 DPI |
| `print-shop` | matte | PDF / TIFF / JPEG, 300 DPI |
| `canvas` | canvas | sRGB JPEG, 200 DPI |
| `office-inkjet` | plain | for test prints, letter / A4 |

These are typical rules. If your shop posts its own, for example "CMYK, 300 dpi, JPEG or
PDF/X-1a, under 75 MB, 36 inch max", the individual options always override the preset:
`--cmyk/--rgb`, `--dpi`, `-o file.pdf`, `--max-mb`, `--size`.

## 2. Check before you render

```bash
mosaic-poster check target.jpg photos/ --printer plotter-bond --size 36x54
```

This takes seconds and catches the expensive mistakes:

- **Too wide:** the poster is wider than the roll. It suggests rotating or scaling,
  with the exact `--size`.
- **Wrong file type:** the printer doesn't take the format you chose.
- **CMYK JPEG on a plotter:** many reject it from USB, so it suggests a PDF.
- **Too many repeats:** it suggests a `--cols` value, or collecting more photos.
- **Tiles too small:** people couldn't recognize the photos.
- **Weak target photo:** too dark, low contrast, low resolution, or the wrong shape.
- **Skipped files:** RAW or video files it needs an extra decoder for.

Errors stop a render, unless you add `--force`.

## 3. See what it will look like on paper

Every render writes `poster.report.html` and `poster.preview.jpg`. The report shows:

- **On paper, from across the room:** the whole poster as printed.
- **On screen:** the file itself, for comparison.
- **Up close, actual size:** a 6 × 4 inch patch around the face at real size on a typical
  monitor.
- **Magnified 3×:** for judging how sharp the little photos print.

**How accurate is it?**
- **With `--printer-profile shop.icc`:** an ICC soft proof, the same method as
  Photoshop's *Proof Colors*. Ask your print shop for the profile of the printer and
  paper they'll use.
- **Without a profile:** a paper simulation of paper white, black depth, dot gain, color
  range and ink spread. It's good for the "will bond paper look dull?" question, but
  approximate.
- **CMYK files:** colors are also round-tripped through the CMYK profile, and the report
  says what share of the picture changes color noticeably.

For a file you already have: `mosaic-poster proof poster.jpg --printer plotter-bond`.

## 4. Paper color compensation

Uncoated paper, like bond and plain paper, soaks up ink, so prints come out darker,
flatter and softer. Presets apply a correction automatically, and you can set it
yourself:

| Paper | brightness | contrast | saturation |
|---|---|---|---|
| bond | 1.05 | 1.10 | 1.15 |
| plain | 1.04 | 1.08 | 1.12 |
| matte | 1.00 | 1.05 | 1.07 |
| canvas | 1.00 | 1.05 | 1.08 |
| luster | 1.00 | 1.00 | 1.03 |
| glossy | 1.00 | 1.00 | 1.00 |

## 5. Test, then print

```bash
mosaic-poster target.jpg photos/ --printer plotter-bond --size 36x54 --test-strip --fallbacks
```

- **`--test-strip`:** writes `poster.test-strip.pdf`, a full-width 3-inch slice through the
  face, in the same format and color as the real file. Printing it checks three things
  cheaply: the printer accepts the file, the colors are right, and the photos are big
  enough.
- **`--fallbacks`:** writes `poster.alt-rgb.jpg` and other alternatives, so you have
  something else to try at the printer.

**At the printer:**
- **Scale:** print at **100%**, with "fit to page" off.
- **Quality:** use **Best**, not Normal. Normal visibly blurs the small photos.
- **Preview:** check the printer's preview is upright and not cropped.
- **One file at a time.**
- **Drying:** let the ink dry before rolling. Bond smudges easily in dark areas.

## Troubleshooting

**"File contains format errors. The printer cannot process the job" (HP DesignJet
61:08.2) when printing from USB.**
The plotter's built-in reader can't open that file. CMYK JPEGs are the usual cause, even
when the shop's sign says CMYK and JPEG are allowed. The PDF version prints. In order:

1. `-o poster.pdf`, the CMYK PDF.
2. `poster.alt-rgb.jpg` from `--fallbacks`.
3. `--no-optimize --no-icc`, the plainest possible encoding.

**The printer stops or crashes partway through.**
Very large jobs can exhaust a plotter's memory. Split the poster:

```bash
--panels 2 --overlap 0.5
```

This writes `poster_part1of2.pdf` and `poster_part2of2.pdf`, with half an inch of overlap
for trimming and joining. The seam usually falls in the background. Print the test strip
first to rule out a file problem.

**The JPEG quality had to drop low to fit the size limit.**
A 36 × 54 inch poster at 300 DPI is 175 megapixels. RGB compresses much better than CMYK.
Splitting into panels gives each part the full size limit. On bond or matte paper, quality
in the 50s is rarely visible.

**The colors look odd when I open the file.**
Many viewers show CMYK files wrong. Trust `poster.preview.jpg` and the report.

**The face isn't recognizable.**
Raise `--overlay` (0.4–0.5) and `--tint` (0.6–0.7), or crop tighter with `--crop`. Or run
`mosaic-poster compare` to find a better target photo: front-facing, well lit and sharp.

**I can see too many repeats.**
Use fewer columns, or collect more photos. Burst shots count as one photo.
