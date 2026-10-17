// Color math shared by matching, previews and the final render.

export type RGB = [number, number, number];

const lin = (c: number) => {
  c /= 255;
  return c > 0.04045 ? ((c + 0.055) / 1.055) ** 2.4 : c / 12.92;
};
const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);

/** sRGB (0-255) -> CIE Lab (D65). Lab distances match how different colors look. */
export function srgbToLab(r: number, g: number, b: number): RGB {
  const R = lin(r), G = lin(g), B = lin(b);
  const x = (0.4124564 * R + 0.3575761 * G + 0.1804375 * B) / 0.95047;
  const y = 0.2126729 * R + 0.7151522 * G + 0.072175 * B;
  const z = (0.0193339 * R + 0.119192 * G + 0.9503041 * B) / 1.08883;
  const fx = f(x), fy = f(y), fz = f(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/** Flat Lab array (3 per color) from a flat RGB array. */
export function labArray(rgb: ArrayLike<number>): Float32Array {
  const out = new Float32Array(rgb.length);
  for (let i = 0; i < rgb.length; i += 3) {
    const [L, a, b] = srgbToLab(rgb[i], rgb[i + 1], rgb[i + 2]);
    out[i] = L; out[i + 1] = a; out[i + 2] = b;
  }
  return out;
}

export const luma = (r: number, g: number, b: number) => 0.299 * r + 0.587 * g + 0.114 * b;

export interface Finish { brightness: number; contrast: number; saturation: number }

/**
 * Print color compensation, in place on RGBA pixels. Same order and maths as
 * PIL.ImageEnhance (brightness, then contrast around the poster's mean gray, then
 * saturation), so the web and Python versions agree.
 */
export function applyFinish(px: Uint8ClampedArray, fin: Finish, grayMean: number) {
  const { brightness: b, contrast: c, saturation: s } = fin;
  if (b === 1 && c === 1 && s === 1) return;
  for (let i = 0; i < px.length; i += 4) {
    let r = px[i] * b, g = px[i + 1] * b, bl = px[i + 2] * b;
    r = grayMean + c * (r - grayMean);
    g = grayMean + c * (g - grayMean);
    bl = grayMean + c * (bl - grayMean);
    const y = luma(r, g, bl);
    px[i] = y + s * (r - y);
    px[i + 1] = y + s * (g - y);
    px[i + 2] = y + s * (bl - y);
  }
}
