// Poster layout math (mirrors src/mosaic_poster/plan.py).

export interface Plan {
  widthIn: number;
  heightIn: number;
  dpi: number;
  W: number; // pixels
  H: number;
  cols: number;
  rows: number;
}

export const cells = (p: Plan) => p.cols * p.rows;
export const tileIn = (p: Plan) => p.widthIn / p.cols;
export const megapixels = (p: Plan) => (p.W * p.H) / 1e6;

/** Columns for ~0.5 in tiles, but no more cells than ~3 uses per photo. */
export function autoCols(widthIn: number, heightIn: number, nPhotos: number,
  tile = 0.5, targetUses = 3): number {
  const bySize = widthIn / tile;
  const byPhotos = Math.sqrt((targetUses * Math.max(nPhotos, 1) * widthIn) / heightIn);
  return Math.max(8, Math.round(Math.min(bySize, byPhotos)));
}

export function makePlan(widthIn: number, heightIn: number, dpi: number, cols: number,
  nPhotos: number): Plan {
  const W = Math.round(widthIn * dpi), H = Math.round(heightIn * dpi);
  const c = cols > 0 ? cols : autoCols(widthIn, heightIn, nPhotos);
  const rows = Math.max(1, Math.round((H * c) / W));
  return { widthIn, heightIn, dpi, W, H, cols: c, rows };
}

/** Pixel edges that split `total` into `n` near-equal parts (exact edge-to-edge fill). */
export function edges(total: number, n: number): Int32Array {
  const e = new Int32Array(n + 1);
  for (let i = 0; i <= n; i++) e[i] = Math.round((i * total) / n);
  return e;
}

export interface TargetStats {
  width: number;
  height: number;
  ppi: number;        // target pixels per printed inch
  brightness: number; // mean luma 0-255
  contrast: number;   // luma std dev
  sharpness: number;  // mean edge strength
  cropLoss: number;   // share of the photo cut off to fit the poster shape
}

/** Measurements of the target photo from a downscaled copy (gray: luma values). */
export function analyzeTarget(gray: Float32Array, w: number, h: number, fullW: number,
  fullH: number, posterW: number, posterH: number): TargetStats {
  let sum = 0;
  for (const v of gray) sum += v;
  const mean = sum / gray.length;
  let sq = 0, edge = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const v = gray[y * w + x];
      sq += (v - mean) ** 2;
      if (x > 0 && y > 0) {
        edge += Math.abs(v - gray[y * w + x - 1]) + Math.abs(v - gray[(y - 1) * w + x]);
      }
    }
  }
  const aImg = fullW / fullH, aPoster = posterW / posterH;
  return {
    width: fullW, height: fullH, ppi: fullW / posterW, brightness: mean,
    contrast: Math.sqrt(sq / gray.length), sharpness: edge / gray.length,
    cropLoss: 1 - Math.min(aImg, aPoster) / Math.max(aImg, aPoster),
  };
}
