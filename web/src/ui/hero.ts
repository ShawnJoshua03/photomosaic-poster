// Landing hero: a small, honest photo mosaic. It invents ~56 little "photos" on offscreen canvases,
// then builds a bigger picture out of them the way the real tool does: each cell gets the tile whose
// average colour is closest, tinted a little toward the cell's colour. No image files are loaded.
// Decorative only: the page works without it, and with reduced motion the finished picture is drawn once.

type RGB = [number, number, number];

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
const easeOutBack = (t: number) => { const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2; };
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

/** Small seeded generator so the demo looks the same on every visit. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const hsl = (h: number, s: number, l: number) => `hsl(${((h % 360) + 360) % 360} ${s * 100}% ${l * 100}%)`;
const TS = 40; // tile pixel size

interface Photo { canvas: HTMLCanvasElement; avg: RGB; uses: number }

/** One made-up photo. The index picks the scene; hue and lightness vary so the set covers many colours. */
function makePhoto(i: number, rand: () => number): Photo {
  const c = document.createElement("canvas");
  c.width = c.height = TS;
  const g = c.getContext("2d", { willReadFrequently: true })!;
  const hue = (i * 137.5) % 360, light = 0.22 + (((i * 7) % 11) / 11) * 0.58, sat = 0.45 + rand() * 0.45;
  const kind = i % 4;
  if (kind === 0) { // sky, hills, sun
    g.fillStyle = hsl(hue, sat, Math.min(0.9, light + 0.12)); g.fillRect(0, 0, TS, TS);
    g.fillStyle = hsl(hue + 50, 0.9, 0.65); g.beginPath(); g.arc(8 + rand() * 24, 9 + rand() * 6, 5 + rand() * 3, 0, 7); g.fill();
    g.fillStyle = hsl(hue + 120, sat, light * 0.7);
    g.beginPath(); g.moveTo(0, TS); g.lineTo(0, 26); g.quadraticCurveTo(14, 12 + rand() * 8, 26, 26); g.quadraticCurveTo(34, 20, TS, 28); g.lineTo(TS, TS); g.fill();
  } else if (kind === 1) { // stripes
    const n = 3 + Math.floor(rand() * 4), vert = rand() < 0.5;
    for (let s = 0; s < n; s++) {
      g.fillStyle = hsl(hue + s * 22, sat, clamp(light + (s % 2 ? 0.14 : -0.1), 0.1, 0.9));
      if (vert) g.fillRect((s * TS) / n, 0, TS / n + 1, TS); else g.fillRect(0, (s * TS) / n, TS, TS / n + 1);
    }
  } else if (kind === 2) { // shapes on a field
    g.fillStyle = hsl(hue, sat, light); g.fillRect(0, 0, TS, TS);
    g.fillStyle = hsl(hue + 180, sat, clamp(light + 0.25, 0.2, 0.92));
    g.beginPath(); g.arc(12 + rand() * 16, 12 + rand() * 16, 7 + rand() * 6, 0, 7); g.fill();
    g.fillStyle = hsl(hue + 30, sat, clamp(light - 0.15, 0.08, 0.8));
    const x = rand() * 22, y = 18 + rand() * 12;
    g.beginPath(); g.moveTo(x, y + 12); g.lineTo(x + 9, y - 2); g.lineTo(x + 18, y + 12); g.fill();
  } else { // noisy field with a simple subject (a little house)
    g.fillStyle = hsl(hue, sat, light); g.fillRect(0, 0, TS, TS);
    for (let k = 0; k < 160; k++) {
      g.fillStyle = `rgba(${rand() < 0.5 ? "255,255,255" : "0,0,0"},${0.05 + rand() * 0.1})`;
      g.fillRect(rand() * TS, rand() * TS, 2, 2);
    }
    g.fillStyle = hsl(hue + 25, 0.7, clamp(light + 0.3, 0.3, 0.92)); g.fillRect(11, 19, 18, 13);
    g.fillStyle = hsl(hue + 200, 0.6, 0.3); g.beginPath(); g.moveTo(8, 20); g.lineTo(20, 8); g.lineTo(32, 20); g.fill();
  }
  const d = g.getImageData(0, 0, TS, TS).data;
  let r = 0, gg = 0, b = 0;
  for (let p = 0; p < d.length; p += 4) { r += d[p]; gg += d[p + 1]; b += d[p + 2]; }
  const n = d.length / 4;
  return { canvas: c, avg: [r / n, gg / n, b / n], uses: 0 };
}

/** The big picture, as a colour for each cell: a sunset over hills with a sun. u, v run 0..1. */
function target(u: number, v: number): RGB {
  const sun = Math.hypot(((u - 0.62) * 4) / 3, v - 0.5);
  if (sun < 0.17) return [255, 214, 70];
  const hill1 = 0.78 + 0.07 * Math.sin(u * 6.5 + 1), hill2 = 0.68 + 0.09 * Math.sin(u * 4 + 3.5);
  if (v > hill1) return [28, 40, 92];
  if (v > hill2) return [196, 70, 52];
  const t = clamp(v / 0.7, 0, 1);
  const glow = clamp(1 - sun * 2.2, 0, 1) * 0.5;
  return [clamp(90 + 165 * t + 40 * glow, 0, 255), clamp(60 + 100 * t + 90 * glow, 0, 255), clamp(170 - 100 * t, 0, 255)];
}

interface Cell { x: number; y: number; photo: Photo; tint: RGB; delay: number }

export function initHero(): void {
  const art = document.getElementById("hero-art");
  const canvas = document.getElementById("hero-canvas") as HTMLCanvasElement | null;
  const cta = document.getElementById("start");
  const ctx = canvas?.getContext("2d");

  // "Make a poster" scrolls to the tool. The plain anchor link still works if this never runs.
  cta?.addEventListener("click", (e) => {
    const tool = document.getElementById("s-photos");
    if (!tool) return;
    e.preventDefault();
    tool.scrollIntoView({ behavior: reduce.matches ? "auto" : "smooth", block: "start" });
    document.getElementById("drop")?.focus({ preventScroll: true });
  });

  if (!art || !canvas || !ctx) return;

  const COLS = 28, ROWS = 21;
  const rand = rng(7);
  const photos = Array.from({ length: 56 }, (_, i) => makePhoto(i, rand));
  const cap = document.getElementById("hero-cap");
  if (cap) cap.textContent = `${COLS * ROWS} cells, ${photos.length} made-up photos, all drawn by code. Hover one.`;

  // Match each cell to the nearest tile; a small penalty for reuse keeps the set varied, like the real tool.
  const cells: Cell[] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const tint = target((c + 0.5) / COLS, (r + 0.5) / ROWS);
      let best = photos[0], bestD = Infinity;
      for (const p of photos) {
        const d = (p.avg[0] - tint[0]) ** 2 * 0.3 + (p.avg[1] - tint[1]) ** 2 * 0.59 + (p.avg[2] - tint[2]) ** 2 * 0.11 + p.uses * 90;
        if (d < bestD) { bestD = d; best = p; }
      }
      best.uses++;
      cells.push({ x: c, y: r, photo: best, tint, delay: rand() * 1300 });
    }
  }

  let W = 0, H = 0, cw = 0, dpr = 1;
  let start = 0, raf = 0, onScreen = true, hover = -1;
  const DUR = 520, TOTAL = 1300 + DUR;
  const ink = () => getComputedStyle(document.documentElement).getPropertyValue("--edge").trim() || "#111";
  const animating = (now: number) => start > 0 && now - start < TOTAL && !reduce.matches;

  /** Returns true when the canvas backing store changed. */
  function size() {
    const w = canvas!.clientWidth, h = canvas!.clientHeight;
    if (!w || !h) return false;
    dpr = window.devicePixelRatio || 1;
    if (w === W && h === H && canvas!.width === Math.round(w * dpr)) return false;
    W = w; H = h; cw = W / COLS;
    canvas!.width = Math.round(W * dpr); canvas!.height = Math.round(H * dpr);
    return true;
  }

  function drawCell(cell: Cell, scale: number, tintAlpha: number) {
    const s = cw * scale, px = (cell.x + 0.5) * cw - s / 2, py = (cell.y + 0.5) * cw - s / 2;
    ctx!.drawImage(cell.photo.canvas, px, py, s + 0.5, s + 0.5);
    ctx!.globalAlpha = tintAlpha;
    ctx!.fillStyle = `rgb(${cell.tint[0] | 0},${cell.tint[1] | 0},${cell.tint[2] | 0})`;
    ctx!.fillRect(px, py, s + 0.5, s + 0.5);
    ctx!.globalAlpha = 1;
  }

  function draw(now: number) {
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx!.clearRect(0, 0, W, H);
    const settled = !animating(now);
    cells.forEach((cell, i) => {
      if (i === hover && settled) return; // drawn last, bigger
      const p = settled ? 1 : clamp((now - start - cell.delay) / DUR, 0, 1);
      if (p <= 0) return;
      // Tiles land nearly untinted, then take on the picture's colour as they settle.
      drawCell(cell, settled ? 1 : easeOutBack(p), 0.18 + 0.3 * p);
    });
    if (hover >= 0 && settled) {
      const cell = cells[hover], s = cw * 3.2;
      const cx = clamp((cell.x + 0.5) * cw, s / 2 + 4, W - s / 2 - 10), cy = clamp((cell.y + 0.5) * cw, s / 2 + 4, H - s / 2 - 10);
      const x = cx - s / 2, y = cy - s / 2;
      ctx!.fillStyle = ink(); ctx!.fillRect(x + 6, y + 6, s, s); // hard shadow
      ctx!.drawImage(cell.photo.canvas, x, y, s, s);
      ctx!.lineWidth = 3; ctx!.strokeStyle = ink(); ctx!.strokeRect(x, y, s, s);
    }
  }

  function loop(now: number) {
    raf = 0;
    draw(now);
    if (animating(now) && !document.hidden && onScreen) raf = requestAnimationFrame(loop);
  }
  function kick() { if (!raf) raf = requestAnimationFrame(loop); }

  // Build up the first time the hero is on screen; with reduced motion go straight to the finished picture.
  function begin() {
    if (start || !W) return;
    start = reduce.matches ? -1 : performance.now();
    kick();
  }

  new ResizeObserver(() => { if (size()) { if (start) kick(); else if (onScreen) begin(); } }).observe(canvas);
  new IntersectionObserver(([e]) => {
    onScreen = e.isIntersecting;
    if (onScreen) { size(); if (start) kick(); else begin(); }
  }).observe(art);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && start) kick(); });
  reduce.addEventListener("change", () => { if (reduce.matches) start = -1; kick(); });

  // offsetX/Y are in the canvas's own (unrotated) coordinates, so the tilted frame needs no maths.
  canvas.addEventListener("pointermove", (e) => {
    if (!W) return;
    const c = Math.floor((e.offsetX / canvas.clientWidth) * COLS), r = Math.floor((e.offsetY / canvas.clientHeight) * ROWS);
    const idx = c >= 0 && c < COLS && r >= 0 && r < ROWS ? r * COLS + c : -1;
    if (idx !== hover) { hover = idx; kick(); }
  });
  canvas.addEventListener("pointerleave", () => { hover = -1; kick(); });
}
