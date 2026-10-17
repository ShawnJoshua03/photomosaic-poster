# Contributing

Bug reports, printer war stories and pull requests are welcome.

```bash
git clone https://github.com/OWNER/photomosaic-poster.git
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

- `src/mosaic_poster/tiles.py`: finding, decoding, caching and de-duplicating photos
- `src/mosaic_poster/assign.py`: choosing which photo goes in which tile
- `src/mosaic_poster/color.py`: Lab color matching, print adjustments and CMYK
- `src/mosaic_poster/render.py`: layout, drawing in strips, panels and file output
- `src/mosaic_poster/cli.py`: the `mosaic-poster` command
