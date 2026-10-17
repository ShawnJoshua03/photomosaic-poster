// Printer and paper presets, kept in step with src/mosaic_poster/printers.py.
// Paper numbers are typical values used to approximate how a print will look.

import type { Finish, RGB } from "./color";

export interface Paper {
  key: string;
  name: string;
  white: RGB;        // blank paper
  black: RGB;        // deepest black it holds
  dotGain: number;   // >1 darkens midtones
  saturation: number;
  spreadIn: number;  // ink spread, inches
  finish: Partial<Finish>;
  notes: string;
}

export const PAPERS: Record<string, Paper> = Object.fromEntries(
  ([
    ["glossy", "Glossy photo paper", [250, 250, 248], [14, 14, 16], 1.0, 1.0, 0.0015, {},
      "Most detail and the deepest blacks. Shows glare under room lights."],
    ["luster", "Luster / satin photo paper", [248, 247, 244], [20, 20, 22], 1.02, 0.97, 0.002,
      { saturation: 1.03 }, "The usual photo-lab poster paper: rich color, little glare."],
    ["matte", "Matte poster paper", [246, 245, 241], [34, 33, 35], 1.05, 0.9, 0.003,
      { contrast: 1.05, saturation: 1.07 }, "No glare; softer blacks, so a little extra contrast helps."],
    ["bond", "Uncoated bond / plotter paper", [243, 242, 236], [58, 56, 58], 1.15, 0.78, 0.006,
      { brightness: 1.05, contrast: 1.1, saturation: 1.15 },
      "Cheap and huge, but it soaks up ink: prints come out darker, flatter and a little soft."],
    ["canvas", "Canvas", [238, 234, 224], [42, 40, 40], 1.08, 0.88, 0.004,
      { contrast: 1.05, saturation: 1.08 }, "Warm white and a weave that hides fine detail; prefer bigger tiles."],
    ["plain", "Plain office paper", [244, 244, 240], [52, 52, 54], 1.12, 0.8, 0.005,
      { brightness: 1.04, contrast: 1.08, saturation: 1.12 }, "Fine for test prints, not the real poster."],
  ] as const).map(([key, name, white, black, dotGain, saturation, spreadIn, finish, notes]) => [
    key, { key, name, white: [...white] as RGB, black: [...black] as RGB, dotGain, saturation,
      spreadIn, finish: { ...finish }, notes },
  ]),
);

export type Format = "pdf" | "jpg";

export interface Printer {
  key: string;
  name: string;
  short: string;
  paper: string;
  dpi: number;
  formats: Format[];   // best first
  maxWidthIn: number;  // 0 = unknown
  maxHeightIn: number;
  maxMB: number;
  edgeMarginIn: number;
  notes: string[];
}

export const PRINTERS: Record<string, Printer> = {
  "photo-lab": {
    key: "photo-lab", name: "Photo lab (online or in-store)", short: "Photo lab",
    paper: "luster", dpi: 300, formats: ["jpg"], maxWidthIn: 0, maxHeightIn: 0, maxMB: 0,
    edgeMarginIn: 0,
    notes: ["Labs expect an sRGB JPEG.", "Order the exact size you made so nothing is cropped.",
      "Upload limits vary (often 25-100 MB); set the file size limit to match."],
  },
  "plotter-bond": {
    key: "plotter-bond", name: "Wide-format plotter on bond paper (e.g. HP DesignJet)",
    short: "Plotter, bond paper", paper: "bond", dpi: 300, formats: ["pdf", "jpg"],
    maxWidthIn: 36, maxHeightIn: 0, maxMB: 75, edgeMarginIn: 0.2,
    notes: ["The roll limits the width (often 36 in); the length can be almost anything.",
      "Printing from USB: a PDF is the most reliable. Some plotters reject CMYK JPEGs.",
      "If the printer stops partway through, download it in 2 panels.",
      "Set print quality to Best: Normal visibly blurs the small photos."],
  },
  "print-shop": {
    key: "print-shop", name: "Print shop large-format (matte or satin)", short: "Print shop",
    paper: "matte", dpi: 300, formats: ["pdf", "jpg"], maxWidthIn: 0, maxHeightIn: 0, maxMB: 0,
    edgeMarginIn: 0.125,
    notes: ["Ask whether they want RGB or CMYK; this site makes RGB files, which most shops convert.",
      "Ask for their file-size limit."],
  },
  canvas: {
    key: "canvas", name: "Canvas print service", short: "Canvas", paper: "canvas", dpi: 200,
    formats: ["jpg"], maxWidthIn: 0, maxHeightIn: 0, maxMB: 0, edgeMarginIn: 1.5,
    notes: ["Gallery wraps fold ~1.5 in around the frame: keep the face away from the edges."],
  },
  "office-inkjet": {
    key: "office-inkjet", name: "Home or office printer (test prints)", short: "Home printer",
    paper: "plain", dpi: 300, formats: ["pdf", "jpg"], maxWidthIn: 8.5, maxHeightIn: 14,
    maxMB: 0, edgeMarginIn: 0.25,
    notes: ["Print a test strip of the real poster to check tile size and color cheaply."],
  },
};

export const SIZES: [number, number][] = [
  [18, 24], [24, 36], [36, 48], [36, 54], [20, 30], [16, 20], [11, 14], [8.5, 11],
];
