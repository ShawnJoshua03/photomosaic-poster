// Pixel work shared by the live preview and the full-size export, so the preview is
// computed exactly like the download.

import { applyFinish, type Finish } from "./color";

export interface Crop { zoom: number; fx: number; fy: number } // fx/fy: focus 0-1

/** Source rectangle of the target that fills a poster of aspect `aspect` (w/h). */
export function cropRect(tw: number, th: number, aspect: number, crop: Crop) {
  let w = tw, h = tw / aspect;
  if (h > th) { h = th; w = th * aspect; }
  w /= crop.zoom; h /= crop.zoom;
  const x = Math.min(Math.max(0, crop.fx * tw - w / 2), tw - w);
  const y = Math.min(Math.max(0, crop.fy * th - h / 2), th - h);
  return { x, y, w, h };
}

export interface StripJob {
  W: number;               // strip width in px
  x0?: number;             // strip left within the poster (default 0)
  y0: number;              // strip top within the poster
  h: number;               // strip height
  cols: number;
  c0?: number; c1?: number; // tile columns covered (default: all)
  xe: Int32Array;          // column edges (poster px)
  ye: Int32Array;          // row edges (poster px)
  r0: number; r1: number;  // tile rows in this strip
  grid: Int32Array;        // photo per cell
  cellRGB: Float32Array;   // target color per cell (3 per cell)
  means: Float32Array;     // photo mean colors (3 per photo)
  tint: number;
  overlay: number;
  finish: Finish;
  grayMean: number;
}

/**
 * px: the strip with photos already drawn. ov: the target drawn at the same size
 * (or null). Applies tint, overlay and print color compensation in place.
 */
export function composeStrip(px: Uint8ClampedArray, ov: Uint8ClampedArray | null, j: StripJob) {
  const { W, cols, xe, ye, grid, cellRGB, means, tint } = j;
  const x0 = j.x0 ?? 0, c0 = j.c0 ?? 0, c1 = j.c1 ?? cols;
  for (let r = j.r0; r < j.r1; r++) {
    const ya = Math.max(0, ye[r] - j.y0), yb = Math.min(j.h, ye[r + 1] - j.y0);
    for (let c = c0; c < c1; c++) {
      const cell = r * cols + c, t = grid[cell];
      // Shift the photo's average color part of the way to the cell's: keeps detail.
      const dr = tint * (cellRGB[cell * 3] - means[t * 3]);
      const dg = tint * (cellRGB[cell * 3 + 1] - means[t * 3 + 1]);
      const db = tint * (cellRGB[cell * 3 + 2] - means[t * 3 + 2]);
      const xa = Math.max(0, xe[c] - x0), xb = Math.min(W, xe[c + 1] - x0);
      for (let y = ya; y < yb; y++) {
        let i = (y * W + xa) * 4;
        for (let x = xa; x < xb; x++, i += 4) {
          px[i] += dr; px[i + 1] += dg; px[i + 2] += db;
        }
      }
    }
  }
  if (ov && j.overlay > 0) {
    // A faint copy of the target restores eyes and hair a coarse grid can't carry.
    const a = j.overlay, b = 1 - a;
    for (let i = 0; i < px.length; i += 4) {
      px[i] = px[i] * b + ov[i] * a;
      px[i + 1] = px[i + 1] * b + ov[i + 1] * a;
      px[i + 2] = px[i + 2] * b + ov[i + 2] * a;
    }
  }
  applyFinish(px, j.finish, j.grayMean);
}

/** Light unsharp mask for the overlay layer (radius ~ tile/3), done with a canvas blur. */
export function sharpen(ctx: OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D,
  w: number, h: number, radius: number, amount = 1.2) {
  if (radius < 0.6) return;
  const src = ctx.getImageData(0, 0, w, h);
  const tmp = new OffscreenCanvas(w, h);
  const tg = tmp.getContext("2d")!;
  tg.filter = `blur(${radius}px)`;
  tg.drawImage(ctx.canvas as CanvasImageSource, 0, 0);
  const blur = tg.getImageData(0, 0, w, h).data, p = src.data;
  for (let i = 0; i < p.length; i += 4) {
    p[i] += amount * (p[i] - blur[i]);
    p[i + 1] += amount * (p[i + 1] - blur[i + 1]);
    p[i + 2] += amount * (p[i + 2] - blur[i + 2]);
  }
  ctx.putImageData(src, 0, 0);
}
