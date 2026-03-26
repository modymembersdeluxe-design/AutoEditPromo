# AutoEditPromo

AutoEditPromo is a Python desktop GUI app that auto-generates long or short promo/remix/song videos from local media using **FFmpeg** and **FFprobe**.

## Folders scanned

- `videos/`
- `music/`
- `images/`
- `sounds/`

## New Mega Deluxe controls

### Auto-Remix & Auto-Edit
- Beat-aligned remix toggle
- Auto-remix support toggle
- Theme transition toggle
- Auto-cut / action-point detection toggles
- Auto-edit support toggle

### Music & Audio features
- Music remix + auto-fade workflow controls
- Event-driven SFX placement toggle
- Voiceover/speech-priority strategy selector
- Auto-volume leveling (speech > music > effects)
- Auto-mute modes: `off`, `mute_music`, `mute_all`

### Output options
- Aspect ratios: 16:9, 4:3, 9:16
- Export: MP4
- Low-res preview render option
- Quality profiles: `preview_360p`, `hd`, `custom`
- Mega Deluxe custom controls: Width, Height, FPS, Bitrate

### Build modes
- `promo`
- `remix`
- `songs`
- `songs_remix`

### Mega Deluxe generation settings
- Min Clip / Max Clip / Total Clips
- Random seed for deterministic generation behavior
- Transition seconds, Dance intensity, Promo intensity
- Intro asset / Outro asset insertion
- Generated naming preset (default: `Generated Mega Deluxe Promo & Remix & Songs`)
- Target duration with auto-expanded clip sequencing for longer promos

## Requirements
- Python 3.11+
- FFmpeg + FFprobe available in `PATH`

## Run

```bash
python main.py
```

## Output
Generated files are written to `output/`, including `output/final_promo.mp4`.

## Font note
- To avoid `Fontconfig error: Cannot load default config file`, the app uses explicit `fontfile=` drawtext paths.
- If no known font file is found on your system, generation continues and skips text overlays instead of failing.
