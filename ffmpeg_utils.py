from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and proc.returncode != 0:
        quoted = " ".join(shlex.quote(c) for c in cmd)
        raise FFmpegError(f"Command failed ({proc.returncode}): {quoted}\n{proc.stderr}")
    return proc


def ensure_ffmpeg_available() -> None:
    for exe in ("ffmpeg", "ffprobe"):
        proc = subprocess.run([exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise FFmpegError(f"{exe} not found in PATH.")


def ffprobe_media(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = run_cmd(cmd)
    raw = proc.stdout
    if raw is None:
        return {"format": {}, "streams": []}
    raw = raw.strip()
    if not raw:
        return {"format": {}, "streams": []}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"format": {}, "streams": []}


def parse_media_info(meta: dict) -> dict[str, float | int]:
    duration = float(meta.get("format", {}).get("duration", 0.0) or 0.0)
    streams = meta.get("streams", [])
    width = height = 0
    fps = 0.0
    for stream in streams:
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
            raw_fps = stream.get("avg_frame_rate", "0/1")
            try:
                num, den = raw_fps.split("/")
                fps = (float(num) / float(den)) if float(den) else 0.0
            except Exception:  # noqa: BLE001
                fps = 0.0
            break
    return {"duration": duration, "width": width, "height": height, "fps": fps}


def parse_tbpm(meta: dict) -> float | None:
    tags = meta.get("format", {}).get("tags", {}) or {}
    raw = tags.get("TBPM") or tags.get("tbpm") or tags.get("BPM") or tags.get("bpm")
    if raw is None:
        return None
    try:
        bpm = float(str(raw).strip())
    except ValueError:
        return None
    if bpm <= 0:
        return None
    return bpm


def get_media_info(path: Path) -> dict[str, float | int]:
    return parse_media_info(ffprobe_media(path))


def extract_segment(src: Path, dst: Path, start: float, duration: float, logger) -> None:
    copy_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-avoid_negative_ts",
        "1",
        "-c",
        "copy",
        str(dst),
    ]
    proc = run_cmd(copy_cmd, check=False)
    if proc.returncode == 0:
        logger(f"Segment copied without re-encode: {dst.name}")
        return

    logger(f"Copy-cut failed for {src.name}, falling back to re-encode segment.")
    recode_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        str(dst),
    ]
    run_cmd(recode_cmd, check=True)


def normalize_clip(
    src: Path, dst: Path, width: int, height: int, fps: int, *, preset: str = "veryfast", crf: int = 20
) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-an",
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        str(dst),
    ]
    run_cmd(cmd)


def build_xfade_filter(num_clips: int, seg_len: float, transition: float = 0.35) -> tuple[str, str]:
    if num_clips < 2:
        return "[0:v]format=yuv420p[vout]", "[vout]"

    parts: list[str] = []
    prev = "[0:v]"
    offset = max(seg_len - transition, 0.0)
    for i in range(1, num_clips):
        out = f"[x{i}]"
        parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={transition:.3f}:offset={offset:.3f}{out}"
        )
        prev = out
        offset += max(seg_len - transition, 0.01)
    parts.append(f"{prev}format=yuv420p[vout]")
    return ";".join(parts), "[vout]"


def mix_audio_or_silence(video_input: Path, music: Path | None, out: Path, duration: float) -> None:
    if music and music.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_input),
            "-stream_loop",
            "-1",
            "-i",
            str(music),
            "-filter_complex",
            "[1:a]atrim=duration={:.3f},afade=t=in:st=0:d=0.6,afade=t=out:st={:.3f}:d=0.8[a]".format(
                duration,
                max(duration - 0.8, 0.0),
            ),
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-shortest",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out),
        ]
        run_cmd(cmd)
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_input),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    run_cmd(cmd)
