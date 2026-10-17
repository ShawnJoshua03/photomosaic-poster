// Camera RAW files (CR2, NEF, ARW, DNG, ...) can't be decoded natively by browsers,
// but nearly all of them embed a full-size JPEG preview made by the camera. For a
// mosaic tile that preview is plenty, so we find the largest embedded JPEG.

export const RAW_EXTS = new Set(["dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2",
  "raf", "orf", "rw2", "pef", "srw", "x3f", "3fr", "erf", "kdc", "mrw", "raw", "iiq"]);

/** Returns the largest complete JPEG inside `bytes`, or null. */
export function extractEmbeddedJpeg(bytes: Uint8Array): Uint8Array | null {
  let best: [number, number] | null = null;
  for (let i = 0; i < bytes.length - 3; i++) {
    // SOI followed by a marker (APPn/DQT/SOF...): the start of a JPEG stream.
    if (bytes[i] !== 0xff || bytes[i + 1] !== 0xd8 || bytes[i + 2] !== 0xff) continue;
    const end = findEnd(bytes, i + 2);
    if (end > 0 && (!best || end - i > best[1] - best[0])) best = [i, end];
    if (end > 0) i = end - 1;
  }
  return best ? bytes.subarray(best[0], best[1]) : null;
}

/** Walk JPEG segments from `p` to the end of the image; returns the byte after EOI. */
function findEnd(b: Uint8Array, p: number): number {
  while (p + 4 <= b.length) {
    if (b[p] !== 0xff) return -1;
    const m = b[p + 1];
    if (m === 0xd9) return p + 2;              // EOI
    if (m === 0xff) { p++; continue; }         // fill byte
    const len = (b[p + 2] << 8) | b[p + 3];
    if (len < 2) return -1;
    p += 2 + len;
    if (m === 0xda) {                          // SOS: entropy data until next marker
      while (p + 1 < b.length) {
        if (b[p] === 0xff && b[p + 1] !== 0 && !(b[p + 1] >= 0xd0 && b[p + 1] <= 0xd7)) break;
        p++;
      }
    }
  }
  return -1;
}
