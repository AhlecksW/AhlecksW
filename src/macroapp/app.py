"""Tkinter UI tying recorder, player, matcher and storage together.

Layout:
    +-----------------+-------------------------------------------------+
    |  Macros (list)  |  Name                                           |
    |  [ macro A ]    |  Record:   [Record (F9 stops)]  events: N       |
    |  [ macro B ]    |  Image:    [thumbnail] [Paste][Crop][Clear]     |
    |  ...            |            match mode / threshold               |
    |                 |  Playback: repeat / delay  [Play][Stop]         |
    |  [New][Delete]  |  status…                                        |
    +-----------------+-------------------------------------------------+
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional

from PIL import Image, ImageGrab, ImageTk

from .cropper import ScreenCropper
from .matcher import ImageMatcher
from .player import (
    MATCH_CLICK_IMAGE,
    MATCH_NONE,
    MATCH_RUN_IF_PRESENT,
    MATCH_WAIT_FOR_IMAGE,
    MacroPlayer,
)
from .recorder import MacroRecorder
from .storage import Macro, Storage

MATCH_LABELS = {
    "No image (just replay actions)": MATCH_NONE,
    "Run only if image is on screen": MATCH_RUN_IF_PRESENT,
    "Wait for image, then run": MATCH_WAIT_FOR_IMAGE,
    "Click on the image (ignore recorded clicks)": MATCH_CLICK_IMAGE,
}
LABEL_BY_MODE = {v: k for k, v in MATCH_LABELS.items()}


def data_dir() -> str:
    """Folder for saved macros — next to the .exe when frozen, else project root."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(base, "data")
    os.makedirs(path, exist_ok=True)
    return path


class MacroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AhlecksW Macro Automator")
        self.geometry("840x560")
        self.minsize(760, 520)

        self.storage = Storage(data_dir())
        self.recorder = MacroRecorder()
        self.player = MacroPlayer()
        self.matcher = ImageMatcher()

        self.macros: List[Macro] = self.storage.load()
        self.current: Optional[Macro] = None
        self._current_image: Optional[Image.Image] = None
        self._thumb: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self._refresh_list()
        if self.macros:
            self.listbox.selection_set(0)
            self._on_select()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------------- build
    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        # Left: macro list
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="Macros", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=26, height=22, exportselection=False)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="New", command=self._new_macro).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Delete", command=self._delete_macro).pack(side="left", expand=True, fill="x")

        # Right: details
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)

        # Name
        name_row = ttk.Frame(right)
        name_row.pack(fill="x", pady=(0, 8))
        ttk.Label(name_row, text="Name", width=10).pack(side="left")
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_row, textvariable=self.name_var)
        self.name_entry.pack(side="left", fill="x", expand=True)
        self.name_entry.bind("<FocusOut>", lambda _e: self._apply_name())
        self.name_entry.bind("<Return>", lambda _e: self._apply_name())

        # Record
        rec = ttk.LabelFrame(right, text="Record", padding=8)
        rec.pack(fill="x", pady=4)
        self.record_btn = ttk.Button(rec, text="● Record", command=self._toggle_record)
        self.record_btn.pack(side="left")
        self.events_label = ttk.Label(rec, text="0 events")
        self.events_label.pack(side="left", padx=10)
        self.capture_moves = tk.BooleanVar(value=False)
        ttk.Checkbutton(rec, text="Capture mouse movement", variable=self.capture_moves).pack(side="left", padx=10)
        ttk.Label(rec, text="(F9 stops recording)").pack(side="right")

        # Image
        img = ttk.LabelFrame(right, text="Image recognition", padding=8)
        img.pack(fill="x", pady=4)
        self.thumb_label = ttk.Label(img, text="No image", relief="sunken", width=22, anchor="center")
        self.thumb_label.pack(side="left", padx=(0, 8))
        img_ctrl = ttk.Frame(img)
        img_ctrl.pack(side="left", fill="both", expand=True)
        row1 = ttk.Frame(img_ctrl)
        row1.pack(fill="x")
        ttk.Button(row1, text="Crop from screen", command=self._crop_image).pack(side="left", padx=2)
        ttk.Button(row1, text="Paste image", command=self._paste_image).pack(side="left", padx=2)
        ttk.Button(row1, text="Clear", command=self._clear_image).pack(side="left", padx=2)
        ttk.Button(row1, text="Test match", command=self._test_match).pack(side="left", padx=2)

        row2 = ttk.Frame(img_ctrl)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="Mode").pack(side="left")
        self.mode_var = tk.StringVar(value=list(MATCH_LABELS.keys())[0])
        self.mode_combo = ttk.Combobox(
            row2, textvariable=self.mode_var, values=list(MATCH_LABELS.keys()),
            state="readonly", width=38,
        )
        self.mode_combo.pack(side="left", padx=4)

        row3 = ttk.Frame(img_ctrl)
        row3.pack(fill="x", pady=(6, 0))
        ttk.Label(row3, text="Match %").pack(side="left")
        self.threshold_var = tk.IntVar(value=80)
        self.threshold_label = ttk.Label(row3, text="80%", width=5)
        self.threshold_scale = ttk.Scale(
            row3, from_=50, to=100, orient="horizontal",
            command=lambda v: self.threshold_label.config(text=f"{int(float(v))}%"),
        )
        self.threshold_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.threshold_label.pack(side="left")
        self.threshold_scale.set(80)

        # Playback
        play = ttk.LabelFrame(right, text="Playback", padding=8)
        play.pack(fill="x", pady=4)
        ttk.Label(play, text="Repeat (0 = forever)").pack(side="left")
        self.repeat_var = tk.StringVar(value="1")
        ttk.Spinbox(play, from_=0, to=999999, width=8, textvariable=self.repeat_var).pack(side="left", padx=4)
        ttk.Label(play, text="Delay (s)").pack(side="left", padx=(10, 0))
        self.delay_var = tk.StringVar(value="0.5")
        ttk.Spinbox(play, from_=0, to=60, increment=0.1, width=6, textvariable=self.delay_var).pack(side="left", padx=4)
        self.play_btn = ttk.Button(play, text="▶ Play", command=self._play)
        self.play_btn.pack(side="left", padx=(12, 2))
        self.stop_btn = ttk.Button(play, text="■ Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=2)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=4)
        status.pack(fill="x", side="bottom")

    # --------------------------------------------------------- list handling
    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for m in self.macros:
            tag = "🖼" if m.has_image else "  "
            self.listbox.insert("end", f"{tag} {m.name}  ({len(m.events)})")

    def _selected_index(self) -> Optional[int]:
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _on_select(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._commit_current()  # save edits to whatever was selected before
        self.current = self.macros[idx]
        self._load_into_form(self.current)

    def _load_into_form(self, m: Macro):
        self.name_var.set(m.name)
        self.events_label.config(text=f"{len(m.events)} events")
        self.repeat_var.set(str(m.repeat))
        self.delay_var.set(str(m.loop_delay))
        self.mode_var.set(LABEL_BY_MODE.get(m.match_mode, list(MATCH_LABELS.keys())[0]))
        self.threshold_scale.set(int(m.threshold * 100))
        self.threshold_label.config(text=f"{int(m.threshold * 100)}%")
        self._current_image = self.storage.load_image(m)
        self._show_thumb(self._current_image)

    def _show_thumb(self, image: Optional[Image.Image]):
        if image is None:
            self._thumb = None
            self.thumb_label.config(image="", text="No image")
            return
        preview = image.copy()
        preview.thumbnail((140, 90))
        self._thumb = ImageTk.PhotoImage(preview)
        self.thumb_label.config(image=self._thumb, text="")

    # --------------------------------------------------------- commit / edit
    def _apply_name(self):
        if self.current:
            self.current.name = self.name_var.get().strip() or "Untitled"
            self._refresh_list_preserve()

    def _refresh_list_preserve(self):
        idx = self._selected_index()
        self._refresh_list()
        if idx is not None and idx < len(self.macros):
            self.listbox.selection_set(idx)

    def _commit_current(self):
        """Pull the form values back into the current macro object."""
        if not self.current:
            return
        m = self.current
        m.name = self.name_var.get().strip() or "Untitled"
        m.match_mode = MATCH_LABELS.get(self.mode_var.get(), MATCH_NONE)
        m.threshold = self.threshold_scale.get() / 100.0
        try:
            m.repeat = max(0, int(float(self.repeat_var.get())))
        except ValueError:
            m.repeat = 1
        try:
            m.loop_delay = max(0.0, float(self.delay_var.get()))
        except ValueError:
            m.loop_delay = 0.5

    def _new_macro(self):
        self._commit_current()
        m = Macro(name=f"Macro {len(self.macros) + 1}")
        self.macros.append(m)
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")
        self._on_select()
        self._save()

    def _delete_macro(self):
        idx = self._selected_index()
        if idx is None:
            return
        m = self.macros[idx]
        if not messagebox.askyesno("Delete", f"Delete macro '{m.name}'?"):
            return
        self.storage.delete_image(m)
        del self.macros[idx]
        self.current = None
        self._refresh_list()
        self._save()
        if self.macros:
            self.listbox.selection_set(min(idx, len(self.macros) - 1))
            self._on_select()

    # ------------------------------------------------------------- recording
    def _toggle_record(self):
        if self.recorder.recording:
            self._finish_record()
        else:
            self._start_record()

    def _start_record(self):
        if not self.current:
            self._new_macro()
        self.recorder.capture_moves = self.capture_moves.get()
        self.record_btn.config(text="■ Stop recording")
        self._set_status("Recording… press F9 to stop")
        self.recorder.start(on_stop=lambda: self.after(0, self._finish_record))

    def _finish_record(self):
        if not self.recorder.recording and not self.recorder.events:
            return
        events = self.recorder.stop()
        if self.current:
            self.current.events = events
            self.events_label.config(text=f"{len(events)} events")
            self._refresh_list_preserve()
            self._save()
        self.record_btn.config(text="● Record")
        self._set_status(f"Recorded {len(events)} events")

    # ---------------------------------------------------------------- images
    def _crop_image(self):
        if not self.current:
            self._new_macro()
        self.iconify()
        self.after(250, lambda: ScreenCropper(self, self._on_cropped))

    def _on_cropped(self, image: Optional[Image.Image]):
        self.deiconify()
        if image is None:
            self._set_status("Crop cancelled")
            return
        self._set_image(image)

    def _paste_image(self):
        if not self.current:
            self._new_macro()
        try:
            grabbed = ImageGrab.grabclipboard()
        except Exception as exc:  # pragma: no cover - platform specific
            messagebox.showerror("Paste failed", str(exc))
            return
        if isinstance(grabbed, Image.Image):
            self._set_image(grabbed)
        elif isinstance(grabbed, list) and grabbed:
            try:
                self._set_image(Image.open(grabbed[0]))
            except Exception as exc:
                messagebox.showerror("Paste failed", str(exc))
        else:
            messagebox.showinfo("Paste", "No image found on the clipboard.")

    def _set_image(self, image: Image.Image):
        self._current_image = image.convert("RGB")
        self.storage.save_image(self.current, self._current_image)
        self._show_thumb(self._current_image)
        self._refresh_list_preserve()
        self._save()
        self._set_status("Image saved to macro")

    def _clear_image(self):
        if self.current:
            self.storage.delete_image(self.current)
            self._current_image = None
            self._show_thumb(None)
            self._refresh_list_preserve()
            self._save()

    def _test_match(self):
        if self._current_image is None:
            messagebox.showinfo("Test match", "Attach an image first.")
            return
        threshold = self.threshold_scale.get() / 100.0
        self._set_status("Testing match in 1s…")
        self.after(1000, lambda: self._do_test_match(threshold))

    def _do_test_match(self, threshold: float):
        score, center = self.matcher.score(self._current_image)
        verdict = "MATCH" if score >= threshold else "no match"
        self._set_status(
            f"Best similarity {score * 100:.1f}% at {center} — {verdict} (need {threshold * 100:.0f}%)"
        )

    # ------------------------------------------------------------- playback
    def _play(self):
        if not self.current or not self.current.events:
            if self.mode_var.get() != "Click on the image (ignore recorded clicks)":
                messagebox.showinfo("Play", "Record some actions first.")
                return
        self._commit_current()
        self._save()
        m = self.current

        self.play_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.player.play(
            events=m.events,
            repeat=m.repeat,
            loop_delay=m.loop_delay,
            match_mode=m.match_mode,
            template=self._current_image,
            threshold=m.threshold,
            wait_timeout=m.wait_timeout,
            on_status=lambda s: self.after(0, self._set_status, s),
            on_finished=lambda: self.after(0, self._on_play_finished),
        )

    def _stop(self):
        self.player.stop()

    def _on_play_finished(self):
        self.play_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ---------------------------------------------------------------- common
    def _set_status(self, text: str):
        self.status_var.set(text)

    def _save(self):
        self._commit_current()
        self.storage.save(self.macros)

    def _on_close(self):
        if self.recorder.recording:
            self.recorder.stop()
        self.player.stop()
        self._save()
        self.destroy()


def main():
    app = MacroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
