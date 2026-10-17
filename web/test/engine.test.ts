import { describe, expect, it } from "vitest";
import { advise } from "../src/engine/advice";
import { assignTiles, lookAlikeGroups, rng } from "../src/engine/assign";
import { applyFinish, labArray, srgbToLab } from "../src/engine/color";
import { cropRect } from "../src/engine/compose";
import { autoCols, edges, makePlan } from "../src/engine/layout";
import { buildPdf } from "../src/engine/pdf";
import { PAPERS, PRINTERS } from "../src/engine/presets";
import { extractEmbeddedJpeg } from "../src/engine/raw";

const randomColors = (n: number, seed: number) => {
  const r = rng(seed), a = new Float32Array(n * 3);
  for (let i = 0; i < a.length; i++) a[i] = r() * 255;
  return a;
};

describe("color", () => {
  it("converts to Lab like the Python version", () => {
    const [L, a, b] = srgbToLab(255, 255, 255);
    expect(L).toBeCloseTo(100, 0); expect(Math.abs(a)).toBeLessThan(0.5); expect(Math.abs(b)).toBeLessThan(0.5);
    expect(srgbToLab(0, 0, 0)[0]).toBeCloseTo(0, 1);
    expect(srgbToLab(255, 0, 0)[0]).toBeCloseTo(53.2, 0);
  });
  it("leaves pixels alone when nothing changes, and brightens when asked", () => {
    const px = new Uint8ClampedArray([100, 100, 100, 255]);
    applyFinish(px, { brightness: 1, contrast: 1, saturation: 1 }, 128);
    expect([...px]).toEqual([100, 100, 100, 255]);
    applyFinish(px, { brightness: 1.2, contrast: 1, saturation: 1 }, 128);
    expect(px[0]).toBe(120);
  });
});

describe("layout", () => {
  it("fills the page exactly with tile edges", () => {
    const e = edges(10800, 66);
    expect(e[0]).toBe(0); expect(e[66]).toBe(10800);
    const widths = [...e].slice(1).map((v, i) => v - e[i]);
    expect(Math.max(...widths) - Math.min(...widths)).toBeLessThanOrEqual(1);
  });
  it("plans a 36x54 poster at 300 DPI", () => {
    const p = makePlan(36, 54, 300, 66, 2000);
    expect([p.W, p.H, p.rows]).toEqual([10800, 16200, 99]);
  });
  it("picks about 0.5 inch tiles, fewer with few photos", () => {
    expect(autoCols(36, 54, 3000)).toBe(72);
    expect(autoCols(36, 54, 100)).toBeLessThan(20);
  });
  it("crops the target to the poster shape and respects the zoom", () => {
    const c = cropRect(1000, 2000, 1, { zoom: 1, fx: 0.5, fy: 0.5 });
    expect(c.w).toBe(1000); expect(c.h).toBe(1000); expect(c.y).toBe(500);
    expect(cropRect(1000, 2000, 1, { zoom: 2, fx: 0, fy: 0 }).x).toBe(0);
  });
});

describe("matching", () => {
  const rows = 12, cols = 10, n = 60;
  const cells = labArray(randomColors(rows * cols, 1)), tiles = labArray(randomColors(n, 2));
  const groups = Int32Array.from({ length: n }, (_, i) => i);

  it("fills every cell, caps repeats and is reproducible", () => {
    const r = assignTiles(cells, rows, cols, tiles, groups, { maxRepeats: 3, spacing: 2 });
    expect(Math.min(...r.grid)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...r.uses)).toBeLessThanOrEqual(3);
    const again = assignTiles(cells, rows, cols, tiles, groups, { maxRepeats: 3, spacing: 2 });
    expect([...again.grid]).toEqual([...r.grid]);
    const other = assignTiles(cells, rows, cols, tiles, groups, { maxRepeats: 3, spacing: 2, seed: 9 });
    expect([...other.grid]).not.toEqual([...r.grid]);
  });
  it("never repeats a photo within the spacing", () => {
    const sp = 2, { grid } = assignTiles(cells, rows, cols, tiles, groups, { spacing: sp });
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      let same = 0;
      for (let y = Math.max(0, r - sp); y <= Math.min(rows - 1, r + sp); y++)
        for (let x = Math.max(0, c - sp); x <= Math.min(cols - 1, c + sp); x++)
          if (grid[y * cols + x] === grid[r * cols + c]) same++;
      expect(same).toBe(1);
    }
  });
  it("keeps look-alikes apart and uses every distinct photo", () => {
    const pairs = Int32Array.from({ length: n }, (_, i) => Math.floor(i / 2));
    const { grid } = assignTiles(cells, rows, cols, tiles, pairs, { spacing: 1 });
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      let same = 0;
      for (let y = Math.max(0, r - 1); y <= Math.min(rows - 1, r + 1); y++)
        for (let x = Math.max(0, c - 1); x <= Math.min(cols - 1, c + 1); x++)
          if (pairs[grid[y * cols + x]] === pairs[grid[r * cols + c]]) same++;
      expect(same).toBe(1);
    }
    expect(new Set([...pairs].map((_, i) => pairs[i]).filter((g) => [...grid].some((t) => pairs[t] === g))).size).toBe(30);
  });
  it("still fills the grid with too few photos", () => {
    const r = assignTiles(labArray(randomColors(25, 3)), 5, 5, labArray(randomColors(3, 4)), Int32Array.from([0, 1, 2]), { maxRepeats: 2 });
    expect(Math.min(...r.grid)).toBeGreaterThanOrEqual(0);
  });
  it("groups near-identical hashes", () => {
    const a = Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8]), b = Uint8Array.from(a); b[0] ^= 1;
    const c = Uint8Array.from([255, 0, 255, 0, 255, 0, 255, 0]);
    const g = lookAlikeGroups([a, b, c]);
    expect(g[0]).toBe(g[1]); expect(g[2]).not.toBe(g[0]);
  });
});

describe("advice", () => {
  const base = { plan: makePlan(48, 36, 300, 0, 100), format: "pdf" as const, maxMB: 0, nPhotos: 100,
    nDistinct: 100, skipped: {}, finishTouched: false };
  it("stops a poster that is too wide for the roll and suggests the fix", () => {
    const f = advise({ ...base, printer: PRINTERS["plotter-bond"], paper: PAPERS.bond });
    const err = f.find((x) => x.level === "error")!;
    expect(err.fix).toContain("36 x 48");
  });
  it("rejects a format the printer doesn't take and asks for the size limit", () => {
    const f = advise({ ...base, plan: makePlan(36, 54, 300, 0, 3000), printer: PRINTERS["photo-lab"], format: "pdf" });
    expect(f.some((x) => x.level === "error" && /PDF/.test(x.title))).toBe(true);
    const g = advise({ ...base, plan: makePlan(36, 54, 300, 0, 3000), printer: PRINTERS["plotter-bond"], paper: PAPERS.bond });
    expect(g.some((x) => /under 75 MB/.test(x.title))).toBe(true);
  });
  it("warns about too many repeats and tiny tiles", () => {
    const f = advise({ ...base, plan: makePlan(36, 54, 300, 200, 100), nPhotos: 100 });
    expect(f.some((x) => /would appear/.test(x.title))).toBe(true);
    expect(f.some((x) => /across/.test(x.title))).toBe(true);
  });
  it("orders errors first", () => {
    const f = advise({ ...base, printer: PRINTERS["plotter-bond"] });
    expect(f[0].level).toBe("error");
  });
});

describe("pdf", () => {
  it("writes a one-page file at exactly the print size", async () => {
    const strips = [0, 100].map((y) => ({ jpeg: new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])]), widthPx: 300, heightPx: 100, yPx: y }));
    // One byte per character, so string offsets equal byte offsets (JPEG data isn't UTF-8).
    const text = new TextDecoder("latin1").decode(await buildPdf(300, 200, 100, strips).arrayBuffer());
    expect(text.startsWith("%PDF-1.4")).toBe(true);
    expect(text).toContain("/MediaBox [0 0 216 144]");   // 3 x 2 in
    expect(text).toContain("/Filter /DCTDecode");
    expect((text.match(/\/Subtype \/Image/g) ?? []).length).toBe(2);
    expect(text.trimEnd().endsWith("%%EOF")).toBe(true);
    // The xref offset must really point at the xref table.
    const start = parseInt(/startxref\n(\d+)/.exec(text)![1], 10);
    expect(text.slice(start, start + 4)).toBe("xref");
    // ...and every object offset must point at its "N 0 obj".
    const table = text.slice(start).split("\n").slice(3, 3 + 6);
    table.forEach((line, i) => {
      const off = parseInt(line.slice(0, 10), 10);
      expect(text.slice(off, off + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`);
    });
  });
});

describe("raw", () => {
  it("finds the largest embedded JPEG", () => {
    const jpg = (n: number) => [0xff, 0xd8, 0xff, 0xe0, 0, 4, 0, 0, 0xff, 0xda, 0, 2, ...new Array(n).fill(7), 0xff, 0xd9];
    const raw = Uint8Array.from([...new Array(50).fill(1), ...jpg(10), ...new Array(30).fill(2), ...jpg(200), 9, 9]);
    const found = extractEmbeddedJpeg(raw)!;
    expect(found.length).toBe(jpg(200).length);
    expect(extractEmbeddedJpeg(Uint8Array.from([1, 2, 3, 4]))).toBeNull();
  });
});
