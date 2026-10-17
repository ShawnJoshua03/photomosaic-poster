// Recommendations (mirrors src/mosaic_poster/advice.py): checks against the
// printer's rules plus advice on photos and the target, each with a concrete fix.

import { autoCols, cells, megapixels, tileIn, type Plan, type TargetStats } from "./layout";
import type { Format, Paper, Printer } from "./presets";

export type Level = "error" | "warn" | "tip" | "ok";
export interface Finding { level: Level; title: string; detail?: string; fix?: string }

export interface AdviceInput {
  plan: Plan;
  printer?: Printer;
  paper?: Paper;
  format: Format;
  maxMB: number;
  nPhotos: number;
  nDistinct: number;
  skipped: Record<string, number>;
  target?: TargetStats;
  finishTouched: boolean; // the user changed brightness/contrast/saturation
}

const ORDER: Level[] = ["error", "warn", "tip", "ok"];

export function advise(a: AdviceInput): Finding[] {
  const f: Finding[] = [];
  const { plan, printer: pr } = a;
  const w = plan.widthIn, h = plan.heightIn;

  if (pr) {
    if (pr.maxWidthIn && w > pr.maxWidthIn) {
      f.push(h <= pr.maxWidthIn
        ? { level: "error", title: `${w} in is wider than this printer's ${pr.maxWidthIn} in maximum`,
            detail: "The same picture fits the other way round.", fix: `Use ${h} x ${w} in` }
        : { level: "error", title: `${w} in is wider than this printer's ${pr.maxWidthIn} in maximum`,
            fix: `Use ${pr.maxWidthIn} x ${Math.round((h * pr.maxWidthIn) / w)} in` });
    }
    if (pr.maxHeightIn && h > pr.maxHeightIn && !(pr.maxWidthIn && w > pr.maxWidthIn)) {
      f.push({ level: "error", title: `${h} in is taller than this printer handles`,
        fix: "Choose a smaller size, or download a test strip" });
    }
    if (!pr.formats.includes(a.format)) {
      f.push({ level: "error", title: `This printer doesn't take ${a.format.toUpperCase()} files`,
        fix: `Download a ${pr.formats[0].toUpperCase()}` });
    }
    if (plan.dpi < pr.dpi) {
      f.push({ level: "warn", title: `${plan.dpi} DPI is below the ${pr.dpi} DPI this printer wants`,
        fix: `Set quality to ${pr.dpi} DPI` });
    }
    if (pr.maxMB && (!a.maxMB || a.maxMB > pr.maxMB)) {
      f.push({ level: "warn", title: `Files must be under ${pr.maxMB} MB`,
        fix: `Set the file size limit to ${pr.maxMB} MB` });
    }
    if (pr.edgeMarginIn) {
      f.push({ level: "tip", title: `The outer ${pr.edgeMarginIn} in may not print`,
        detail: "Keep the face away from the edges; background tiles there are fine." });
    }
  }

  if (a.nPhotos === 0) {
    f.push({ level: "error", title: "Add your photos", detail: "Folders and .zip downloads work too." });
  } else {
    const uses = cells(plan) / a.nPhotos;
    if (uses > 5) {
      f.push({ level: "warn", title: `Each photo would appear about ${uses.toFixed(1)} times`,
        detail: "Above 4-5 uses the repeats are easy to spot.",
        fix: `Use ${autoCols(w, h, a.nPhotos)} columns, or add more photos` });
    } else {
      f.push({ level: "ok", title: `${a.nPhotos} photos for ${cells(plan)} tiles (about ${uses.toFixed(1)} uses each)` });
    }
    if (a.nDistinct && a.nDistinct < a.nPhotos * 0.8) {
      f.push({ level: "tip", title: `${a.nPhotos - a.nDistinct} photos are near-copies (bursts, retakes)`,
        detail: "They're treated as one photo so they don't cluster." });
    }
  }
  const ti = tileIn(plan);
  if (ti < 0.3) {
    f.push({ level: "warn", title: `Tiles are only ${ti.toFixed(2)} in across`,
      detail: "Too small to recognise the photos in them.",
      fix: `Use about ${Math.round(w / 0.5)} columns` });
  } else if (ti > 1.2) {
    f.push({ level: "tip", title: `Tiles are ${ti.toFixed(2)} in across`,
      detail: "Easy to see each photo, but the face looks blocky; raise Sharpness or add columns." });
  }
  for (const [reason, n] of Object.entries(a.skipped)) {
    f.push({ level: reason.includes("unreadable") ? "warn" : "tip", title: `${n} file(s) skipped: ${reason}` });
  }

  const t = a.target;
  if (t) {
    if (t.ppi < 30) {
      f.push({ level: "warn", title: `The big photo is only ${t.width} px wide for ${w} in`,
        detail: "Eyes and hair will look soft. Use the original from the phone, not one sent through a chat app." });
    }
    if (t.brightness < 85) {
      f.push({ level: "tip", title: "The big photo is dark", detail: "Dark areas look muddy.",
        fix: "Raise Brighten photo" });
    }
    if (t.contrast < 35) {
      f.push({ level: "tip", title: "The big photo is low-contrast",
        detail: "Strong light and dark shapes read best from a distance." });
    }
    if (t.cropLoss > 0.25) {
      const turned = (t.height > t.width) !== (h > w);
      f.push({ level: "tip", title: "The poster shape doesn't match the photo",
        detail: `About ${Math.round(t.cropLoss * 100)}% of the photo is cut off.`,
        fix: turned ? `Try ${h} x ${w} in (the photo faces the other way)` : "Drag the photo to choose what's kept" });
    }
  }

  if (a.paper && Object.keys(a.paper.finish).length && !a.finishTouched) {
    f.push({ level: "ok", title: `Color adjusted for ${a.paper.name.toLowerCase()}`, detail: a.paper.notes });
  }
  if (megapixels(plan) > 120) {
    f.push({ level: "tip", title: `Big print: ${Math.round(megapixels(plan))} megapixels`,
      detail: "Print the test strip first to check the file and colors cheaply; if a printer stops partway, download 2 panels." });
  }
  return f.sort((x, y) => ORDER.indexOf(x.level) - ORDER.indexOf(y.level));
}

export const CHECKLIST = [
  "Print at 100% scale with 'fit to page' off.",
  "Choose Best / high quality, not Normal.",
  "Check the printer's preview shows the whole poster, upright.",
  "Let ink dry before rolling; uncoated paper smudges.",
];
