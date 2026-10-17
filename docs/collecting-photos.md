# Collecting photos from friends

## A shared upload folder

The easiest option is a **Google Drive folder** shared as *Anyone with the link → Editor*.
Friends can upload from a phone without installing anything, and HEIC photos from
iPhones upload fine.

- **Message to friends:** "Upload 10–15 photos with the birthday person: selfies, group
  shots, throwbacks. Originals, not screenshots. Don't tell them!"
- **Downside:** anyone with the link can delete files. If that matters, use a Google
  Form with a file-upload question instead. Uploaders then need a Google account.
- **Deadline:** set one. Uploads cluster right after you ask and then stop.

## Getting the photos onto your computer

- **Google Drive:** open the folder, select all (Ctrl/Cmd+A), right-click → Download.
  Large folders arrive as several zip files. Unzip them all, then pass every folder to
  the tool:
  `mosaic-poster target.jpg part1/ part2/ part3/`
- **iCloud shared album:** iCloud.com downloads at most 1,000 photos at a time. Select
  a range by clicking the first photo and Shift+clicking the last. Use the download
  button's *Most Compatible* option for smaller JPEGs. Or install iCloud for Windows
  to sync the whole album.
- **Nothing needs cleaning up.** Videos, Live Photo `.mov` files, documents and corrupt
  files are skipped automatically, and so are duplicate uploads of the same file.
  Camera RAW files (`.cr2`, `.nef` and so on) aren't read; convert them to JPEG first
  if you want them in.

## Choosing the target photo

The big picture matters more than any setting:

- **The face is large in the frame.** Crop with `--crop` if needed.
- **It's well lit, with clear contrast.** Dark hair against a bright sky reads
  beautifully. A night photo needs `--gamma 0.7` and still looks soft.
- **It's at least 1,500 px wide**, ideally the original from the phone or camera,
  not one sent through a chat app.
- **Sunglasses and profiles are fine.** Strong shapes survive the mosaic better than
  subtle expressions.

Check the crop before a long render:

```bash
mosaic-poster target.jpg photos/ -o test.png --dpi 30 --save-target crop_check.png
```
