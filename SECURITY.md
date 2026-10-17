# Security

## Reporting a problem

Please report security problems privately through
[GitHub security advisories](https://github.com/ShawnJoshua03/photomosaic-poster/security/advisories/new),
not in public issues. You should hear back within a week.

## What's in scope

photomosaic-poster runs on your own computer and processes photos other people sent
you. The parts that handle untrusted input are:

- **Photo decoding.** Images, HEIC/AVIF, camera RAW, video and zip files are parsed by
  Pillow, pillow-heif, rawpy (LibRaw) and PyAV (FFmpeg). Here are the protections:
  - **Decompression bombs:** images over 400 megapixels are refused.
  - **Huge files:** files over 2 GB are skipped. Zip members are size-checked before
    reading, and large files are decoded from disk instead of being loaded into memory.
  - **Bad files:** a file that fails to decode is skipped and reported, and the run
    carries on.
  - **Updates:** decoder libraries are kept current by Dependabot and scanned by
    pip-audit in CI.
- **`mosaic-poster collect`, the upload page.** It's a small web server that friends
  upload photos to.
  - **Access:** every request needs a random 128-bit key from the link. Without it the
    server returns 403.
  - **Upload only:** nobody can list, view or download what others uploaded.
  - **Files:** names are sanitized, so they can't escape the folder or use
    Windows-reserved names, and an upload never overwrites an existing file. Only photo,
    video and zip extensions are accepted.
  - **Limits:** each file has a size limit (`--max-mb`) and so does the whole folder
    (`--max-total-gb`). At most 12 uploads run at once, and stalled connections time out.
  - **Browser headers:** a strict Content-Security-Policy, no Referer leaks (so the key
    stays in the link), and no framing by other sites.

  It serves plain HTTP. On a home Wi-Fi that's normally fine. For people outside your
  network, put it behind an HTTPS tunnel (see `docs/collecting-photos.md`) with
  `--local-only`, and stop it when you're done collecting.

## Out of scope

- **Your own computer:** anyone who can run commands on it can read your photos anyway.
- **Bugs inside the decoder libraries:** report those upstream. We'll update promptly.
