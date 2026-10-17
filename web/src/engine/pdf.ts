// A minimal PDF writer: one page at the exact print size, made of horizontal JPEG
// strips stacked edge to edge. The browser never needs the whole poster as one image,
// which is what lets a phone or laptop produce a 36 x 54 inch, 300 DPI file.

export interface Strip {
  jpeg: Blob;        // baseline JPEG of the strip
  widthPx: number;
  heightPx: number;
  yPx: number;       // top edge within the page, in pixels
}

const enc = new TextEncoder();

/** Build the PDF as a Blob (parts are referenced, not copied into one big buffer). */
export function buildPdf(widthPx: number, heightPx: number, dpi: number, strips: Strip[]): Blob {
  const pt = (px: number) => (px * 72) / dpi;
  const W = pt(widthPx), H = pt(heightPx);
  const parts: (Uint8Array | Blob)[] = [];
  const offsets: number[] = [];
  let pos = 0;
  const push = (p: Uint8Array | Blob) => {
    parts.push(p);
    pos += p instanceof Blob ? p.size : p.byteLength;
  };
  const text = (s: string) => push(enc.encode(s));
  const obj = (n: number) => { offsets[n] = pos; };
  const fmt = (v: number) => (Math.round(v * 1000) / 1000).toString();

  text("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  // 1 catalog, 2 pages, 3 page, 4 content, 5.. images
  const imgBase = 5;
  obj(1); text("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
  obj(2); text("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");
  const xobjs = strips.map((_, i) => `/Im${i} ${imgBase + i} 0 R`).join(" ");
  obj(3);
  text(`3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${fmt(W)} ${fmt(H)}] ` +
    `/Resources << /XObject << ${xobjs} >> >> /Contents 4 0 R >>\nendobj\n`);
  // PDF y runs upward from the bottom; strips are given top-down.
  const ops = strips.map((s, i) =>
    `q ${fmt(pt(s.widthPx))} 0 0 ${fmt(pt(s.heightPx))} 0 ${fmt(H - pt(s.yPx + s.heightPx))} cm /Im${i} Do Q`,
  ).join("\n");
  const content = enc.encode(ops);
  obj(4);
  text(`4 0 obj\n<< /Length ${content.byteLength} >>\nstream\n`);
  push(content);
  text("\nendstream\nendobj\n");
  strips.forEach((s, i) => {
    const n = imgBase + i;
    obj(n);
    text(`${n} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${s.widthPx} /Height ${s.heightPx} ` +
      `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${s.jpeg.size} >>\nstream\n`);
    push(s.jpeg);
    text("\nendstream\nendobj\n");
  });
  const count = imgBase + strips.length;
  const xref = pos;
  let table = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) table += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  text(table + `trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts as BlobPart[], { type: "application/pdf" });
}
