import { CHECKLIST } from "../engine/advice";
import { autoCols } from "../engine/layout";
import { collectFiles, decodeAll, type Library } from "../engine/library";
import { PAPERS, PRINTERS, SIZES } from "../engine/presets";
import type { ExportMessage } from "../engine/export.worker";
import {
  applyPrinter, build, defaultSettings, detailFocus, exportRequest, findings, loadTarget, renderRegion,
  withPaper, type Built, type Settings, type Target,
} from "../engine/studio";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
let S: Settings = defaultSettings();
const lib: Library = { photos: [], skipped: {} };
let target: Target | null = null;
let built: Built | null = null;
let view: "paper" | "screen" = "paper";
let token = 0; // newest render wins

// ---- setup of the controls ---------------------------------------------------------

function fill(sel: HTMLSelectElement, items: [string, string][]) {
  sel.replaceChildren(...items.map(([v, t]) => Object.assign(document.createElement("option"), { value: v, textContent: t })));
}
fill($("printer"), [["", "Not sure yet"], ...Object.values(PRINTERS).map((p) => [p.key, p.name] as [string, string])]);
fill($("paper"), [["", "Don't simulate paper"], ...Object.values(PAPERS).map((p) => [p.key, p.name] as [string, string])]);
fill($("size"), [...SIZES.map(([w, h]) => [`${w}x${h}`, `${w} x ${h}`] as [string, string]), ["custom", "Custom size..."]]);
$<HTMLInputElement>("checklist").replaceChildren(...CHECKLIST.map((t) => Object.assign(document.createElement("li"), { textContent: t })));

const sizeKey = () => `${Math.min(S.widthIn, S.heightIn)}x${Math.max(S.widthIn, S.heightIn)}`;
function syncControls() {
  $<HTMLSelectElement>("printer").value = S.printer;
  $<HTMLSelectElement>("paper").value = S.paper;
  const known = SIZES.some(([w, h]) => `${w}x${h}` === sizeKey());
  $<HTMLSelectElement>("size").value = known ? sizeKey() : "custom";
  $<HTMLSelectElement>("orient").value = S.heightIn >= S.widthIn ? "p" : "l";
  $("custom-size").hidden = known;
  $<HTMLInputElement>("w").value = String(S.widthIn);
  $<HTMLInputElement>("h").value = String(S.heightIn);
  $<HTMLInputElement>("tint").value = String(S.tint);
  $<HTMLInputElement>("overlay").value = String(S.overlay);
  $<HTMLInputElement>("zoom").value = String(S.crop.zoom);
  $<HTMLInputElement>("gamma").value = String(S.gamma);
  $<HTMLInputElement>("f-b").value = String(S.finish.brightness);
  $<HTMLInputElement>("f-c").value = String(S.finish.contrast);
  $<HTMLInputElement>("f-s").value = String(S.finish.saturation);
  $<HTMLSelectElement>("format").value = S.format;
  $<HTMLInputElement>("maxmb").value = String(S.maxMB);
  const pr = PRINTERS[S.printer];
  $("printer-note").textContent = pr ? pr.notes.join(" ") : "Pick your printer for its file rules, paper and a matching preview.";
  const opts: [string, string][] = [["0", `Automatic (${autoCols(S.widthIn, S.heightIn, Math.max(lib.photos.length, 1))} across)`]];
  for (const c of [24, 32, 40, 48, 64, 80, 96, 120]) opts.push([String(c), `${c} across (${(S.widthIn / c).toFixed(2)} in)`]);
  fill($("tiles"), opts);
  $<HTMLSelectElement>("tiles").value = String(S.cols);
}

// ---- photos ------------------------------------------------------------------------

async function addPhotos(items: (File | FileSystemEntry)[]) {
  const bar = $("photo-bar"), fillEl = bar.firstElementChild as HTMLElement, status = $("photo-status");
  bar.hidden = false; fillEl.style.width = "0";
  status.textContent = "Looking for photos...";
  try {
    const files = await collectFiles(items, lib.skipped, (n) => { status.textContent = `Found ${n} photos...`; });
    await decodeAll(files, lib, (p) => {
      fillEl.style.width = `${(100 * p.done) / Math.max(p.found, 1)}%`;
      status.textContent = `Reading photos: ${p.done} of ${p.found}`;
    });
  } catch (e) {
    status.textContent = `Something went wrong reading photos: ${e instanceof Error ? e.message : e}`;
  }
  bar.hidden = true;
  const sk = Object.entries(lib.skipped);
  status.textContent = lib.photos.length ? `${lib.photos.length} photos ready.` : "No usable photos found.";
  $("photo-skips").textContent = sk.length ? `Left out: ${sk.map(([k, n]) => `${n} ${k}`).join("; ")}.` : "";
  syncControls();
  refresh(true);
}

const drop = $("drop");
const dropFiles = async (dt: DataTransfer) => {
  const items = [...dt.items].map((i) => i.webkitGetAsEntry?.()).filter((e): e is FileSystemEntry => !!e);
  await addPhotos(items.length ? items : [...dt.files]);
};
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("on"); });
drop.addEventListener("dragleave", () => drop.classList.remove("on"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("on"); if (e.dataTransfer) void dropFiles(e.dataTransfer); });
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") $("in-files").click(); });
$("pick-files").onclick = (e) => { e.stopPropagation(); $("in-files").click(); };
$("pick-folder").onclick = (e) => { e.stopPropagation(); $("in-folder").click(); };
for (const id of ["in-files", "in-folder"]) {
  const el = $<HTMLInputElement>(id);
  el.onchange = () => { if (el.files?.length) void addPhotos([...el.files]); el.value = ""; };
}

// ---- target ------------------------------------------------------------------------

$("pick-target").onclick = () => $("in-target").click();
$<HTMLInputElement>("in-target").onchange = async (e) => {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  try {
    target = await loadTarget(f);
  } catch {
    // HEIC the browser can't open: reuse the photo decoder's converter.
    try {
      const { heicTo } = await import("heic-to");
      const bmp = await heicTo({ blob: f, type: "image/jpeg", quality: 0.95 });
      target = await loadTarget(bmp);
    } catch { alert("That photo couldn't be opened. Try a JPEG or PNG."); return; }
  }
  S = { ...S, crop: { zoom: 1, fx: 0.5, fy: 0.45 } };
  const t = target!;
  if ((t.height > t.width) !== (S.heightIn > S.widthIn)) S = { ...S, widthIn: S.heightIn, heightIn: S.widthIn };
  syncControls();
  refresh(true);
};
const tv = $<HTMLCanvasElement>("target-view");
tv.addEventListener("click", (e) => {
  if (!target) return;
  const r = tv.getBoundingClientRect();
  S = { ...S, crop: { ...S.crop, fx: (e.clientX - r.left) / r.width, fy: (e.clientY - r.top) / r.height } };
  refresh(true);
});
function drawTargetThumb() {
  const g = tv.getContext("2d")!;
  g.clearRect(0, 0, tv.width, tv.height);
  if (!target) return;
  const k = Math.min(tv.width / target.width, tv.height / target.height);
  const w = target.width * k, h = target.height * k, ox = (tv.width - w) / 2, oy = (tv.height - h) / 2;
  g.drawImage(target.source, ox, oy, w, h);
  if (built) { // outline what's kept on the poster
    const c = built.crop, sx = w / built.src.width;
    g.strokeStyle = "#ff8a65"; g.lineWidth = 3;
    g.strokeRect(ox + c.x * sx, oy + c.y * sx, c.w * sx, c.h * sx);
  }
}

// ---- updating ----------------------------------------------------------------------

let timer = 0;
let needBuild = true;
function refresh(rebuild: boolean) {
  needBuild ||= rebuild;
  clearTimeout(timer);
  timer = window.setTimeout(() => void update(), 120);
}

async function update() {
  const my = ++token;
  if (!lib.photos.length || !target) {
    $("busy").textContent = "";
    const list = $("findings");
    list.replaceChildren(li("tip", !lib.photos.length ? "Add your photos" : "Choose the big picture",
      "Both are needed to see the poster."));
    return;
  }
  $("busy").textContent = "Updating...";
  await new Promise((r) => setTimeout(r)); // let the label paint before the heavy work
  if (needBuild || !built) { built = build(lib, target, S); needBuild = false; }
  if (my !== token) return;
  const b = built;
  b.settings = S; // tint, overlay and colour changes need no re-matching
  const ppi = Math.max(8, Math.min(40, 900 / b.plan.widthIn));
  const full = await renderRegion(lib, b, { cx: b.plan.widthIn / 2, cy: b.plan.heightIn / 2, wIn: b.plan.widthIn, hIn: b.plan.heightIn },
    ppi, view === "paper" && S.paper ? S.paper : null);
  if (my !== token) return;
  paint($("view") as HTMLCanvasElement, full);
  $("view-note").textContent = view === "paper" && S.paper
    ? `Simulated on ${PAPERS[S.paper].name.toLowerCase()}. An approximation: for an exact match, use your print shop's colour profile.`
    : view === "paper" ? "Choose a paper in step 3 to see how it will look printed." : "The file as it looks on a screen.";
  const f = detailFocus(b, target);
  const paper = S.paper || null;
  const a = await renderRegion(lib, b, { cx: f.x, cy: f.y, wIn: 6, hIn: 4 }, 96, paper);
  const m = await renderRegion(lib, b, { cx: f.x, cy: f.y, wIn: 2, hIn: 4 / 3 }, 288, paper);
  if (my !== token) return;
  paint($("close-a") as HTMLCanvasElement, a);
  paint($("close-b") as HTMLCanvasElement, m);
  renderFindings(b);
  drawTargetThumb();
  $("busy").textContent = "";
}

function paint(cv: HTMLCanvasElement, img: ImageData) {
  cv.width = img.width; cv.height = img.height;
  cv.getContext("2d")!.putImageData(img, 0, 0);
}

function li(level: string, title: string, detail?: string, fix?: string) {
  const el = document.createElement("li");
  el.className = level;
  const tag = Object.assign(document.createElement("span"), { className: "tg", textContent: level });
  const body = document.createElement("div");
  body.append(Object.assign(document.createElement("div"), { textContent: title }));
  if (detail) body.append(Object.assign(document.createElement("div"), { className: "d", textContent: detail }));
  if (fix) body.append(Object.assign(document.createElement("div"), { className: "fx", textContent: `Fix: ${fix}` }));
  el.append(tag, body);
  return el;
}
function renderFindings(b: Built) {
  $("findings").replaceChildren(...findings(lib, b, S).map((f) => li(f.level, f.title, f.detail, f.fix)));
}

// ---- other controls ----------------------------------------------------------------

const on = (id: string, ev: string, fn: () => void) => $(id).addEventListener(ev, fn);
const num = (id: string) => parseFloat($<HTMLInputElement>(id).value);
on("printer", "change", () => { S = applyPrinter(S, $<HTMLSelectElement>("printer").value); syncControls(); refresh(true); });
on("paper", "change", () => { S = withPaper(S, $<HTMLSelectElement>("paper").value); syncControls(); refresh(false); });
function setSize(w: number, h: number) { S = { ...S, widthIn: w, heightIn: h }; syncControls(); refresh(true); }
on("size", "change", () => {
  const v = $<HTMLSelectElement>("size").value;
  if (v === "custom") { $("custom-size").hidden = false; return; }
  const [a, b] = v.split("x").map(Number);
  S.heightIn >= S.widthIn ? setSize(a, b) : setSize(b, a);
});
on("orient", "change", () => {
  const p = $<HTMLSelectElement>("orient").value === "p", lo = Math.min(S.widthIn, S.heightIn), hi = Math.max(S.widthIn, S.heightIn);
  p ? setSize(lo, hi) : setSize(hi, lo);
});
for (const id of ["w", "h"]) on(id, "change", () => { if (num("w") > 0 && num("h") > 0) setSize(num("w"), num("h")); });
on("tiles", "change", () => { S = { ...S, cols: parseInt($<HTMLSelectElement>("tiles").value, 10) }; refresh(true); });
on("tint", "input", () => { S = { ...S, tint: num("tint") }; refresh(true); });
on("overlay", "input", () => { S = { ...S, overlay: num("overlay") }; refresh(false); });
on("zoom", "input", () => { S = { ...S, crop: { ...S.crop, zoom: num("zoom") } }; refresh(true); });
on("gamma", "input", () => { S = { ...S, gamma: num("gamma") }; refresh(true); });
for (const [id, key] of [["f-b", "brightness"], ["f-c", "contrast"], ["f-s", "saturation"]] as const) {
  on(id, "input", () => { S = { ...S, finishTouched: true, finish: { ...S.finish, [key]: num(id) } }; refresh(false); });
}
on("reshuffle", "click", () => { S = { ...S, seed: S.seed + 1 }; refresh(true); });
on("format", "change", () => { S = { ...S, format: $<HTMLSelectElement>("format").value as Settings["format"] }; if (built) renderFindings(built); });
on("maxmb", "change", () => { S = { ...S, maxMB: Math.max(0, num("maxmb") || 0) }; if (built) renderFindings(built); });
const tabs = { paper: $("t-paper"), screen: $("t-screen") };
for (const [k, el] of Object.entries(tabs) as ["paper" | "screen", HTMLElement][]) {
  el.addEventListener("click", () => {
    view = k;
    for (const [kk, e2] of Object.entries(tabs)) e2.setAttribute("aria-selected", String(kk === k));
    refresh(false);
  });
}

// ---- export ------------------------------------------------------------------------

let exporting = false;
async function download(testStrip: boolean) {
  if (!built || !target || exporting) { $("exp-status").textContent = "Add your photos and the big picture first."; return; }
  const errors = findings(lib, built, S).filter((f) => f.level === "error");
  if (errors.length) { $("exp-status").textContent = `Fix first: ${errors[0].title}`; return; }
  exporting = true;
  const bar = $("exp-bar"), fillEl = bar.firstElementChild as HTMLElement, status = $("exp-status");
  bar.hidden = false; fillEl.style.width = "0"; ($("dl") as HTMLButtonElement).disabled = true;
  const panels = parseInt($<HTMLSelectElement>("panels").value, 10);
  const req = exportRequest(lib, built, S, { panels, testStrip, base: "mosaic-poster" });
  req.target = await createImageBitmap(built.src);
  const worker = new Worker(new URL("../engine/export.worker.ts", import.meta.url), { type: "module" });
  worker.onmessage = (ev: MessageEvent<ExportMessage>) => {
    const m = ev.data;
    if (m.type === "progress") {
      fillEl.style.width = `${(100 * m.done) / Math.max(m.total, 1)}%`;
      status.textContent = `${m.stage}...`;
    } else {
      worker.terminate(); exporting = false; bar.hidden = true; ($("dl") as HTMLButtonElement).disabled = false;
      if (m.type === "error") { status.textContent = `Couldn't build the file: ${m.message}`; return; }
      status.textContent = m.files.map((f) => `${f.name}: ${(f.blob.size / 1e6).toFixed(1)} MB`).join("   ");
      m.files.forEach((f, i) => setTimeout(() => saveBlob(f.blob, f.name), i * 400));
    }
  };
  worker.onerror = () => { exporting = false; bar.hidden = true; ($("dl") as HTMLButtonElement).disabled = false; status.textContent = "The export ran out of memory. Try 2 panels or a smaller size."; };
  worker.postMessage(req, [req.target]);
}
function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
on("dl", "click", () => void download(false));
on("dl-strip", "click", () => void download(true));

syncControls();
refresh(true);
