/// <reference lib="webworker" />
// Decodes one photo at a time, off the main thread, into what the app keeps:
//   master: a 320 px square JPEG (enough for 0.5-1 inch tiles at 300 DPI)
//   thumb:  32 x 32 RGBA, for live previews
//   mean:   average color of the middle 80%, for matching
//   dhash:  8-byte look-alike fingerprint (bursts and retakes)
// so thousands of photos fit in memory and the originals can be let go.

import { extractEmbeddedJpeg, RAW_EXTS } from "./raw";

export const MASTER = 320;
export const THUMB = 32;
const MAX_PIXELS = 400_000_000; // refuse "decompression bombs"

export interface DecodeRequest { id: number; name: string; blob: Blob }
export type DecodeResult =
  | { id: number; ok: true; sha: string; master: Blob; thumb: ArrayBuffer; mean: [number, number, number];
      dhash: Uint8Array; width: number; height: number }
  | { id: number; ok: false; reason: string };

const ext = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

async function toBitmap(name: string, blob: Blob, bytes: Uint8Array): Promise<ImageBitmap> {
  const e = ext(name);
  let src: Blob = blob;
  if (RAW_EXTS.has(e)) {
    const jpg = extractEmbeddedJpeg(bytes);
    if (!jpg) throw new Error("no preview inside this RAW file");
    src = new Blob([jpg as BlobPart], { type: "image/jpeg" });
  }
  try {
    return await createImageBitmap(src, { imageOrientation: "from-image" });
  } catch (err) {
    if (e === "heic" || e === "heif" || e === "hif") {
      const { heicTo } = await import("heic-to"); // ~3 MB, loaded only when needed
      return heicTo({ blob: src, type: "bitmap", options: { imageOrientation: "from-image" } });
    }
    throw err;
  }
}

async function decode(req: DecodeRequest): Promise<DecodeResult> {
  const bytes = new Uint8Array(await req.blob.arrayBuffer());
  const shaBuf = await crypto.subtle.digest("SHA-256", bytes);
  const sha = [...new Uint8Array(shaBuf).slice(0, 16)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const bmp = await toBitmap(req.name, req.blob, bytes);
  const { width, height } = bmp;
  if (width * height > MAX_PIXELS) {
    bmp.close();
    return { id: req.id, ok: false, reason: "image too large" };
  }
  // Square crop, slightly above center: faces usually sit in the upper half.
  const side = Math.min(width, height);
  const sx = (width - side) / 2, sy = Math.max(0, Math.min(height - side, (height - side) * 0.4));
  const c = new OffscreenCanvas(MASTER, MASTER);
  const g = c.getContext("2d")!;
  g.imageSmoothingQuality = "high";
  g.drawImage(bmp, sx, sy, side, side, 0, 0, MASTER, MASTER);
  bmp.close();
  const master = await c.convertToBlob({ type: "image/jpeg", quality: 0.9 });

  const t = new OffscreenCanvas(THUMB, THUMB);
  const tg = t.getContext("2d", { willReadFrequently: true })!;
  tg.imageSmoothingQuality = "high";
  tg.drawImage(c, 0, 0, THUMB, THUMB);
  const thumb = tg.getImageData(0, 0, THUMB, THUMB).data;

  let r = 0, gr = 0, b = 0, n = 0;
  const m = Math.round(THUMB * 0.1);
  for (let y = m; y < THUMB - m; y++) {
    for (let x = m; x < THUMB - m; x++) {
      const i = (y * THUMB + x) * 4;
      r += thumb[i]; gr += thumb[i + 1]; b += thumb[i + 2]; n++;
    }
  }

  // Difference hash: is each pixel brighter than its right-hand neighbour (9x8 gray)?
  const h = new OffscreenCanvas(9, 8);
  const hg = h.getContext("2d", { willReadFrequently: true })!;
  hg.drawImage(c, 0, 0, 9, 8);
  const hp = hg.getImageData(0, 0, 9, 8).data;
  const dhash = new Uint8Array(8);
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 8; x++) {
      const i = (y * 9 + x) * 4, j = i + 4;
      const a = hp[i] + hp[i + 1] + hp[i + 2], bb = hp[j] + hp[j + 1] + hp[j + 2];
      if (bb > a) dhash[y] |= 1 << x;
    }
  }
  return { id: req.id, ok: true, sha, master, thumb: thumb.buffer as ArrayBuffer,
    mean: [r / n, gr / n, b / n], dhash, width, height };
}

self.onmessage = async (ev: MessageEvent<DecodeRequest>) => {
  let res: DecodeResult;
  try {
    res = await decode(ev.data);
  } catch (e) {
    res = { id: ev.data.id, ok: false, reason: e instanceof Error ? e.message : String(e) };
  }
  (self as unknown as Worker).postMessage(res, res.ok ? [res.thumb] : []);
};
