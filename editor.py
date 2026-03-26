from __future__ import annotations

import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from assets import AUDIO_EXTS, VIDEO_EXTS, choose_random, random_segment_start, scan_asset_folders, scan_paths
from ffmpeg_utils import (
    FFmpegError,
    build_xfade_filter,
    ensure_ffmpeg_available,
    extract_segment,
    get_media_info,
    mix_audio_or_silence,
    normalize_clip,
    parse_tbpm,
    ffprobe_media,
    run_cmd,
)


@dataclass(slots=True)
class PromoRequest:
    base_dir: Path
    title: str
    subtitle: str
    messages: list[str]

    # Core timing / build
    min_clip_sec: float = 1.2
    max_clip_sec: float = 3.0
    total_clips: int = 12
    target_duration: int = 40
    fallback_bpm: int = 120
    random_seed: int | None = None
    transition_seconds: float = 0.35
    dance_intensity: float = 0.5
    promo_intensity: float = 0.5

    # Modes
    build_mode: str = "promo"  # promo / remix / songs / songs_remix
    auto_edit_enabled: bool = True
    auto_remix_enabled: bool = True
    beat_aligned: bool = True
    theme_transitions: bool = True
    auto_cut_detection: bool = True
    action_point_detection: bool = False

    # Music + audio
    music_remix_workflow: bool = True
    music_auto_fade: bool = True
    event_sfx_enabled: bool = False
    voiceover_priority: str = "speech_priority"  # speech_priority / balanced / music_priority
    auto_volume_leveling: bool = True
    auto_mute_mode: str = "off"  # off / mute_music / mute_all

    # Output controls
    aspect_16_9: bool = True
    aspect_4_3: bool = True
    aspect_9_16: bool = False
    export_mp4: bool = True
    preview_low_res: bool = False
    quality_profile: str = "hd"  # preview_360p / hd / custom
    custom_width: int = 1280
    custom_height: int = 720
    custom_fps: int = 30
    custom_bitrate_k: int = 3500

    # Assets and naming
    use_intro_asset: bool = False
    use_outro_asset: bool = False
    generated_name_preset: str = "Generated Mega Deluxe Promo & Remix & Songs"
    video_folders: list[Path] | None = None
    audio_folders: list[Path] | None = None
    recursive_scan: bool = False
    audio_mode: str = "random_one"  # random_one / combine_shuffled
    resolution: str = "1280x720"
    crf_quality: int = 20
    style_preset: str = "Clean 2000s"
    transition_mode: str = "fade"  # fade / cut
    dance_effects: int = 40
    dance_mode_preset: str = "Auto"  # Auto / Soft / Hard / Off
    audio_remix_mode: str = "Original"  # Original / Nightcore / Slow Jam / Hyper Dance
    instant_vfx: bool = False
    draft_mode_10x: bool = False


class PromoEditor:
    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self.log = logger or (lambda msg: None)

    def generate(self, req: PromoRequest) -> list[Path]:
        ensure_ffmpeg_available()
        if not req.export_mp4:
            raise ValueError("At least MP4 export must be enabled.")

        if req.random_seed is not None:
            random.seed(req.random_seed)

        assets = scan_asset_folders(req.base_dir)
        if req.video_folders:
            assets["videos"] = sorted(
                set(assets["videos"] + scan_paths(req.video_folders, VIDEO_EXTS, recursive=req.recursive_scan))
            )
        if req.audio_folders:
            assets["music"] = sorted(
                set(assets["music"] + scan_paths(req.audio_folders, AUDIO_EXTS, recursive=req.recursive_scan))
            )
        if not assets["videos"] and not assets["images"]:
            raise ValueError("No source media found. Put files in /videos or /images.")

        self.log(
            f"Mode={req.build_mode}, AutoEdit={req.auto_edit_enabled}, AutoRemix={req.auto_remix_enabled}, "
            f"BeatAligned={req.beat_aligned}, ThemeTransitions={req.theme_transitions}"
        )
        self.log(
            "Discovered assets: "
            f"videos={len(assets['videos'])}, music={len(assets['music'])}, "
            f"images={len(assets['images'])}, sounds={len(assets['sounds'])}"
        )

        output_dir = req.base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        music = self._select_music_source(req, assets["music"], output_dir)
        if req.auto_mute_mode == "mute_all":
            music = None
            self.log("Auto-mute mode: mute_all")
        elif req.auto_mute_mode == "mute_music":
            music = None
            self.log("Auto-mute mode: mute_music")

        if music and req.audio_remix_mode != "Original":
            remixed = output_dir / "_temp_remix_audio.m4a"
            self._remix_audio(music, remixed, req.audio_remix_mode)
            music = remixed

        source_bpm = self._detect_bpm(music) if music else None
        if source_bpm:
            self.log(f"Detected TBPM/BPM from audio tags: {source_bpm:.1f}")
            req.fallback_bpm = int(source_bpm)
        seg_len = self._compute_segment_length(req)
        planned_count = self._compute_clip_count(req, seg_len)

        chosen_videos = choose_random(assets["videos"], min(planned_count, len(assets["videos"])))
        remaining = planned_count - len(chosen_videos)
        chosen_images = choose_random(assets["images"], remaining)

        with tempfile.TemporaryDirectory(prefix="autopromo_") as td:
            temp_dir = Path(td)
            raw_clips: list[Path] = []

            if req.use_intro_asset and assets["images"]:
                intro = self._create_still_clip(assets["images"][0], temp_dir / "intro.mp4", max(seg_len, 2.0))
                raw_clips.append(intro)
                self.log(f"Intro asset inserted: {assets['images'][0].name}")

            for i, vid in enumerate(chosen_videos):
                info = get_media_info(vid)
                self.log(
                    f"Analyzed {vid.name}: duration={info['duration']:.2f}s, "
                    f"res={int(info['width'])}x{int(info['height'])}, fps={info['fps']:.2f}"
                )
                local_seg = self._segment_for_clip(req, seg_len)
                start = random_segment_start(float(info["duration"]), local_seg)
                cut_out = temp_dir / f"cut_{i:03d}.mp4"
                extract_segment(vid, cut_out, start, local_seg, self.log)
                raw_clips.append(cut_out)

            for img in chosen_images:
                idx = len(raw_clips)
                img_clip = self._create_still_clip(img, temp_dir / f"img_{idx:03d}.mp4", seg_len)
                raw_clips.append(img_clip)
                self.log(f"Created image clip from {img.name}")

            if req.use_outro_asset and assets["images"]:
                outro = self._create_still_clip(assets["images"][-1], temp_dir / "outro.mp4", max(seg_len, 2.0))
                raw_clips.append(outro)
                self.log(f"Outro asset inserted: {assets['images'][-1].name}")

            if not raw_clips:
                raise ValueError("Could not create any intermediate clips.")
            while len(raw_clips) < 2:
                clone = temp_dir / f"clone_{len(raw_clips):03d}.mp4"
                shutil.copy2(raw_clips[0], clone)
                raw_clips.append(clone)

            out_paths: list[Path] = []
            for tag, (w, h) in self._target_variants(req):
                self.log(f"Rendering aspect ratio {tag} ({w}x{h})")
                out_paths.append(
                    self._render_variant(
                        raw_clips=raw_clips,
                        req=req,
                        music=music,
                        sfx_pool=assets["sounds"],
                        output_dir=output_dir,
                        width=w,
                        height=h,
                        fps=max(req.custom_fps, 12),
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

    def _compute_segment_length(self, req: PromoRequest) -> float:
        if req.beat_aligned:
            beat_len = max(60.0 / max(req.fallback_bpm, 1), 0.2)
            base = beat_len * (1.5 + req.dance_intensity)
        else:
            base = (req.min_clip_sec + req.max_clip_sec) / 2
        return min(max(base, req.min_clip_sec), req.max_clip_sec)

    def _select_music_source(self, req: PromoRequest, music_files: list[Path], output_dir: Path) -> Path | None:
        if not music_files:
            return None
        if req.audio_mode == "combine_shuffled" and len(music_files) > 1:
            pool = music_files.copy()
            random.shuffle(pool)
            concat_file = output_dir / "_temp_music_concat.txt"
            lines: list[str] = []
            for p in pool:
                escaped = str(p).replace("'", "'\\''")
                lines.append(f"file '{escaped}'\n")
            concat_file.write_text("".join(lines), encoding="utf-8")
            out = output_dir / "_temp_music_combined.m4a"
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out),
            ]
            run_cmd(cmd)
            self.log(f"Music mode combine_shuffled selected ({len(pool)} tracks).")
            return out
        picked = random.choice(music_files)
        self.log(f"Music mode random_one selected: {picked.name}")
        return picked

    def _detect_bpm(self, music: Path) -> float | None:
        try:
            meta = ffprobe_media(music)
            return parse_tbpm(meta)
        except Exception:  # noqa: BLE001
            return None

    def _remix_audio(self, src: Path, out: Path, mode: str) -> None:
        if mode == "Nightcore":
            af = "asetrate=48000*1.18,aresample=48000,atempo=1.06"
        elif mode == "Slow Jam":
            af = "asetrate=44100*0.9,aresample=44100,atempo=0.92"
        elif mode == "Hyper Dance":
            af = "asetrate=48000*1.3,aresample=48000,atempo=1.15"
        else:
            shutil.copy2(src, out)
            return
        run_cmd(["ffmpeg", "-y", "-i", str(src), "-af", af, "-c:a", "aac", "-b:a", "192k", str(out)])

    def _compute_clip_count(self, req: PromoRequest, seg_len: float) -> int:
        auto_count = max(int(req.target_duration / max(seg_len - req.transition_seconds, 0.3)), 2)
        return max(min(req.total_clips, 200), auto_count)

    def _segment_for_clip(self, req: PromoRequest, seg_len: float) -> float:
        if req.auto_cut_detection or req.action_point_detection:
            variance = 0.5 if req.action_point_detection else 0.25
            jitter = random.uniform(-variance, variance)
            return min(max(seg_len + jitter, req.min_clip_sec), req.max_clip_sec)
        return seg_len

    def _target_variants(self, req: PromoRequest) -> list[tuple[str, tuple[int, int]]]:
        if req.quality_profile == "custom":
            base = (max(req.custom_width, 64), max(req.custom_height, 64))
        elif req.quality_profile == "preview_360p":
            base = (640, 360)
        else:
            try:
                rw, rh = req.resolution.lower().split("x", 1)
                base = (max(int(rw), 64), max(int(rh), 64))
            except Exception:  # noqa: BLE001
                base = (1280, 720)

        variants: list[tuple[str, tuple[int, int]]] = []
        if req.aspect_16_9:
            variants.append(("16x9", self._fit_ratio(base, 16, 9)))
        if req.aspect_4_3:
            variants.append(("4x3", self._fit_ratio(base, 4, 3)))
        if req.aspect_9_16:
            variants.append(("9x16", self._fit_ratio((base[1], base[0]), 9, 16)))
        if not variants:
            variants.append(("16x9", self._fit_ratio(base, 16, 9)))

        if req.preview_low_res and ("preview_360p", (640, 360)) not in variants:
            variants.append(("preview_360p", (640, 360)))
        return variants

    def _fit_ratio(self, base: tuple[int, int], rw: int, rh: int) -> tuple[int, int]:
        w, h = base
        if w / h > rw / rh:
            w = int(h * rw / rh)
        else:
            h = int(w * rh / rw)
        return max(w, 64), max(h, 64)

    def _create_still_clip(self, image: Path, out: Path, duration: float) -> Path:
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            f"{duration:.3f}",
            "-vf",
            "zoompan=z='min(zoom+0.0008,1.15)':d=1:s=1280x720,format=yuv420p",
            "-r",
            "30",
            "-an",
            "-c:v",
            "libx264",
            str(out),
        ]
        run_cmd(cmd)
        return out

    def _render_variant(
        self,
        *,
        raw_clips: list[Path],
        req: PromoRequest,
        music: Path | None,
        sfx_pool: list[Path],
        output_dir: Path,
        width: int,
        height: int,
        fps: int,
        seg_len: float,
        suffix: str,
        temp_dir: Path,
    ) -> Path:
        preset = "ultrafast" if req.draft_mode_10x else "veryfast"
        crf = min(max(req.crf_quality + (8 if req.draft_mode_10x else 0), 12), 38)
        norm_clips: list[Path] = []
        for i, clip in enumerate(raw_clips):
            norm = temp_dir / f"norm_{suffix}_{i:03d}.mp4"
            normalize_clip(clip, norm, width, height, fps, preset=preset, crf=crf)
            norm_clips.append(norm)

        composed = temp_dir / f"composed_{suffix}.mp4"
        if req.transition_mode == "fade" and req.auto_edit_enabled and req.theme_transitions:
            filter_base, out_label = build_xfade_filter(len(norm_clips), seg_len, req.transition_seconds)
            self._compose_clips(norm_clips, composed, filter_base, out_label, preset=preset, crf=crf)
        else:
            self._concat_only(norm_clips, composed, preset=preset, crf=crf)

        total_duration = max(seg_len * len(norm_clips) - (len(norm_clips) - 1) * req.transition_seconds, 1.0)
        av = temp_dir / f"av_{suffix}.mp4"
        mix_audio_or_silence(composed, music, av, total_duration)

        mixed = temp_dir / f"mixed_{suffix}.mp4"
        if req.event_sfx_enabled and sfx_pool:
            self._apply_event_sfx(av, sfx_pool[0], mixed, total_duration, req)
            av = mixed

        final = output_dir / f"{req.generated_name_preset} - {req.build_mode} - {suffix}.mp4"
        font_file = self._find_font_file(req.base_dir)
        if font_file is None:
            self.log("Font file not found; skipping drawtext overlays to avoid Fontconfig errors.")
        draw = self._drawtext_filter(req, total_duration, font_file)
        draw = self._compose_vf(draw, req)
        bitrate = f"{max(req.custom_bitrate_k, 400)}k"
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
            preset,
            "-crf",
            str(crf),
            "-b:v",
            bitrate,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(final),
        ]
        run_cmd(cmd_final)
        self.log(f"Exported {final.name}")
        return final

    def _compose_clips(
        self, norm_clips: list[Path], composed: Path, filter_base: str, out_label: str, *, preset: str, crf: int
    ) -> None:
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
            preset,
            "-crf",
            str(crf),
            str(composed),
        ]
        try:
            run_cmd(cmd)
            return
        except FFmpegError:
            self.log("xfade composition failed on this system; falling back to stable concat mode.")
        self._concat_only(norm_clips, composed, preset=preset, crf=crf)

    def _concat_only(self, norm_clips: list[Path], composed: Path, *, preset: str, crf: int) -> None:
        concat_inputs = "".join(f"[{i}:v]" for i in range(len(norm_clips)))
        concat_filter = f"{concat_inputs}concat=n={len(norm_clips)}:v=1:a=0[vout]"
        fallback = ["ffmpeg", "-y"]
        for c in norm_clips:
            fallback += ["-i", str(c)]
        fallback += [
            "-filter_complex",
            concat_filter,
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            str(composed),
        ]
        run_cmd(fallback)

    def _compose_vf(self, draw_filter: str, req: PromoRequest) -> str:
        chain = [draw_filter]
        style = req.style_preset
        if style == "VHS Deluxe":
            chain.append("eq=contrast=1.1:saturation=0.8,noise=alls=12:allf=t+u")
        elif style == "CRT Glow":
            chain.append("gblur=sigma=1.2,eq=brightness=0.03:saturation=1.2")
        elif style == "Lo‑Fi Old Net":
            chain.append("eq=contrast=0.95:saturation=0.7,noise=alls=18:allf=t")
        else:  # Clean 2000s
            chain.append("eq=contrast=1.03:saturation=1.05")

        dance_power = max(min(req.dance_effects, 100), 0) / 100.0
        if req.dance_mode_preset == "Off":
            dance_power = 0.0
        elif req.dance_mode_preset == "Soft":
            dance_power = min(dance_power, 0.35)
        elif req.dance_mode_preset == "Hard":
            dance_power = max(dance_power, 0.7)
        if req.instant_vfx or dance_power > 0:
            sat = 1.0 + dance_power * 0.35
            sharp = 3 + int(dance_power * 5)
            chain.append(f"eq=saturation={sat:.2f},unsharp={sharp}:{sharp}:0.7")
        return ",".join([c for c in chain if c])

    def _apply_event_sfx(self, av_input: Path, sfx_file: Path, out: Path, total_duration: float, req: PromoRequest) -> None:
        if req.voiceover_priority == "speech_priority":
            music_gain = 0.75
            sfx_gain = 0.65
        elif req.voiceover_priority == "music_priority":
            music_gain = 1.0
            sfx_gain = 0.45
        else:
            music_gain = 0.9
            sfx_gain = 0.55

        if not req.auto_volume_leveling:
            music_gain = sfx_gain = 1.0

        event_start = max(total_duration * 0.35, 0.1)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(av_input),
            "-stream_loop",
            "-1",
            "-i",
            str(sfx_file),
            "-filter_complex",
            (
                f"[0:a]volume={music_gain}[base];"
                f"[1:a]atrim=0:2.0,adelay={int(event_start*1000)}|{int(event_start*1000)},volume={sfx_gain}[s];"
                "[base][s]amix=inputs=2:normalize=0[a]"
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
            str(out),
        ]
        run_cmd(cmd)

    def _find_font_file(self, base_dir: Path) -> Path | None:
        candidates = [
            base_dir / "fonts" / "DejaVuSans.ttf",
            base_dir / "fonts" / "Arial.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _drawtext_filter(self, req: PromoRequest, total_duration: float, font_file: Path | None) -> str:
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")

        filters = [
            "fade=t=in:st=0:d=0.5",
            f"fade=t=out:st={max(total_duration - 0.7, 0.0):.2f}:d=0.7",
        ]
        if font_file is None:
            return ",".join(filters)

        font_arg = f"fontfile='{esc(str(font_file))}':"

        mode_text = f"{req.build_mode.upper()} | Remix={int(req.auto_remix_enabled)} | AutoEdit={int(req.auto_edit_enabled)}"
        filters.append(
            f"drawtext={font_arg}text='{esc(mode_text)}':x=(w-text_w)/2:y=h*0.03:fontcolor=white:fontsize=24:"
            "box=1:boxcolor=black@0.35:boxborderw=8:enable='between(t,0,6)'"
        )

        if req.title:
            filters.append(
                f"drawtext={font_arg}text='{esc(req.title)}':x=(w-text_w)/2:y=h*0.10:fontcolor=white:fontsize=52:"
                "box=1:boxcolor=black@0.45:boxborderw=16:enable='between(t,0,4)'"
            )
        if req.subtitle:
            filters.append(
                f"drawtext={font_arg}text='{esc(req.subtitle)}':x=(w-text_w)/2:y=h*0.20:fontcolor=white:fontsize=30:"
                "box=1:boxcolor=black@0.35:boxborderw=10:enable='between(t,1,6)'"
            )

        msg_window = 2.8
        for idx, msg in enumerate(req.messages):
            start = 2.0 + idx * msg_window
            end = min(start + msg_window, total_duration - 0.2)
            if end <= start:
                break
            filters.append(
                f"drawtext={font_arg}text='{esc(msg)}':x=(w-text_w)/2:y=h*0.82:fontcolor=yellow:fontsize=38:"
                f"box=1:boxcolor=black@0.4:boxborderw=12:enable='between(t,{start:.2f},{end:.2f})'"
            )

        return ",".join(filters)
