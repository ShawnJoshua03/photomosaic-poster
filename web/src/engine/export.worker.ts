/// <reference lib="webworker" />
// Full-resolution export, off the main thread. The poster is drawn a few tile-rows
// at a time; each strip is JPEG-compressed as soon as it's done and only the
// compressed strips are kept, so a 175-megapixel poster fits in a browser tab.

import type { Finish } from "./color";
import { composeStrip, sharpen } from "./compose";
import { edges } from "./layout";
import { buildPdf, type Strip } from "./pdf";

export interface Piece { name: string; r0: number; r1: number } // tile rows [r0, r1)

export interface ExportRequest {
  W: number; H: number; dpi: number; cols: number; rows: number;
  grid: Int32Array; cellRGB: Float32Array; means: Float32Array;
  masters: Blob[];                 // by photo index
  target: ImageBitmap;
  crop: { x: number; y: number; w: number; h: number }; // target px shown on the poster
  tint: number; overlay: number; finish: Finish; grayMean: number;
  format: "pdf" | "jpg";
  maxMB: number;                   // 0 = no limit
  pieces: Piece[];
}

export type ExportMessage =
  | { type: "progress"; stage: string; done: number; total: number }
  | { type: "done"; files: { name: string; blob: Blob; quality: number }[] }
  | { type: "error"; message: string };

const post = (m: ExportMessage) => (self as unknown as Worker).postMessage(m);
const MAX_STRIP_PIXELS = 12_000_000; // under Safari's canvas limit, small enough for phones

self.onmessage = async (ev: MessageEvent<ExportRequest>) => {
  try {
    post({ type: "done", files: await run(ev.data) });
  } catch (e) {
    post({ type: "error", message: e instanceof Error ? e.message : String(e) });
  }
};

async function run(q: ExportRequest) {
  const xe = edges(q.W, q.cols), ye = edges(q.H, q.rows);
  const cw = Math.ceil(q.W / q.cols), ch = Math.ceil(q.H / q.rows);

  // Decode each photo that's actually used, once, at tile size.
  const used = [...new Set(q.grid)];
  const tiles = new Map<number, ImageBitmap>();
  for (let i = 0; i < used.length; i++) {
    tiles.set(used[i], await createImageBitmap(q.masters[used[i]],
      { resizeWidth: cw, resizeHeight: ch, resizeQuality: "high" }));
    if (i % 50 === 0) post({ type: "progress", stage: "Preparing photos", done: i, total: used.length });
  }

  const stripRows = Math.max(1, Math.floor(MAX_STRIP_PIXELS / (q.W * ch)));
  const renderStrip = (r0: number, r1: number): ImageData => {
    const y0 = ye[r0], h = ye[r1] - y0;
    const c = new OffscreenCanvas(q.W, h);
    const g = c.getContext("2d", { willReadFrequently: true })!;
    for (let r = r0; r < r1; r++) {
      for (let col = 0; col < q.cols; col++) {
        g.drawImage(tiles.get(q.grid[r * q.cols + col])!, xe[col], ye[r] - y0,
          xe[col + 1] - xe[col], ye[r + 1] - ye[r]);
      }
    }
    const img = g.getImageData(0, 0, q.W, h);
    let ov: Uint8ClampedArray | null = null;
    if (q.overlay > 0) {
      // Padding above and below keeps the sharpen filter from leaving seams.
      const pad = Math.ceil(ch * 1.2);
      const top = Math.max(0, y0 - pad), bottom = Math.min(q.H, y0 + h + pad);
      const oc = new OffscreenCanvas(q.W, bottom - top);
      const og = oc.getContext("2d", { willReadFrequently: true })!;
      og.imageSmoothingQuality = "high";
      const sy = q.crop.y + (top / q.H) * q.crop.h, sh = ((bottom - top) / q.H) * q.crop.h;
      og.drawImage(q.target, q.crop.x, sy, q.crop.w, sh, 0, 0, q.W, bottom - top);
      sharpen(og, q.W, bottom - top, cw / 3);
      ov = og.getImageData(0, y0 - top, q.W, h).data;
    }
    composeStrip(img.data, ov, {
      W: q.W, y0, h, cols: q.cols, xe, ye, r0, r1, grid: q.grid, cellRGB: q.cellRGB,
      means: q.means, tint: q.tint, overlay: q.overlay, finish: q.finish, grayMean: q.grayMean,
    });
    return img;
  };
  const encode = async (img: ImageData, quality: number) => {
    const c = new OffscreenCanvas(img.width, img.height);
    c.getContext("2d")!.putImageData(img, 0, 0);
    return c.convertToBlob({ type: "image/jpeg", quality });
  };

  const files: { name: string; blob: Blob; quality: number }[] = [];
  for (const piece of q.pieces) {
    const ranges: [number, number][] = [];
    for (let r = piece.r0; r < piece.r1; r += stripRows) ranges.push([r, Math.min(piece.r1, r + stripRows)]);
    const pieceH = ye[piece.r1] - ye[piece.r0];

    // Pick a JPEG quality that fits the size limit: measure a sample strip at two
    // qualities, interpolate, then verify the real total (step down if over).
    let quality = 0.92;
    const limit = q.maxMB > 0 ? q.maxMB * 1e6 * 0.97 : 0;
    if (limit) {
      const mid = ranges[Math.floor(ranges.length / 2)];
      const sample = renderStrip(mid[0], mid[1]);
      const sPix = sample.width * sample.height;
      const hi = (await encode(sample, 0.92)).size / sPix, lo = (await encode(sample, 0.6)).size / sPix;
      const want = limit / (q.W * pieceH);
      if (want < hi) {
        const t = Math.log(want / hi) / Math.log(lo / hi); // 0 at q=.92, 1 at q=.6
        quality = Math.max(0.3, Math.min(0.92, 0.92 - 0.32 * t - 0.02));
      }
    }

    if (q.format === "pdf") {
      for (;;) {
        const strips: Strip[] = [];
        let total = 0;
        for (let i = 0; i < ranges.length; i++) {
          const [r0, r1] = ranges[i];
          const jpeg = await encode(renderStrip(r0, r1), quality);
          total += jpeg.size;
          strips.push({ jpeg, widthPx: q.W, heightPx: ye[r1] - ye[r0], yPx: ye[r0] - ye[piece.r0] });
          post({ type: "progress", stage: `Building ${piece.name}`, done: i + 1, total: ranges.length });
        }
        if (limit && total > limit && quality > 0.3) { quality = Math.max(0.3, quality - 0.08); continue; }
        files.push({ name: piece.name, blob: buildPdf(q.W, pieceH, q.dpi, strips), quality });
        break;
      }
    } else {
      const full = new OffscreenCanvas(q.W, pieceH);
      const fg = full.getContext("2d")!;
      for (let i = 0; i < ranges.length; i++) {
        const [r0, r1] = ranges[i];
        fg.putImageData(renderStrip(r0, r1), 0, ye[r0] - ye[piece.r0]);
        post({ type: "progress", stage: `Building ${piece.name}`, done: i + 1, total: ranges.length });
      }
      let blob = await full.convertToBlob({ type: "image/jpeg", quality });
      while (limit && blob.size > limit && quality > 0.3) {
        quality = Math.max(0.3, quality - 0.05);
        blob = await full.convertToBlob({ type: "image/jpeg", quality });
      }
      files.push({ name: piece.name, blob: setJpegDpi(new Uint8Array(await blob.arrayBuffer()), q.dpi), quality });
    }
  }
  tiles.forEach((b) => b.close());
  return files;
}

/** Browsers write JPEGs at 72 DPI; set the JFIF density so the print size is right. */
function setJpegDpi(b: Uint8Array, dpi: number): Blob {
  const d = Math.round(dpi);
  if (b[2] === 0xff && b[3] === 0xe0 && b[6] === 0x4a && b[7] === 0x46) { // APP0 "JF"
    b[13] = 1;                          // units: dots per inch
    b[14] = d >> 8; b[15] = d & 0xff;   // X density
    b[16] = d >> 8; b[17] = d & 0xff;   // Y density
    return new Blob([b as BlobPart], { type: "image/jpeg" });
  }
  const app0 = new Uint8Array([0xff, 0xe0, 0, 16, 0x4a, 0x46, 0x49, 0x46, 0, 1, 1, 1,
    d >> 8, d & 0xff, d >> 8, d & 0xff, 0, 0]);
  return new Blob([b.subarray(0, 2) as BlobPart, app0, b.subarray(2) as BlobPart], { type: "image/jpeg" });
}
