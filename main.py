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
        self.title("AutoEditPromo")
        self.geometry("760x560")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.project_dir = tk.StringVar(value=str(Path.cwd()))
        self.title_text = tk.StringVar(value="My Promo")
        self.subtitle_text = tk.StringVar(value="Fast. Clean. Automatic.")
        self.messages_text = tk.StringVar(value="Limited offer|Visit our site|Follow for more")
        self.clip_count = tk.IntVar(value=6)
        self.target_duration = tk.IntVar(value=24)
        self.bpm = tk.IntVar(value=120)

        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(frm, text="Project folder").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.project_dir, width=70).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Browse", command=self._pick_project_dir).grid(row=row, column=2, sticky="ew")

        row += 1
        ttk.Label(frm, text="Title").grid(row=row, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(frm, textvariable=self.title_text).grid(row=row, column=1, columnspan=2, sticky="ew", pady=(10, 0))

        row += 1
        ttk.Label(frm, text="Subtitle").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=self.subtitle_text).grid(row=row, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        row += 1
        ttk.Label(frm, text="Promo messages (| separated)").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frm, textvariable=self.messages_text).grid(row=row, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        row += 1
        ttk.Label(frm, text="Clip count").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frm, from_=2, to=40, textvariable=self.clip_count, width=8).grid(row=row, column=1, sticky="w", pady=(8, 0))

        row += 1
        ttk.Label(frm, text="Target duration (sec)").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frm, from_=5, to=300, textvariable=self.target_duration, width=8).grid(row=row, column=1, sticky="w", pady=(8, 0))

        row += 1
        ttk.Label(frm, text="Music BPM (fallback)").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frm, from_=60, to=220, textvariable=self.bpm, width=8).grid(row=row, column=1, sticky="w", pady=(8, 0))

        row += 1
        ttk.Button(frm, text="Generate Promo", command=self._start_generation).grid(row=row, column=0, columnspan=3, sticky="ew", pady=16)

        row += 1
        self.log_widget = tk.Text(frm, height=18, wrap="word", state="disabled")
        self.log_widget.grid(row=row, column=0, columnspan=3, sticky="nsew")

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(row, weight=1)

    def _pick_project_dir(self) -> None:
        picked = filedialog.askdirectory(initialdir=self.project_dir.get())
        if picked:
            self.project_dir.set(picked)

    def _start_generation(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("AutoEditPromo", "Generation already running.")
            return

        base = Path(self.project_dir.get()).expanduser().resolve()
        req = PromoRequest(
            base_dir=base,
            title=self.title_text.get().strip(),
            subtitle=self.subtitle_text.get().strip(),
            messages=[m.strip() for m in self.messages_text.get().split("|") if m.strip()],
            clip_count=self.clip_count.get(),
            target_duration=self.target_duration.get(),
            fallback_bpm=self.bpm.get(),
        )

        self._append_log(f"Starting generation in: {base}")
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
