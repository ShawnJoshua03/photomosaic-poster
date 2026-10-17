# Changelog

## 0.2.1

### Security
- **Decompression bombs:** images over 400 MP are refused instead of being allowed
  unlimited size.
- **Large files:** they are hashed in chunks and decoded from disk, files over 2 GB are
  skipped, and zip members are size-checked before reading.
- **Upload page (`collect`):**
  - a 128-bit key instead of 72-bit;
  - security headers (CSP, no-referrer, nosniff, no framing);
  - a total folder cap (`--max-total-gb`), a limit of 12 uploads at once, and a timeout
    for stalled connections;
  - Windows-reserved names are made safe;
  - rejected uploads get a clear error instead of a reset connection;
  - a `--local-only` mode for use behind a tunnel.
- **Dependencies:** Pillow 10.3 or newer is now required.
- **CI:** bandit, pip-audit, CodeQL and Dependabot now run automatically.

### Project
- **PyPI publishing:** releases are published from GitHub Actions.
- **Templates:** issue templates (including printer reports) and a PR template.
- **Docs:** `SECURITY.md` and `CLAUDE.md`.

## 0.2.0

- **More formats:** every common image format, HEIC/AVIF, camera RAW, video frames and
  `.zip` downloads.
- **Printer and paper presets**, with `check` for rule checks and recommendations.
- **Print previews** in an HTML report: paper simulation, or an ICC soft proof.
- **New commands:** `collect` (upload page), `compare` (choose the target photo) and
  `proof` (preview an existing file).
- **New options:** `--test-strip`, `--fallbacks`, and WebP/TIFF output.

## 0.1.0

- **First release:** mosaic matching with repeat caps, spacing and look-alike grouping,
  and every photo guaranteed a spot.
- **Output:** tint and overlay, rendering in strips, CMYK/PDF/JPEG output with size
  limits, and panels.
