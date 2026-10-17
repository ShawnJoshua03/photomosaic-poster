// Getting photos in: folders, loose files and .zip downloads, decoded by a pool of
// workers, with duplicates dropped and everything skipped explained.

import { Unzip, UnzipInflate } from "fflate";
import type { DecodeRequest, DecodeResult } from "./decode.worker";
import { RAW_EXTS } from "./raw";

export interface Photo {
  name: string;
  master: Blob;
  thumb: Uint8ClampedArray; // 32x32 RGBA
  mean: [number, number, number];
  dhash: Uint8Array;
}

export interface Library { photos: Photo[]; skipped: Record<string, number> }

const IMAGE_EXTS = new Set(["jpg", "jpeg", "jpe", "jfif", "png", "webp", "gif", "bmp", "avif",
  "heic", "heif", "hif", "tif", "tiff"]);
const VIDEO_EXTS = new Set(["mov", "mp4", "m4v", "avi", "mkv", "webm", "3gp"]);
const MAX_FILE = 2_000_000_000;
const JUNK = /(^|\/)(__MACOSX|\.|Thumbs\.db|desktop\.ini)/;

const ext = (n: string) => n.split(".").pop()?.toLowerCase() ?? "";

export interface Progress { found: number; done: number; added: number; current?: string }

/** Turn a drop or file-picker selection into named blobs (zips expanded, junk dropped). */
export async function collectFiles(items: (File | FileSystemEntry)[],
  skipped: Record<string, number>, onFound: (n: number) => void): Promise<{ name: string; blob: Blob }[]> {
  const out: { name: string; blob: Blob }[] = [];
  const skip = (why: string) => { skipped[why] = (skipped[why] ?? 0) + 1; };
  const consider = async (name: string, blob: Blob) => {
    if (JUNK.test(name)) return;
    const e = ext(name);
    if (e === "zip") { await unzip(blob, consider, skip); return; }
    if (blob.size > MAX_FILE) return skip("file over 2 GB");
    if (IMAGE_EXTS.has(e) || RAW_EXTS.has(e)) { out.push({ name: name.split("/").pop()!, blob }); onFound(out.length); }
    else if (VIDEO_EXTS.has(e)) skip("video (the web version uses photos only)");
    else skip("not a photo");
  };
  for (const it of items) {
    if (it instanceof File) await consider(it.webkitRelativePath || it.name, it);
    else await walk(it, consider);
  }
  return out;
}

async function walk(entry: FileSystemEntry, consider: (n: string, b: Blob) => Promise<void>) {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    await consider(entry.fullPath.replace(/^\//, ""), file);
  } else if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    for (;;) { // readEntries returns batches; keep going until empty
      const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
      if (!batch.length) break;
      for (const e of batch) await walk(e, consider);
    }
  }
}

/** Stream a zip (Google Drive / iCloud downloads can be gigabytes) without loading it whole. */
async function unzip(blob: Blob, consider: (n: string, b: Blob) => Promise<void>,
  skip: (why: string) => void) {
  const found: Promise<void>[] = [];
  const uz = new Unzip();
  uz.register(UnzipInflate);
  uz.onfile = (f) => {
    const e = ext(f.name);
    if (f.name.endsWith("/") || JUNK.test(f.name)) return;
    if (!(IMAGE_EXTS.has(e) || RAW_EXTS.has(e) || e === "zip")) {
      skip(VIDEO_EXTS.has(e) ? "video (the web version uses photos only)" : "not a photo");
      return; // not started -> its data is skipped
    }
    if ((f.originalSize ?? 0) > MAX_FILE) return skip("file over 2 GB");
    const chunks: Uint8Array[] = [];
    found.push(new Promise<void>((resolve) => {
      f.ondata = (err, data, final) => {
        if (err) { skip("damaged file in zip"); resolve(); return; }
        chunks.push(data);
        if (final) consider(f.name, new Blob(chunks as BlobPart[])).then(resolve);
      };
    }));
    f.start();
  };
  const reader = blob.stream().getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) { uz.push(new Uint8Array(0), true); break; }
    uz.push(value);
  }
  await Promise.all(found);
}

/** Decode everything with a worker pool. Exact duplicates (same bytes) are dropped. */
export async function decodeAll(files: { name: string; blob: Blob }[], lib: Library,
  onProgress: (p: Progress) => void): Promise<void> {
  const nWorkers = Math.max(1, Math.min(6, (navigator.hardwareConcurrency || 4) - 1));
  const workers = Array.from({ length: nWorkers },
    () => new Worker(new URL("./decode.worker.ts", import.meta.url), { type: "module" }));
  const seen = new Set<string>();
  let next = 0, done = 0;
  const skip = (why: string) => { lib.skipped[why] = (lib.skipped[why] ?? 0) + 1; };

  await Promise.all(workers.map((w) => new Promise<void>((resolve) => {
    const feed = () => {
      if (next >= files.length) { w.terminate(); resolve(); return; }
      const id = next++;
      w.postMessage({ id, name: files[id].name, blob: files[id].blob } satisfies DecodeRequest);
    };
    w.onmessage = (ev: MessageEvent<DecodeResult>) => {
      const r = ev.data;
      done++;
      if (!r.ok) skip(r.reason === "image too large" ? "image too large" : "unreadable or damaged");
      else if (seen.has(r.sha)) skip("exact duplicate");
      else {
        seen.add(r.sha);
        lib.photos.push({ name: files[r.id].name, master: r.master, thumb: new Uint8ClampedArray(r.thumb),
          mean: r.mean, dhash: r.dhash });
      }
      onProgress({ found: files.length, done, added: lib.photos.length, current: files[r.id].name });
      feed();
    };
    w.onerror = () => { done++; skip("unreadable or damaged"); feed(); };
    feed();
  })));
}
