from __future__ import annotations

import random
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _list_files(folder: Path, exts: set[str]) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in exts]


def scan_asset_folders(base_dir: Path) -> dict[str, list[Path]]:
    return {
        "videos": _list_files(base_dir / "videos", VIDEO_EXTS),
        "music": _list_files(base_dir / "music", AUDIO_EXTS),
        "images": _list_files(base_dir / "images", IMAGE_EXTS),
        "sounds": _list_files(base_dir / "sounds", AUDIO_EXTS),
    }


def choose_random(items: list[Path], count: int) -> list[Path]:
    if not items or count <= 0:
        return []
    if count >= len(items):
        pool = items.copy()
        random.shuffle(pool)
        return pool
    return random.sample(items, count)


def random_segment_start(duration: float, seg_len: float) -> float:
    if duration <= seg_len:
        return 0.0
    return random.uniform(0, max(duration - seg_len, 0.0))
