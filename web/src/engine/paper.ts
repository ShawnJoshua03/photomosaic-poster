// "How will it look printed?" - an approximation of ink on a given paper
// (mirrors src/mosaic_poster/proof.py): paper white instead of screen white, the
// paper's deepest black, darker midtones from ink spreading (dot gain) and less
// vivid color. Ink spread softening is applied separately with a canvas blur.

import { luma } from "./color";
import type { Paper } from "./presets";

export function simulatePaper(px: Uint8ClampedArray, paper: Paper) {
  const [wr, wg, wb] = paper.white, [kr, kg, kb] = paper.black;
  const s = paper.saturation, g = paper.dotGain;
  // A lookup table makes the dot-gain curve cheap.
  const curve = new Float32Array(256);
  for (let i = 0; i < 256; i++) curve[i] = (i / 255) ** g;
  for (let i = 0; i < px.length; i += 4) {
    const y = luma(px[i], px[i + 1], px[i + 2]);
    const r = Math.min(255, Math.max(0, y + s * (px[i] - y)));
    const gr = Math.min(255, Math.max(0, y + s * (px[i + 1] - y)));
    const b = Math.min(255, Math.max(0, y + s * (px[i + 2] - y)));
    px[i] = kr + curve[r | 0] * (wr - kr);
    px[i + 1] = kg + curve[gr | 0] * (wg - kg);
    px[i + 2] = kb + curve[b | 0] * (wb - kb);
  }
}

/** Blur radius (px) for ink spread when `ppi` preview pixels cover one printed inch. */
export const spreadPx = (paper: Paper, ppi: number) => paper.spreadIn * ppi;
