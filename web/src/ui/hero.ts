// Landing page art: the repo's own demo poster (docs/demo.jpg, built from 600 generated pictures) with a
// loupe that follows the cursor, plus a "across the room to up close" slider over the same poster.
// The demo close-up (docs/demo-closeup.jpg) is a real full-resolution crop of the 3600 x 4800 poster, so the
// loupe shows true detail inside that crop's box and only an enlargement of the small picture elsewhere.
// Decorative and explanatory only: the page works without it.

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));

// Where the 900 x 600 close-up sits on the 3600 x 4800 poster, as fractions (see examples/make_demo.py).
const REG = { x: 1350 / 3600, y: 1860 / 4800, w: 900 / 3600, h: 600 / 4800 };
const POSTER = "url(./demo/demo.jpg)", CLOSE = "url(./demo/demo-closeup.jpg)";

function initLoupe(): void {
  const frame = document.getElementById("hero-frame");
  const loupe = document.getElementById("hero-loupe");
  const region = document.getElementById("hero-region");
  const zoomEl = document.getElementById("hero-zoom") as HTMLInputElement | null;
  if (!frame || !loupe || !region || !zoomEl) return;

  let px = REG.x + REG.w / 2, py = REG.y + REG.h / 2; // loupe centre, as fractions of the poster
  let Z = parseFloat(zoomEl.value);

  region.style.left = `${REG.x * 100}%`; region.style.top = `${REG.y * 100}%`;
  region.style.width = `${REG.w * 100}%`; region.style.height = `${REG.h * 100}%`;

  function paint() {
    const D = frame!.clientWidth, H = frame!.clientHeight, L = loupe!.clientWidth;
    if (!D) return;
    const cx = px * D, cy = py * H;
    // Poster layer, enlarged Z times; the close-up layer sits on top at the same scale.
    const bw = D * Z, bh = H * Z;
    const ox = L / 2 - cx * Z, oy = L / 2 - cy * Z;
    const cw = REG.w * D * Z, ch = REG.h * H * Z;
    loupe!.style.backgroundSize = `${cw}px ${ch}px, ${bw}px ${bh}px`;
    loupe!.style.backgroundPosition = `${ox + REG.x * D * Z}px ${oy + REG.y * H * Z}px, ${ox}px ${oy}px`;
    loupe!.style.left = `${cx - L / 2}px`; loupe!.style.top = `${cy - L / 2}px`;
  }
  loupe.style.backgroundImage = `${CLOSE}, ${POSTER}`;
  loupe.style.backgroundRepeat = "no-repeat";

  function move(e: PointerEvent) {
    const r = frame!.getBoundingClientRect();
    px = clamp((e.clientX - r.left) / r.width, 0.03, 0.97);
    py = clamp((e.clientY - r.top) / r.height, 0.03, 0.97);
    paint();
  }
  frame.addEventListener("pointermove", move);
  frame.addEventListener("pointerdown", move);
  zoomEl.addEventListener("input", () => { Z = parseFloat(zoomEl.value); paint(); });
  new ResizeObserver(paint).observe(frame);
  paint();
}

/** The proof section's third picture: scrub from the whole poster to the real close-up. */
function initScrubber(): void {
  const frame = document.getElementById("proof-frame");
  const range = document.getElementById("proof-zoom") as HTMLInputElement | null;
  const tag = document.getElementById("proof-tag");
  if (!frame || !range) return;
  frame.style.backgroundImage = `${CLOSE}, ${POSTER}`;
  frame.style.backgroundRepeat = "no-repeat";

  function paint() {
    const w = frame!.clientWidth, h = frame!.clientHeight;
    if (!w) return;
    const t = parseFloat(range!.value);
    // Poster width: whole poster fits at 0; at 1 the close-up fills the frame's height.
    const wd0 = Math.min(w, h * 0.75);
    const wd1 = (h * 0.75) / REG.h;
    const wd = wd0 * Math.pow(wd1 / wd0, t);
    const hd = wd * (4 / 3);
    const fx = REG.x + REG.w / 2, fy = REG.y + REG.h / 2;
    // The focus point glides from where it sits on the centred poster to the middle of the frame.
    const sx = w / 2 + (fx - 0.5) * wd0, sy = h / 2 + (fy - 0.5) * wd0 * (4 / 3);
    const tx = sx + (w / 2 - sx) * t, ty = sy + (h / 2 - sy) * t;
    const ox = tx - fx * wd, oy = ty - fy * hd;
    frame!.style.backgroundSize = `${REG.w * wd}px ${REG.h * hd}px, ${wd}px ${hd}px`;
    frame!.style.backgroundPosition = `${ox + REG.x * wd}px ${oy + REG.y * hd}px, ${ox}px ${oy}px`;
    if (tag) tag.textContent = t < 0.34 ? "Across the room" : t < 0.8 ? "Closer" : "Up close";
  }
  range.addEventListener("input", paint);
  new ResizeObserver(paint).observe(frame);
  paint();
}

export function initHero(): void {
  // "Make a poster" scrolls to the tool. The plain anchor link still works if this never runs.
  document.getElementById("start")?.addEventListener("click", (e) => {
    const tool = document.getElementById("s-photos");
    if (!tool) return;
    e.preventDefault();
    tool.scrollIntoView({ behavior: reduce.matches ? "auto" : "smooth", block: "start" });
    document.getElementById("drop")?.focus({ preventScroll: true });
  });
  initLoupe();
  initScrubber();
}
