# AutoEditPromo

AutoEditPromo is a Python desktop GUI application that auto-generates promo videos from local assets using **FFmpeg** and **FFprobe**.

## Features

- Scans asset folders:
  - `videos/`
  - `music/`
  - `images/`
  - `sounds/`
- Uses `ffprobe` to analyze clips:
  - duration
  - resolution
  - fps
- Builds a randomized sequence of clip segments.
- Basic beat-sync timing using configurable fallback BPM.
- Adds transitions:
  - fade in/out
  - crossfade between clips
- Adds text overlays:
  - title
  - subtitle
  - promo messages
- Exports:
  - `output/final_promo_16x9.mp4`
  - `output/final_promo_4x3.mp4`
  - `output/final_promo.mp4` (copy of 16:9)
- Uses threads in GUI to prevent freezing.
- Falls back to silent audio if no music is available.
- Tries `-c copy` for source clip cuts, with safe re-encode fallback.

## Requirements

- Python **3.11+**
- FFmpeg and FFprobe in your PATH

Check FFmpeg:

```bash
ffmpeg -version
ffprobe -version
```

## Project structure

- `main.py` - Tkinter GUI
- `editor.py` - promo generation logic
- `ffmpeg_utils.py` - ffmpeg/ffprobe command wrappers
- `assets.py` - folder scanning + random asset selection

## Quick start

1. Create folders in your project directory:

```text
videos/
music/
images/
sounds/
```

2. Add media files.
3. Start app:

```bash
python main.py
```

4. Configure text + duration options and click **Generate Promo**.

Output is written to `output/`.

## Notes

- `sounds/` is scanned and ready for extension.
- Clip copy-cut (`-c copy`) may fail for some keyframe layouts; app auto-falls back to re-encode.
