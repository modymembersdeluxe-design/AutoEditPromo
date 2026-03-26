from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from assets import choose_random, random_segment_start, scan_asset_folders
from ffmpeg_utils import (
    build_xfade_filter,
    ensure_ffmpeg_available,
    extract_segment,
    get_media_info,
    mix_audio_or_silence,
    normalize_clip,
    run_cmd,
)


@dataclass(slots=True)
class PromoRequest:
    base_dir: Path
    title: str
    subtitle: str
    messages: list[str]
    clip_count: int = 6
    target_duration: int = 24
    fallback_bpm: int = 120


class PromoEditor:
    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self.log = logger or (lambda msg: None)

    def generate(self, req: PromoRequest) -> list[Path]:
        ensure_ffmpeg_available()
        assets = scan_asset_folders(req.base_dir)

        if not assets["videos"] and not assets["images"]:
            raise ValueError("No source media found. Put files in /videos or /images.")

        self.log(
            "Discovered assets: "
            f"videos={len(assets['videos'])}, music={len(assets['music'])}, "
            f"images={len(assets['images'])}, sounds={len(assets['sounds'])}"
        )

        output_dir = req.base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        music = assets["music"][0] if assets["music"] else None
        if music:
            self.log(f"Music track selected: {music.name}")
        else:
            self.log("No music found. Will render with generated silent audio track.")

        bpm = req.fallback_bpm
        beat_len = max(60.0 / bpm, 0.2)
        seg_len = max(beat_len * 2, 1.0)

        rough_total = max(req.target_duration, 6)
        count_from_duration = max(int(rough_total / seg_len), 2)
        planned_count = max(min(req.clip_count, 40), count_from_duration)

        chosen_videos = choose_random(assets["videos"], min(planned_count, len(assets["videos"])))
        remaining = planned_count - len(chosen_videos)
        chosen_images = choose_random(assets["images"], remaining)

        with tempfile.TemporaryDirectory(prefix="autopromo_") as td:
            temp_dir = Path(td)
            raw_clips: list[Path] = []

            for i, vid in enumerate(chosen_videos):
                info = get_media_info(vid)
                self.log(
                    f"Analyzed {vid.name}: duration={info['duration']:.2f}s, "
                    f"res={int(info['width'])}x{int(info['height'])}, fps={info['fps']:.2f}"
                )
                start = random_segment_start(float(info["duration"]), seg_len)
                cut_out = temp_dir / f"cut_{i:03d}.mp4"
                extract_segment(vid, cut_out, start, seg_len, self.log)
                raw_clips.append(cut_out)

            for j, img in enumerate(chosen_images):
                idx = len(raw_clips)
                img_clip = temp_dir / f"img_{idx:03d}.mp4"
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(img),
                    "-t",
                    f"{seg_len:.3f}",
                    "-vf",
                    "zoompan=z='min(zoom+0.0008,1.15)':d=1:s=1280x720,format=yuv420p",
                    "-r",
                    "30",
                    "-an",
                    "-c:v",
                    "libx264",
                    str(img_clip),
                ]
                run_cmd(cmd)
                raw_clips.append(img_clip)
                self.log(f"Created image clip from {img.name}")

            if not raw_clips:
                raise ValueError("Could not create any intermediate clips.")

            # Ensure enough clips even if user has tiny asset set.
            while len(raw_clips) < 2:
                clone = temp_dir / f"clone_{len(raw_clips):03d}.mp4"
                shutil.copy2(raw_clips[0], clone)
                raw_clips.append(clone)

            out_paths: list[Path] = []
            for tag, (w, h) in (("16x9", (1280, 720)), ("4x3", (960, 720))):
                self.log(f"Rendering aspect ratio {tag} ({w}x{h})")
                out_paths.append(
                    self._render_variant(
                        raw_clips=raw_clips,
                        req=req,
                        music=music,
                        output_dir=output_dir,
                        width=w,
                        height=h,
                        seg_len=seg_len,
                        suffix=tag,
                        temp_dir=temp_dir,
                    )
                )

            default_out = output_dir / "final_promo.mp4"
            shutil.copy2(out_paths[0], default_out)
            out_paths.append(default_out)
            self.log(f"Default output written: {default_out}")
            return out_paths

    def _render_variant(
        self,
        *,
        raw_clips: list[Path],
        req: PromoRequest,
        music: Path | None,
        output_dir: Path,
        width: int,
        height: int,
        seg_len: float,
        suffix: str,
        temp_dir: Path,
    ) -> Path:
        norm_clips: list[Path] = []
        for i, clip in enumerate(raw_clips):
            norm = temp_dir / f"norm_{suffix}_{i:03d}.mp4"
            normalize_clip(clip, norm, width, height, 30)
            norm_clips.append(norm)

        filter_base, out_label = build_xfade_filter(len(norm_clips), seg_len)
        composed = temp_dir / f"composed_{suffix}.mp4"
        cmd = ["ffmpeg", "-y"]
        for c in norm_clips:
            cmd += ["-i", str(c)]
        cmd += [
            "-filter_complex",
            filter_base,
            "-map",
            out_label,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            str(composed),
        ]
        run_cmd(cmd)

        total_duration = max(seg_len * len(norm_clips) - (len(norm_clips) - 1) * 0.35, 1.0)
        av = temp_dir / f"av_{suffix}.mp4"
        mix_audio_or_silence(composed, music, av, total_duration)

        final = output_dir / f"final_promo_{suffix}.mp4"
        draw = self._drawtext_filter(req, total_duration)
        cmd_final = [
            "ffmpeg",
            "-y",
            "-i",
            str(av),
            "-vf",
            draw,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            str(final),
        ]
        run_cmd(cmd_final)
        self.log(f"Exported {final.name}")
        return final

    def _drawtext_filter(self, req: PromoRequest, total_duration: float) -> str:
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")

        filters = [
            "fade=t=in:st=0:d=0.5",
            f"fade=t=out:st={max(total_duration - 0.7, 0.0):.2f}:d=0.7",
        ]

        if req.title:
            filters.append(
                "drawtext=text='{}':x=(w-text_w)/2:y=h*0.08:fontcolor=white:fontsize=54:"
                "box=1:boxcolor=black@0.45:boxborderw=16:enable='between(t,0,4)'".format(esc(req.title))
            )
        if req.subtitle:
            filters.append(
                "drawtext=text='{}':x=(w-text_w)/2:y=h*0.18:fontcolor=white:fontsize=30:"
                "box=1:boxcolor=black@0.35:boxborderw=10:enable='between(t,1,6)'".format(esc(req.subtitle))
            )

        msg_window = 2.8
        for idx, msg in enumerate(req.messages):
            start = 2.0 + idx * msg_window
            end = min(start + msg_window, total_duration - 0.2)
            if end <= start:
                break
            filters.append(
                "drawtext=text='{}':x=(w-text_w)/2:y=h*0.82:fontcolor=yellow:fontsize=38:"
                "box=1:boxcolor=black@0.4:boxborderw=12:enable='between(t,{:.2f},{:.2f})'".format(
                    esc(msg), start, end
                )
            )

        return ",".join(filters)
