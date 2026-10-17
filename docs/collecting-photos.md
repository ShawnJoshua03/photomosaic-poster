# Collecting photos

The hard part of a group poster is usually getting everyone's photos. Shared drives
stall, downloads arrive as a pile of zips, and iCloud stops at 1,000 photos per download.
Here are the options, best first.

## Option 1: the built-in upload page (easiest for big batches)

```bash
mosaic-poster collect photos/
```

It prints a private link. Friends open it on their phone, type their name and pick
photos.

- **Straight to you:** uploads land on your computer, in `photos/<their name>/`. There
  is nothing to download afterwards.
- **No phone limits:** there are no account limits and no 1,000-photo caps. Originals
  come through at full quality, including HEIC, RAW, video and zips.
- **Reliable:** three uploads run at a time, each with retries, and a live counter shows
  how many photos have arrived from how many people.
- **Safe for duplicates:** same-named files never overwrite each other. The poster tool
  drops exact duplicates anyway.
- **Private:** the link carries a random key, so people without it get "forbidden".
  Nobody can browse or download what others uploaded.

**Friends on the same Wi-Fi** can use the "Same Wi-Fi" link directly.

**Friends anywhere else** need the page exposed through a tunnel. For example, with
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/),
which is free and needs no account:

```bash
cloudflared tunnel --url http://localhost:8000
```

Send friends `https://<the-printed-address>/?k=<the key from collect>`. Keep both windows
open while people upload, and press Ctrl+C when you're done. Then the link stops working.

When you're done collecting, make the poster from that folder:

```bash
mosaic-poster target.jpg photos/
```

## Option 2: a shared Google Drive folder

Share the folder as *Anyone with the link → Editor*.

- **Downloading:** select all and download. Large folders arrive as several zips. **Don't
  unzip them**; pass the zips straight in:
  `mosaic-poster target.jpg drive-download-1.zip drive-download-2.zip`
- **Downside:** anyone with the link can delete files.

## Option 3: an iCloud shared album

- **On iCloud.com:** downloads stop at 1,000 photos at a time. Select a range by clicking
  the first photo and Shift+clicking the last, download it, then do the next range.
  *Most Compatible* gives smaller JPEGs.
- **iCloud for Windows:** the app can sync the whole album with no cap.
- **Live Photos:** they come with `.mov` clips. Those are skipped unless you add
  `--include-videos`, which you rarely want, since the still photo is already there.

## Tips for the message to friends

- **What to send:** "10–15 photos with the birthday person: selfies, group shots,
  throwbacks. Originals, not screenshots."
- **A deadline:** set one. Uploads cluster right after you ask, then stop, so send a
  reminder a day before.
- **The surprise:** "Don't tell them!"

## Choosing the target photo

Compare candidates before committing:

```bash
mosaic-poster compare beach.jpg grad.jpg selfie.heic --photos photos/ --size 36x54
```

This renders a quick mosaic of each candidate side by side, using a sample of your photos.
It scores each one on resolution, contrast, sharpness, brightness and how much has to be
cropped. The score can't see faces, so trust your eyes on the preview sheet.

**What works:**
- **A large face in the frame.** Portrait photos suit portrait posters.
- **Strong light and dark shapes,** like dark hair against a bright sky. A night photo
  needs `--gamma 0.7` and still looks soft.
- **The original file,** at least 1,500 px wide. Not one forwarded through a chat app.
- **Sunglasses and profiles are fine.** Bold shapes survive a mosaic better than subtle
  expressions.
