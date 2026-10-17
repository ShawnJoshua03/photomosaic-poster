// The poster project: ties photos, target, printer and look together, and renders
// previews (whole poster, up close) with the same pixel code the export uses.

import { advise, type Finding } from "./advice";
import { assignTiles, lookAlikeGroups } from "./assign";
import { composeStrip, cropRect, sharpen, type Crop } from "./compose";
import { labArray, luma, type Finish } from "./color";
import type { ExportRequest } from "./export.worker";
import { analyzeTarget, edges, makePlan, type Plan, type TargetStats } from "./layout";
import type { Library } from "./library";
import { simulatePaper, spreadPx } from "./paper";
import { PAPERS, PRINTERS, type Format } from "./presets";

export interface Settings {
  printer: string;      // key, "" = none
  paper: string;        // key, "" = none
  widthIn: number;
  heightIn: number;
  dpi: number;
  cols: number;         // 0 = auto
  tint: number;         // 0-1
  overlay: number;      // 0-1
  gamma: number;        // brighten the big photo (<1 brightens)
  finish: Finish;
  finishTouched: boolean;
  crop: Crop;
  format: Format;
  maxMB: number;
  seed: number;
}

export const defaultSettings = (): Settings => ({
  printer: "", paper: "", widthIn: 24, heightIn: 36, dpi: 150, cols: 0, tint: 0.5, overlay: 0.3,
  gamma: 1, finish: { brightness: 1, contrast: 1, saturation: 1 }, finishTouched: false,
  crop: { zoom: 1, fx: 0.5, fy: 0.45 }, format: "pdf", maxMB: 0, seed: 1,
});

/** What the chosen printer implies; the user's own choices are applied on top. */
export function applyPrinter(s: Settings, key: string): Settings {
  const pr = PRINTERS[key];
  const n = { ...s, printer: key, finish: { ...s.finish } };
  if (!pr) return n;
  n.paper = pr.paper;
  n.dpi = pr.dpi;
  n.format = pr.formats[0];
  n.maxMB = pr.maxMB ? Math.floor(pr.maxMB * 0.99) : 0;
  if (pr.maxWidthIn && n.widthIn > pr.maxWidthIn) {
    const f = pr.maxWidthIn / n.widthIn;
    n.heightIn = Math.round(n.heightIn * f);
    n.widthIn = pr.maxWidthIn;
  }
  return withPaper(n, n.paper);
}

export function withPaper(s: Settings, key: string): Settings {
  const n = { ...s, paper: key };
  if (!s.finishTouched) {
    const f = PAPERS[key]?.finish ?? {};
    n.finish = { brightness: f.brightness ?? 1, contrast: f.contrast ?? 1, saturation: f.saturation ?? 1 };
  }
  return n;
}

export interface Target {
  canvas: OffscreenCanvas | HTMLCanvasElement; // gamma applied, max 2400 px
  width: number; height: number;               // original size, for advice
  gray: Float32Array; gw: number; gh: number;
  source: ImageBitmap;
}

export async function loadTarget(blob: Blob): Promise<Target> {
  const src = await createImageBitmap(blob, { imageOrientation: "from-image" });
  const k = Math.min(1, 2400 / Math.max(src.width, src.height));
  const c = new OffscreenCanvas(Math.round(src.width * k), Math.round(src.height * k));
  c.getContext("2d")!.drawImage(src, 0, 0, c.width, c.height);
  const gw = 160, gh = Math.max(1, Math.round((160 * src.height) / src.width));
  const g = new OffscreenCanvas(gw, gh).getContext("2d", { willReadFrequently: true })!;
  g.drawImage(src, 0, 0, gw, gh);
  const d = g.getImageData(0, 0, gw, gh).data, gray = new Float32Array(gw * gh);
  for (let i = 0; i < gray.length; i++) gray[i] = luma(d[i * 4], d[i * 4 + 1], d[i * 4 + 2]);
  return { canvas: c, width: src.width, height: src.height, gray, gw, gh, source: src };
}

/** The target with the "brighten" curve applied, as the canvas everything draws from. */
function gammaCanvas(t: Target, gamma: number): OffscreenCanvas | HTMLCanvasElement {
  if (gamma === 1) return t.canvas;
  const c = new OffscreenCanvas(t.canvas.width, t.canvas.height);
  const g = c.getContext("2d", { willReadFrequently: true })!;
  g.drawImage(t.canvas as CanvasImageSource, 0, 0);
  const img = g.getImageData(0, 0, c.width, c.height), lut = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) lut[i] = 255 * (i / 255) ** gamma;
  for (let i = 0; i < img.data.length; i += 4) {
    img.data[i] = lut[img.data[i]]; img.data[i + 1] = lut[img.data[i + 1]]; img.data[i + 2] = lut[img.data[i + 2]];
  }
  g.putImageData(img, 0, 0);
  return c;
}

export interface Built {
  plan: Plan;
  grid: Int32Array;
  cellRGB: Float32Array;
  means: Float32Array;
  grayMean: number;
  groups: Int32Array;
  nDistinct: number;
  maxUses: number;
  crop: { x: number; y: number; w: number; h: number };
  src: OffscreenCanvas | HTMLCanvasElement;
  stats: TargetStats;
  settings: Settings;
}

/** Matching: the slow part. Redo it only when photos, target, size or grid change. */
export function build(lib: Library, target: Target, s: Settings): Built {
  const n = lib.photos.length;
  const plan = makePlan(s.widthIn, s.heightIn, s.dpi, s.cols, n);
  const src = gammaCanvas(target, s.gamma);
  const crop = cropRect(src.width, src.height, plan.W / plan.H, s.crop);
  // Average color of each cell of the target.
  const cc = new OffscreenCanvas(plan.cols, plan.rows);
  const cg = cc.getContext("2d", { willReadFrequently: true })!;
  cg.imageSmoothingQuality = "high";
  cg.drawImage(src as CanvasImageSource, crop.x, crop.y, crop.w, crop.h, 0, 0, plan.cols, plan.rows);
  const px = cg.getImageData(0, 0, plan.cols, plan.rows).data;
  const cellRGB = new Float32Array(plan.cols * plan.rows * 3);
  for (let i = 0; i < plan.cols * plan.rows; i++) {
    cellRGB[i * 3] = px[i * 4]; cellRGB[i * 3 + 1] = px[i * 4 + 1]; cellRGB[i * 3 + 2] = px[i * 4 + 2];
  }
  const means = new Float32Array(n * 3);
  lib.photos.forEach((p, i) => { means.set(p.mean, i * 3); });
  const groups = lookAlikeGroups(lib.photos.map((p) => p.dhash));
  const r = assignTiles(labArray(cellRGB), plan.rows, plan.cols, labArray(means), groups,
    { tint: s.tint, seed: s.seed });
  let gm = 0;
  for (let i = 0; i < cellRGB.length; i += 3) gm += luma(cellRGB[i], cellRGB[i + 1], cellRGB[i + 2]);
  gm = (gm / (cellRGB.length / 3)) * s.finish.brightness;
  return {
    plan, grid: r.grid, cellRGB, means, grayMean: gm, groups,
    nDistinct: groups.reduce((m, g) => Math.max(m, g), -1) + 1, maxUses: Math.max(...r.uses),
    crop, src, settings: s,
    stats: analyzeTarget(target.gray, target.gw, target.gh, target.width, target.height, plan.W, plan.H),
  };
}

export function findings(lib: Library, b: Built, s: Settings): Finding[] {
  return advise({
    plan: b.plan, printer: PRINTERS[s.printer], paper: PAPERS[s.paper], format: s.format, maxMB: s.maxMB,
    nPhotos: lib.photos.length, nDistinct: b.nDistinct, skipped: lib.skipped, target: b.stats,
    finishTouched: s.finishTouched,
  });
}

// ---- previews ------------------------------------------------------------------------

const thumbCache = new WeakMap<Library, ImageBitmap[]>();
async function thumbs(lib: Library): Promise<ImageBitmap[]> {
  let t = thumbCache.get(lib);
  if (!t || t.length !== lib.photos.length) {
    t = await Promise.all(lib.photos.map((p) =>
      createImageBitmap(new ImageData(p.thumb as Uint8ClampedArray<ArrayBuffer>, 32, 32))));
    thumbCache.set(lib, t);
  }
  return t;
}

const bigCache = new Map<string, ImageBitmap>();
async function tileAt(lib: Library, i: number, w: number, h: number, th: ImageBitmap[]) {
  if (Math.max(w, h) <= 32) return th[i];
  const key = `${lib.photos[i].name}|${i}|${w}x${h}`;
  let b = bigCache.get(key);
  if (!b) {
    b = await createImageBitmap(lib.photos[i].master, { resizeWidth: w, resizeHeight: h, resizeQuality: "high" });
    if (bigCache.size > 600) bigCache.clear();
    bigCache.set(key, b);
  }
  return b;
}

export interface Region { cx: number; cy: number; wIn: number; hIn: number } // centre + size, inches

/**
 * Render part of the poster at `ppi` pixels per printed inch. With `paper`, shows how it
 * will look printed on that paper (the whole poster is a region too).
 */
export async function renderRegion(lib: Library, b: Built, reg: Region, ppi: number,
  paperKey: string | null): Promise<ImageData> {
  const { plan, settings: s } = b;
  const PW = Math.round(plan.widthIn * ppi), PH = Math.round(plan.heightIn * ppi);
  const xe = edges(PW, plan.cols), ye = edges(PH, plan.rows);
  const w = Math.min(PW, Math.round(reg.wIn * ppi)), h = Math.min(PH, Math.round(reg.hIn * ppi));
  const x0 = Math.min(Math.max(0, Math.round(reg.cx * ppi - w / 2)), PW - w);
  const y0 = Math.min(Math.max(0, Math.round(reg.cy * ppi - h / 2)), PH - h);
  const c0 = xe.findIndex((_e, i) => i < plan.cols && xe[i + 1] > x0);
  let c1 = c0; while (c1 < plan.cols && xe[c1] < x0 + w) c1++;
  const r0 = ye.findIndex((_e, i) => i < plan.rows && ye[i + 1] > y0);
  let r1 = r0; while (r1 < plan.rows && ye[r1] < y0 + h) r1++;

  const th = await thumbs(lib);
  const cv = new OffscreenCanvas(w, h);
  const g = cv.getContext("2d", { willReadFrequently: true })!;
  const tw = Math.ceil(PW / plan.cols), tH = Math.ceil(PH / plan.rows);
  for (let r = r0; r < r1; r++) {
    for (let c = c0; c < c1; c++) {
      const tile = await tileAt(lib, b.grid[r * plan.cols + c], tw, tH, th);
      g.drawImage(tile, xe[c] - x0, ye[r] - y0, xe[c + 1] - xe[c], ye[r + 1] - ye[r]);
    }
  }
  const img = g.getImageData(0, 0, w, h);
  let ov: Uint8ClampedArray | null = null;
  if (s.overlay > 0) {
    const oc = new OffscreenCanvas(w, h), og = oc.getContext("2d", { willReadFrequently: true })!;
    og.imageSmoothingQuality = "high";
    const k = b.crop.w / PW;
    og.drawImage(b.src as CanvasImageSource, b.crop.x + x0 * k, b.crop.y + y0 * (b.crop.h / PH),
      w * k, h * (b.crop.h / PH), 0, 0, w, h);
    sharpen(og, w, h, tw / 3);
    ov = og.getImageData(0, 0, w, h).data;
  }
  composeStrip(img.data, ov, { W: w, x0, y0, h, cols: plan.cols, c0, c1, xe, ye, r0, r1, grid: b.grid,
    cellRGB: b.cellRGB, means: b.means, tint: s.tint, overlay: s.overlay, finish: s.finish, grayMean: b.grayMean });

  const paper = paperKey ? PAPERS[paperKey] : null;
  if (paper) {
    simulatePaper(img.data, paper);
    const blur = spreadPx(paper, ppi);
    if (blur >= 0.4) {
      const bc = new OffscreenCanvas(w, h), bg = bc.getContext("2d", { willReadFrequently: true })!;
      bg.putImageData(img, 0, 0);
      const out = new OffscreenCanvas(w, h).getContext("2d", { willReadFrequently: true })!;
      out.filter = `blur(${blur}px)`;
      out.drawImage(bc, 0, 0);
      return out.getImageData(0, 0, w, h);
    }
  }
  return img;
}

/** Where the face probably is, for the close-up previews (skin colour + detail + upper-middle). */
export function detailFocus(b: Built, tw: Target): { x: number; y: number } {
  const { gray, gw, gh } = tw;
  let best = -1, bx = 0.5, by = 0.4;
  for (let y = 3; y < gh - 3; y += 2) {
    for (let x = 3; x < gw - 3; x += 2) {
      let e = 0;
      for (let dy = -3; dy <= 3; dy += 3) for (let dx = -3; dx <= 3; dx += 3) {
        e += Math.abs(gray[(y + dy) * gw + x + dx] - gray[y * gw + x]);
      }
      const prior = Math.exp(-(((x / gw - 0.5) / 0.35) ** 2 + ((y / gh - 0.4) / 0.35) ** 2));
      if (e * prior > best) { best = e * prior; bx = x / gw; by = y / gh; }
    }
  }
  // Map from target space into the poster through the crop.
  const px = (bx * tw.canvas.width - b.crop.x) / b.crop.w, py = (by * tw.canvas.height - b.crop.y) / b.crop.h;
  return { x: Math.min(Math.max(px, 0.1), 0.9) * b.plan.widthIn, y: Math.min(Math.max(py, 0.1), 0.9) * b.plan.heightIn };
}

// ---- export ------------------------------------------------------------------------

export interface ExportPlan { pieces: { name: string; r0: number; r1: number }[] }

export function exportRequest(lib: Library, b: Built, s: Settings, opts: {
  panels: number; testStrip: boolean; base: string;
}): ExportRequest {
  const { plan } = b;
  const ext = s.format;
  const pieces: ExportRequest["pieces"] = [];
  if (opts.testStrip) {
    // A full-width slice, ~3 in tall, through the middle of the face area.
    const rows = Math.min(plan.rows, Math.max(2, Math.round(3 / (plan.heightIn / plan.rows))));
    const mid = Math.round(plan.rows * 0.42);
    const r0 = Math.min(Math.max(0, mid - Math.floor(rows / 2)), plan.rows - rows);
    pieces.push({ name: `${opts.base}.test-strip.${ext}`, r0, r1: r0 + rows });
  } else if (opts.panels > 1) {
    for (let i = 0; i < opts.panels; i++) {
      pieces.push({ name: `${opts.base}_part${i + 1}of${opts.panels}.${ext}`,
        r0: Math.round((i * plan.rows) / opts.panels), r1: Math.round(((i + 1) * plan.rows) / opts.panels) });
    }
  } else pieces.push({ name: `${opts.base}.${ext}`, r0: 0, r1: plan.rows });
  return {
    W: plan.W, H: plan.H, dpi: plan.dpi, cols: plan.cols, rows: plan.rows, grid: b.grid, cellRGB: b.cellRGB,
    means: b.means, masters: lib.photos.map((p) => p.master), target: null as unknown as ImageBitmap,
    crop: b.crop, tint: s.tint, overlay: s.overlay, finish: s.finish, grayMean: b.grayMean,
    format: s.format, maxMB: s.maxMB, pieces,
  };
}
