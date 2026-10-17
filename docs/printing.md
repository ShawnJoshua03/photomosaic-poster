# Printing guide

A mosaic poster has thousands of tiny photos, so getting the file right for the printer
matters more than usual. This page covers what to ask, what to send, and how to fix the
usual problems.

## 1. Ask the printer three things

1. **Maximum width.** Wide-format plotters take rolls, often 24" or 36" wide, but the
   length can be almost anything. A 36-inch roll can print 36×54, for example.
2. **File rules.** Many shops post them: color mode (RGB or CMYK), DPI, file type and a
   maximum file size.
3. **Paper.** Glossy or matte photo paper shows the most detail. Uncoated bond paper
   soaks up ink, so prints come out darker and flatter.

## 2. Pick the size and tiles

Keep tiles around **0.5 inch** or larger if people should recognize faces in them:

```
columns ≈ poster width in inches × 2
```

For example, a 36-inch-wide poster gets about 66–72 columns. You also need enough photos
for that many tiles; see the table in the README. `--cols 0`, the default, does this math
for you.

The shape of the target photo matters. A portrait photo suits a portrait poster. If the
photo and poster shapes differ, the target is cropped (see `--crop` and `--focus-y`).

## 3. Make the file

| The printer asks for | Use |
|---|---|
| Nothing specific, photo lab | `-o poster.jpg --dpi 300` |
| CMYK | `--cmyk` with `.jpg`, `.pdf` or `.tif` output |
| A maximum file size | `--max-mb 74`, safely under a "75 MB" rule |
| PDF | `-o poster.pdf` (one page at exactly the print size) |
| 300 DPI | `--dpi 300` |

**A typical plotter job:**

```bash
mosaic-poster target.jpg photos/ -o poster.pdf --size 36x54 --dpi 300 \
    --cmyk --max-mb 74 --brightness 1.05 --contrast 1.1 --saturation 1.15
```

**What `--max-mb` does:** a 36×54 inch poster at 300 DPI is 175 megapixels. The tool finds
the highest JPEG quality that fits the limit. RGB compresses much better than CMYK, so RGB
files get much higher quality at the same size. Use CMYK only if the printer asks for it.

**CMYK color:** the tool converts with a CMYK ICC profile already on your computer.
On Windows that's SWOP. On macOS it's Generic CMYK. If you have the shop's own profile,
pass it with `--cmyk-profile shop.icc`.

## 4. At the printer

- **Scale:** print at **100%**. Turn off "fit to page", or it adds margins and shrinks
  the poster.
- **Quality:** use **Best** or high quality, not Normal or Fast. The tiny photos are the
  point.
- **Preview:** check the preview is upright and not cropped.
- **Drying:** let it dry before rolling it. Bond paper smudges easily in dark areas.
- **Test strip:** for big jobs, print a strip first (`--panels`, or crop a test area).

## Troubleshooting

**"File contains format errors" / HP DesignJet error 61:08.2 when printing from USB.**
The printer's built-in USB reader can't open the file type, even if the shop's sign says
it's allowed. That rule usually means files their computer processes. Try these, one file
at a time:

1. A PDF: `-o poster.pdf` (works with `--cmyk` too).
2. The plainest RGB JPEG: `-o poster.jpg --no-optimize`.
3. CMYK JPEG without an embedded profile: `-o poster.jpg --cmyk --no-icc --no-optimize`.

**The printer stops or crashes partway through.**
Plotters can run out of memory on very large images. Split the poster into panels:

```bash
--panels 2 --overlap 0.5
```

This writes `poster_part1of2.pdf` and `poster_part2of2.pdf`, each with half an inch of
overlap so you can trim and join them neatly. A seam across a background area, below the
face, is hard to notice.

**The colors look odd when I open the file on my computer.**
Many photo viewers show CMYK files wrong, too dark or with odd colors. Check with the
`--save-target` image or an RGB export instead.

**The face isn't recognizable.**
Raise `--overlay` (0.4–0.5) and `--tint` (0.6–0.7), crop tighter on the face with `--crop`,
or use a brighter, higher-contrast photo. A front-facing, well-lit close-up works best.

**I can see too many repeats.**
Use fewer columns, add photos, or lower `--max-repeats`. Burst shots count as one photo
because they look alike.
