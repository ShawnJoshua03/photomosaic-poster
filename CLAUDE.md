# photomosaic-poster

CLI and library that turns a target photo plus folders of photos into a print-ready
mosaic poster. Python 3.9+, Pillow, numpy, pillow-heif; optional rawpy (RAW) and av (video).

## Commands

- Install for development: `python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"`
  (on macOS/Linux: `.venv/bin/pip`)
- Tests: `.venv/Scripts/python -m pytest -q` (about 20 s, generated images only)
- Security scan: `.venv/Scripts/python -m bandit -q -r src` (CI runs it plus pip-audit)
- Demo images for the README: `python examples/make_demo.py`

## Layout (src/mosaic_poster/)

| Module | Job |
|---|---|
| `formats.py` | Read any photo: images, HEIC/AVIF, RAW, video frames, zip members |
| `tiles.py` | Decode into tiles, cache, duplicates, look-alikes |
| `assign.py` | Which photo goes in which tile |
| `plan.py` | Layout math, target-photo measurements |
| `color.py` | Lab color, print color compensation, CMYK profiles |
| `printers.py` | Printer and paper presets |
| `advice.py` | Rule checks and recommendations |
| `proof.py` | Print previews |
| `report.py` | The HTML report |
| `render.py` | Drawing in strips, panels, test strips, fallbacks, file output |
| `compare.py`, `collect.py` | The `compare` and `collect` commands |
| `cli.py` | The `mosaic-poster` command |

Each new printer lesson becomes a preset field in `printers.py` and a check in
`advice.py`.

## Web app (web/, "Tessera")

Browser version: everything runs on the visitor's device (nothing uploaded). TypeScript + Vite,
no framework. `web/src/engine/` mirrors the Python modules (assign, advice, presets, paper
simulation); `studio.ts` ties state together; `export.worker.ts` builds the full-size PDF/JPEG in
strips; `decode.worker.ts` imports photos (HEIC via lazy-loaded `heic-to`, RAW via embedded JPEG).
- Dev: `cd web && npm ci && npm run dev`; checks: `npx tsc --noEmit && npx vitest run && npm run build`
- Keep `presets.ts`/`advice.ts` in step with `printers.py`/`advice.py`.
- Strict CSP in `index.html`: no inline scripts or styles, no outside connections.
- Export never holds the whole poster as one image: strips are compressed as they're drawn.

## Rules

- **Never commit real photos of people.** Tests and docs use generated images, and
  `.gitignore` blocks image files except `docs/*.jpg`.
- **Untrusted input:** `collect` and photo decoding handle files from other people.
  Keep the limits in `formats.py` (MAX_IMAGE_PIXELS, MAX_FILE_BYTES) and the hardening
  in `collect.py`, which is described in SECURITY.md.
- **Memory:** posters can be 175 MP. Draw in strips and keep the poster RGB until save;
  don't hold extra full-size copies.
- **Style:** match the surrounding code: short docstrings that say *why*, and
  plain-language user messages that include the fix.
- **Releases:** bump `__version__` in `__init__.py` and update CHANGELOG.md, then
  publish a GitHub release tagged `vX.Y.Z`. `publish.yml` uploads to PyPI.
