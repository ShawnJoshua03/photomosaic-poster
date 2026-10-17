# Contributing

Bug reports, printer war stories and pull requests are welcome.

```bash
git clone https://github.com/ShawnJoshua03/photomosaic-poster.git
cd photomosaic-poster
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

- **Tests:** they use generated images only. Please never commit real photos of people.
- **Code:** match the style of the surrounding code, and add a test for new behavior.
- **Printer reports:** if you hit a printer or print-shop quirk, include the printer
  model, the exact error message and the options you used. Workarounds go in
  `docs/printing.md`.

## Layout

- `formats.py`: reading any photo: images, HEIC/AVIF, camera RAW, video frames, zips
- `tiles.py`: decoding photos into tiles, caching, duplicates and look-alikes
- `assign.py`: choosing which photo goes in which tile
- `plan.py`: layout math and target-photo measurements
- `color.py`: Lab color, print color compensation, CMYK profiles
- `printers.py`: printer and paper presets
- `advice.py`: rule checks and recommendations (add new printer lessons here)
- `proof.py`: print simulation and soft-proof previews
- `report.py`: the HTML report
- `render.py`: drawing in strips, panels, test strips, fallbacks and file output
- `compare.py`, `collect.py`: the `compare` and `collect` commands
- `cli.py`: the `mosaic-poster` command

All of these live in `src/mosaic_poster/`.
