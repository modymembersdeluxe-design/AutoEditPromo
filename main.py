from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from editor import PromoEditor, PromoRequest


class AutoEditPromoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AutoEditPromo - Mega Deluxe")
        self.geometry("980x760")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.project_dir = tk.StringVar(value=str(Path.cwd()))
        self.title_text = tk.StringVar(value="Generated Mega Deluxe Promo")
        self.subtitle_text = tk.StringVar(value="Auto-Remix & Auto-Edit")
        self.messages_text = tk.StringVar(value="Beat-synced cuts|Promo energy|Generated automatically")

        self.build_mode = tk.StringVar(value="promo")
        self.min_clip_sec = tk.DoubleVar(value=1.2)
        self.max_clip_sec = tk.DoubleVar(value=3.0)
        self.total_clips = tk.IntVar(value=14)
        self.target_duration = tk.IntVar(value=45)
        self.bpm = tk.IntVar(value=120)
        self.seed = tk.StringVar(value="")
        self.transition_seconds = tk.DoubleVar(value=0.35)
        self.dance_intensity = tk.DoubleVar(value=0.6)
        self.promo_intensity = tk.DoubleVar(value=0.7)

        self.auto_edit_enabled = tk.BooleanVar(value=True)
        self.auto_remix_enabled = tk.BooleanVar(value=True)
        self.beat_aligned = tk.BooleanVar(value=True)
        self.theme_transitions = tk.BooleanVar(value=True)
        self.auto_cut_detection = tk.BooleanVar(value=True)
        self.action_point_detection = tk.BooleanVar(value=False)

        self.music_remix_workflow = tk.BooleanVar(value=True)
        self.music_auto_fade = tk.BooleanVar(value=True)
        self.event_sfx_enabled = tk.BooleanVar(value=False)
        self.voiceover_priority = tk.StringVar(value="speech_priority")
        self.auto_volume_leveling = tk.BooleanVar(value=True)
        self.auto_mute_mode = tk.StringVar(value="off")

        self.aspect_16_9 = tk.BooleanVar(value=True)
        self.aspect_4_3 = tk.BooleanVar(value=True)
        self.aspect_9_16 = tk.BooleanVar(value=False)
        self.export_mp4 = tk.BooleanVar(value=True)
        self.preview_low_res = tk.BooleanVar(value=False)
        self.quality_profile = tk.StringVar(value="hd")
        self.custom_width = tk.IntVar(value=1280)
        self.custom_height = tk.IntVar(value=720)
        self.custom_fps = tk.IntVar(value=30)
        self.custom_bitrate = tk.IntVar(value=3500)

        self.use_intro_asset = tk.BooleanVar(value=False)
        self.use_outro_asset = tk.BooleanVar(value=False)
        self.naming_preset = tk.StringVar(value="Generated Mega Deluxe Promo & Remix & Songs")

        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(root)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Project folder").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.project_dir, width=90).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(top, text="Browse", command=self._pick_project_dir).pack(side=tk.LEFT)

        nb = ttk.Notebook(root)
        nb.pack(fill=tk.BOTH, expand=True, pady=8)

        self._build_generation_tab(nb)
        self._build_audio_tab(nb)
        self._build_output_tab(nb)

        ttk.Button(root, text="Generate Mega Deluxe Promo", command=self._start_generation).pack(fill=tk.X, pady=(4, 8))

        self.log_widget = tk.Text(root, height=13, wrap="word", state="disabled")
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    def _build_generation_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Build & Remix")

        r = 0
        ttk.Label(tab, text="Title").grid(row=r, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.title_text, width=55).grid(row=r, column=1, sticky="ew", padx=6)
        r += 1
        ttk.Label(tab, text="Subtitle").grid(row=r, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.subtitle_text).grid(row=r, column=1, sticky="ew", padx=6)
        r += 1
        ttk.Label(tab, text="Messages (| separated)").grid(row=r, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.messages_text).grid(row=r, column=1, sticky="ew", padx=6)

        r += 1
        ttk.Label(tab, text="Build mode").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(tab, textvariable=self.build_mode, values=["promo", "remix", "songs", "songs_remix"], state="readonly").grid(row=r, column=1, sticky="w", pady=(8, 0))

        r += 1
        timings = ttk.Frame(tab)
        timings.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for i, (label, var) in enumerate([
            ("Min Clip", self.min_clip_sec),
            ("Max Clip", self.max_clip_sec),
            ("Total Clips", self.total_clips),
            ("Target Duration", self.target_duration),
            ("BPM", self.bpm),
            ("Transition Sec", self.transition_seconds),
            ("Dance Intensity", self.dance_intensity),
            ("Promo Intensity", self.promo_intensity),
        ]):
            ttk.Label(timings, text=label).grid(row=i // 4 * 2, column=i % 4, sticky="w", padx=4)
            ttk.Entry(timings, textvariable=var, width=10).grid(row=i // 4 * 2 + 1, column=i % 4, sticky="w", padx=4)

        r += 1
        ttk.Label(tab, text="Random seed (optional)").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(tab, textvariable=self.seed, width=18).grid(row=r, column=1, sticky="w", pady=(8, 0))

        r += 1
        toggles = ttk.LabelFrame(tab, text="Auto-Remix / Auto-Edit Controls", padding=8)
        toggles.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(toggles, text="Beat-aligned remix", variable=self.beat_aligned).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(toggles, text="Auto-remix support", variable=self.auto_remix_enabled).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(toggles, text="Theme transitions", variable=self.theme_transitions).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(toggles, text="Auto-cut detection", variable=self.auto_cut_detection).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(toggles, text="Action-point detection", variable=self.action_point_detection).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(toggles, text="Auto-edit support", variable=self.auto_edit_enabled).grid(row=2, column=1, sticky="w")

        r += 1
        io_frame = ttk.LabelFrame(tab, text="Intro / Outro & Naming", padding=8)
        io_frame.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(io_frame, text="Insert Intro Asset", variable=self.use_intro_asset).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(io_frame, text="Insert Outro Asset", variable=self.use_outro_asset).grid(row=0, column=1, sticky="w")
        ttk.Label(io_frame, text="Generated naming preset").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(io_frame, textvariable=self.naming_preset, width=60).grid(row=1, column=1, sticky="ew", pady=(8, 0))

        tab.columnconfigure(1, weight=1)

    def _build_audio_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Music & Audio")

        box = ttk.LabelFrame(tab, text="Music & Audio Features", padding=8)
        box.pack(fill=tk.X)
        ttk.Checkbutton(box, text="Music remix workflow", variable=self.music_remix_workflow).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(box, text="Auto-fade workflow", variable=self.music_auto_fade).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(box, text="Event-driven SFX placement", variable=self.event_sfx_enabled).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(box, text="Auto-volume leveling (speech > music > effects)", variable=self.auto_volume_leveling).grid(row=1, column=1, sticky="w")

        ttk.Label(box, text="Voiceover/speech strategy").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(box, textvariable=self.voiceover_priority, values=["speech_priority", "balanced", "music_priority"], state="readonly", width=20).grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(box, text="Auto-mute mode").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(box, textvariable=self.auto_mute_mode, values=["off", "mute_music", "mute_all"], state="readonly", width=20).grid(row=3, column=1, sticky="w", pady=(8, 0))

    def _build_output_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Output")

        out = ttk.LabelFrame(tab, text="Output Options", padding=8)
        out.pack(fill=tk.X)
        ttk.Checkbutton(out, text="16:9", variable=self.aspect_16_9).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(out, text="4:3", variable=self.aspect_4_3).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(out, text="9:16", variable=self.aspect_9_16).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(out, text="Export MP4", variable=self.export_mp4).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(out, text="Preview low-res render", variable=self.preview_low_res).grid(row=1, column=1, sticky="w")

        ttk.Label(out, text="Quality profile").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(out, textvariable=self.quality_profile, values=["preview_360p", "hd", "custom"], state="readonly", width=15).grid(row=2, column=1, sticky="w", pady=(8, 0))

        deluxe = ttk.LabelFrame(tab, text="Mega Deluxe Generation Settings", padding=8)
        deluxe.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(deluxe, text="Width").grid(row=0, column=0, sticky="w")
        ttk.Entry(deluxe, textvariable=self.custom_width, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(deluxe, text="Height").grid(row=0, column=2, sticky="w")
        ttk.Entry(deluxe, textvariable=self.custom_height, width=10).grid(row=0, column=3, sticky="w")
        ttk.Label(deluxe, text="FPS").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(deluxe, textvariable=self.custom_fps, width=10).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(deluxe, text="Bitrate (k)").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(deluxe, textvariable=self.custom_bitrate, width=10).grid(row=1, column=3, sticky="w", pady=(6, 0))

    def _pick_project_dir(self) -> None:
        picked = filedialog.askdirectory(initialdir=self.project_dir.get())
        if picked:
            self.project_dir.set(picked)

    def _seed_value(self) -> int | None:
        s = self.seed.get().strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return abs(hash(s)) % (2**31)

    def _start_generation(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("AutoEditPromo", "Generation already running.")
            return

        req = PromoRequest(
            base_dir=Path(self.project_dir.get()).expanduser().resolve(),
            title=self.title_text.get().strip(),
            subtitle=self.subtitle_text.get().strip(),
            messages=[m.strip() for m in self.messages_text.get().split("|") if m.strip()],
            build_mode=self.build_mode.get(),
            min_clip_sec=self.min_clip_sec.get(),
            max_clip_sec=self.max_clip_sec.get(),
            total_clips=self.total_clips.get(),
            target_duration=self.target_duration.get(),
            fallback_bpm=self.bpm.get(),
            random_seed=self._seed_value(),
            transition_seconds=self.transition_seconds.get(),
            dance_intensity=self.dance_intensity.get(),
            promo_intensity=self.promo_intensity.get(),
            auto_edit_enabled=self.auto_edit_enabled.get(),
            auto_remix_enabled=self.auto_remix_enabled.get(),
            beat_aligned=self.beat_aligned.get(),
            theme_transitions=self.theme_transitions.get(),
            auto_cut_detection=self.auto_cut_detection.get(),
            action_point_detection=self.action_point_detection.get(),
            music_remix_workflow=self.music_remix_workflow.get(),
            music_auto_fade=self.music_auto_fade.get(),
            event_sfx_enabled=self.event_sfx_enabled.get(),
            voiceover_priority=self.voiceover_priority.get(),
            auto_volume_leveling=self.auto_volume_leveling.get(),
            auto_mute_mode=self.auto_mute_mode.get(),
            aspect_16_9=self.aspect_16_9.get(),
            aspect_4_3=self.aspect_4_3.get(),
            aspect_9_16=self.aspect_9_16.get(),
            export_mp4=self.export_mp4.get(),
            preview_low_res=self.preview_low_res.get(),
            quality_profile=self.quality_profile.get(),
            custom_width=self.custom_width.get(),
            custom_height=self.custom_height.get(),
            custom_fps=self.custom_fps.get(),
            custom_bitrate_k=self.custom_bitrate.get(),
            use_intro_asset=self.use_intro_asset.get(),
            use_outro_asset=self.use_outro_asset.get(),
            generated_name_preset=self.naming_preset.get().strip() or "Generated Mega Deluxe Promo & Remix & Songs",
        )

        self._append_log(f"Starting generation in: {req.base_dir}")
        self.worker = threading.Thread(target=self._run_editor, args=(req,), daemon=True)
        self.worker.start()

    def _run_editor(self, req: PromoRequest) -> None:
        editor = PromoEditor(logger=self.log_queue.put)
        try:
            outputs = editor.generate(req)
            self.log_queue.put(f"Done. Output files: {', '.join(str(p) for p in outputs)}")
        except Exception as exc:  # noqa: BLE001
            self.log_queue.put(f"ERROR: {exc}")

    def _append_log(self, line: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert(tk.END, line + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.after(100, self._drain_log_queue)


if __name__ == "__main__":
    app = AutoEditPromoApp()
    app.mainloop()
