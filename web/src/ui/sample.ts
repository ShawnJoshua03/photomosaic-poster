// "Try with sample photos": made-up pictures and a big picture drawn on canvases, so the whole tool can be
// tried in one click with no files and no network. Nothing here touches the mosaic engine; the results go
// through the same decode and build path as photos the person adds.

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
const hsl = (h: number, s: number, l: number) => `hsl(${((h % 360) + 360) % 360} ${s * 100}% ${l * 100}%)`;

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

const toBlob = (c: HTMLCanvasElement, q: number) =>
  new Promise<Blob>((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("no image"))), "image/jpeg", q));

/** A postcard scene: sky, sun, hills and a couple of little figures. Hue and lightness cover the colour wheel. */
function drawPhoto(g: CanvasRenderingContext2D, S: number, i: number, rand: () => number) {
  const hue = (i * 137.5) % 360, light = 0.2 + (((i * 7) % 13) / 13) * 0.62, sat = 0.4 + rand() * 0.5;
  const sky = g.createLinearGradient(0, 0, 0, S);
  sky.addColorStop(0, hsl(hue, sat, clamp(light + 0.12, 0.08, 0.92)));
  sky.addColorStop(1, hsl(hue + 25, sat * 0.8, clamp(light - 0.06, 0.05, 0.9)));
  g.fillStyle = sky; g.fillRect(0, 0, S, S);
  g.fillStyle = hsl(hue + 45, 0.9, 0.7);
  g.beginPath(); g.arc(S * (0.2 + rand() * 0.6), S * (0.15 + rand() * 0.2), S * (0.07 + rand() * 0.08), 0, 7); g.fill();
  g.fillStyle = hsl(hue + 130, sat, clamp(light * 0.6, 0.06, 0.6));
  g.beginPath(); g.moveTo(0, S); g.lineTo(0, S * 0.65);
  g.quadraticCurveTo(S * 0.3, S * (0.45 + rand() * 0.2), S * 0.55, S * 0.68);
  g.quadraticCurveTo(S * 0.8, S * 0.55, S, S * 0.7); g.lineTo(S, S); g.fill();
  for (let k = 0, n = 1 + Math.floor(rand() * 3); k < n; k++) {
    const x = S * (0.15 + rand() * 0.7), y = S * (0.78 + rand() * 0.1);
    g.fillStyle = hsl(rand() * 360, 0.6, 0.5); g.fillRect(x - S * 0.04, y - S * 0.12, S * 0.08, S * 0.12);
    g.fillStyle = "#f0c8a8"; g.beginPath(); g.arc(x, y - S * 0.16, S * 0.035, 0, 7); g.fill();
  }
}

/** A bold target: a heart at sunset over dark hills, 3:4 portrait. */
function drawTarget(g: CanvasRenderingContext2D, w: number, h: number) {
  const sky = g.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, "#ffb05a"); sky.addColorStop(1, "#c3407a");
  g.fillStyle = sky; g.fillRect(0, 0, w, h);
  g.fillStyle = "#ffe08c"; g.beginPath(); g.arc(w * 0.5, h * 0.2, w * 0.15, 0, 7); g.fill();
  g.fillStyle = "#c8143c"; g.beginPath();
  for (let i = 0; i <= 200; i++) {
    const t = (i / 200) * Math.PI * 2;
    const x = w / 2 + 16 * Math.sin(t) ** 3 * (w / 40);
    const y = h * 0.55 - (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) * (w / 40);
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  }
  g.fill();
  g.fillStyle = "#281940"; g.beginPath();
  g.moveTo(0, h); g.lineTo(0, h * 0.8); g.lineTo(w * 0.3, h * 0.72); g.lineTo(w * 0.6, h * 0.85); g.lineTo(w, h * 0.75); g.lineTo(w, h); g.fill();
}

export async function makeSamples(count = 240): Promise<{ photos: File[]; target: File }> {
  const rand = rng(23);
  const c = document.createElement("canvas");
  c.width = c.height = 160;
  const g = c.getContext("2d")!;
  const photos: File[] = [];
  for (let i = 0; i < count; i++) {
    drawPhoto(g, 160, i, rand);
    photos.push(new File([await toBlob(c, 0.85)], `sample-${String(i).padStart(3, "0")}.jpg`, { type: "image/jpeg" }));
  }
  const t = document.createElement("canvas");
  t.width = 1800; t.height = 2400;
  drawTarget(t.getContext("2d")!, 1800, 2400);
  return { photos, target: new File([await toBlob(t, 0.92)], "sample-heart.jpg", { type: "image/jpeg" }) };
}
