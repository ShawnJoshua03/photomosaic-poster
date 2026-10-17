"""A self-contained HTML report: print previews, rule checks and recommendations."""
import base64
import html
import io

from .advice import PRINT_CHECKLIST

_CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1dc;
--error:#c62828;--warn:#b26a00;--tip:#1f5fbf;--ok:#2e7d32;--code:#f0eee9}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--card:#202023;--ink:#ececee;
--muted:#a0a0a8;--line:#333338;--error:#ff6b6b;--warn:#f0b04a;--tip:#7fb0ff;--ok:#6fcf74;
--code:#2a2a2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.sub{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:16px}
.verdict{display:flex;gap:12px;align-items:center;margin-top:16px;font-weight:600}
.dot{width:12px;height:12px;border-radius:50%}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
figure{margin:0}figure img{display:block;max-width:100%;height:auto;border-radius:6px;
border:1px solid var(--line)}figcaption{color:var(--muted);font-size:13px;margin-top:6px}
figcaption b{color:var(--ink)}.actual img{width:6in;max-width:100%}
.f{display:grid;grid-template-columns:64px 1fr;gap:8px;padding:10px 0;
border-top:1px solid var(--line)}.f:first-child{border-top:0}
.tag{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.error .tag{color:var(--error)}.warn .tag{color:var(--warn)}.tip .tag{color:var(--tip)}
.ok .tag{color:var(--ok)}.d{color:var(--muted);font-size:14px}
code{background:var(--code);padding:1px 6px;border-radius:4px;font-size:13px;
overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;
padding:6px 8px;border-top:1px solid var(--line)}th{color:var(--muted);font-weight:500}
.tw{overflow-x:auto}ul{padding-left:20px;margin:0}li{margin:4px 0}
"""


def _img(im, quality=88):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def write_report(path, opt, result, printer, paper, previews):
    e = html.escape
    plan = result.plan
    errors = sum(f.level == "error" for f in result.findings)
    warns = sum(f.level == "warn" for f in result.findings)
    if errors:
        verdict, color = f"{errors} problem(s) to fix before printing", "var(--error)"
    elif warns:
        verdict, color = f"Printable - {warns} thing(s) worth checking", "var(--warn)"
    else:
        verdict, color = "Ready to print", "var(--ok)"

    if opt.printer_profile:
        accuracy = (f"Previews are an ICC soft proof using <code>{e(str(opt.printer_profile))}"
                    "</code>, the same method as Photoshop's Proof Colors.")
    elif paper:
        accuracy = (f"Previews simulate <b>{e(paper.name)}</b> (paper white, black depth, "
                    "ink spread and color range). This is an approximation; for an exact "
                    "preview ask the print shop for their ICC profile and pass "
                    "<code>--printer-profile shop.icc</code>.")
    else:
        accuracy = ("No printer or paper chosen, so the 'printed' preview shows the file "
                    "itself. Add <code>--printer</code> or <code>--paper</code> for a paper "
                    "simulation.")
    if opt.cmyk:
        accuracy += " Colors were also round-tripped through the CMYK profile used for the file."

    figs = []
    for key in ("printed", "screen"):
        title, cap, im = previews[key]
        figs.append(f'<figure><img src="{_img(im)}" alt="{e(title)}"><figcaption><b>'
                    f'{e(title)}</b> - {e(cap)}</figcaption></figure>')
    close = []
    for key in ("actual", "zoom"):
        title, cap, im = previews[key]
        cls = ' class="actual"' if key == "actual" else ""
        close.append(f'<figure{cls}><img src="{_img(im, 92)}" alt="{e(title)}"><figcaption>'
                     f'<b>{e(title)}</b> - {e(cap)}</figcaption></figure>')

    rows = []
    for p, q, mb in result.files:
        rows.append(f"<tr><td>{e(p.name)}</td><td>{p.suffix[1:].upper()}</td>"
                    f"<td>{mb:.1f} MB</td><td>{q if q else '-'}</td></tr>")

    finds = []
    for f in result.findings:
        fix = f"<div>fix: <code>{e(f.fix)}</code></div>" if f.fix else ""
        detail = f'<div class="d">{e(f.detail)}</div>' if f.detail else ""
        finds.append(f'<div class="f {f.level}"><div class="tag">{f.level}</div><div>'
                     f'<div>{e(f.title)}</div>{detail}{fix}</div></div>')

    facts = [
        ("Print size", f"{plan.width_in:g} x {plan.height_in:g} in at {plan.dpi:g} DPI "
                       f"({plan.W} x {plan.H} px, {plan.megapixels:.0f} MP)"),
        ("Grid", f"{plan.cols} x {plan.rows} = {plan.cells} tiles, each {plan.tile_in:.2f} in"),
        ("Photos", f"{result.n_photos} used ({result.n_distinct} visually distinct); "
                   f"most-used appears {result.max_uses}x"),
        ("Color", ("CMYK" if opt.cmyk else "RGB")
         + (f"; paper: {paper.name}" if paper else "")),
    ]
    if result.skipped:
        facts.append(("Left out", ", ".join(f"{n} {r}" for r, n in sorted(result.skipped.items()))))
    if result.gamut_pct is not None:
        facts.append(("Color change in print", f"{result.gamut_pct:.0f}% of the picture"))
    fact_rows = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in facts)

    notes = list(PRINT_CHECKLIST)
    if printer:
        notes += list(printer.notes)
    if paper and paper.notes:
        notes.append(paper.notes)
    note_items = "".join(f"<li>{e(n)}</li>" for n in notes)
    printer_line = e(printer.name) if printer else "No printer preset"

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poster print report</title><style>{_CSS}</style></head><body><main>
<h1>Poster print report</h1>
<div class="sub">{e(result.outputs[0].name)} &middot; {printer_line}</div>
<div class="verdict"><span class="dot" style="background:{color}"></span>{e(verdict)}</div>

<h2>Preview</h2>
<div class="card"><p class="sub" style="margin-top:0">{accuracy}</p>
<div class="grid">{''.join(figs)}</div></div>

<h2>Up close</h2>
<div class="card"><div class="grid">{''.join(close)}</div></div>

<h2>Checks and recommendations</h2>
<div class="card">{''.join(finds) or '<div class="sub">Nothing to report.</div>'}</div>

<h2>Files</h2>
<div class="card tw"><table><tr><th>File</th><th>Type</th><th>Size</th>
<th>JPEG quality</th></tr>{''.join(rows)}</table></div>

<h2>Poster details</h2>
<div class="card tw"><table>{fact_rows}</table></div>

<h2>At the printer</h2>
<div class="card"><ul>{note_items}</ul></div>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")
