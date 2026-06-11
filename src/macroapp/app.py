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
from .editor import EventEditor
from .hotkeys import HotkeyCapture, HotkeyManager
from .matcher import ImageMatcher
from .player import (
    MATCH_CLICK_IMAGE,
    MATCH_NONE,
    MATCH_RUN_IF_PRESENT,
    MATCH_WAIT_FOR_IMAGE,
    MacroPlayer,
)
from .recorder import MacroRecorder
from .share import decode_macro, encode_macro
from .storage import Macro, Routine, Storage, new_step
from .theme import FROST_BG, apply_theme, style_listbox, style_text

ROUTINE_MODES = {"Sequence (in order)": "sequence", "Reactive (watch & react)": "reactive"}
MODE_LABELS = {v: k for k, v in ROUTINE_MODES.items()}
AFTER_LABELS = {"Run once, then next": "once", "Repeat until next image": "repeat_until_next"}
AFTER_BY_VALUE = {v: k for k, v in AFTER_LABELS.items()}

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
        self.title("Cryo Chamber")
        self.geometry("840x560")
        self.minsize(760, 520)
        apply_theme(self)

        self.storage = Storage(data_dir())
        self.recorder = MacroRecorder()
        self.player = MacroPlayer()
        self.matcher = ImageMatcher()
        self.hotkeys = HotkeyManager()

        self.macros: List[Macro] = self.storage.load()
        self.current: Optional[Macro] = None
        self._current_image: Optional[Image.Image] = None
        self._thumb: Optional[ImageTk.PhotoImage] = None

        # Routines (image-triggered chains of macros)
        self.routines: List[Routine] = self.storage.load_routines()
        self.current_routine: Optional[Routine] = None
        self.current_step: Optional[dict] = None
        self._step_thumb: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self._refresh_list()
        if self.macros:
            self.listbox.selection_set(0)
            self._on_select()
        self._refresh_routine_list()
        if self.routines:
            self.routine_listbox.selection_set(0)
            self._on_routine_select()
        self._refresh_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------------- build
    def _build_ui(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        macros_tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(macros_tab, text="Macros")
        routines_tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(routines_tab, text="Routines")

        root = macros_tab

        # Left: macro list
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="Macros", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=26, height=22, exportselection=False)
        style_listbox(self.listbox)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="New", command=self._new_macro).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Delete", command=self._delete_macro).pack(side="left", expand=True, fill="x")
        share = ttk.Frame(left)
        share.pack(fill="x")
        ttk.Button(share, text="Export", command=self._export_macro).pack(side="left", expand=True, fill="x")
        ttk.Button(share, text="Import", command=self._import_macro).pack(side="left", expand=True, fill="x")

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
        ttk.Button(rec, text="Edit steps…", command=self._edit_steps).pack(side="left", padx=4)
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

        # Run options: global hotkey + playback speed
        opts = ttk.LabelFrame(right, text="Run options", padding=8)
        opts.pack(fill="x", pady=4)
        ttk.Label(opts, text="Start hotkey").pack(side="left")
        self.hotkey_var = tk.StringVar(value="none")
        ttk.Label(opts, textvariable=self.hotkey_var, width=20, relief="sunken", anchor="center").pack(side="left", padx=4)
        ttk.Button(opts, text="Set", command=self._set_hotkey).pack(side="left", padx=2)
        ttk.Button(opts, text="Clear", command=self._clear_hotkey).pack(side="left", padx=2)
        ttk.Label(opts, text="Speed ×").pack(side="left", padx=(14, 2))
        self.speed_var = tk.StringVar(value="1.0")
        ttk.Spinbox(opts, from_=0.1, to=10, increment=0.1, width=6, textvariable=self.speed_var).pack(side="left")

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

        self._build_routines_tab(routines_tab)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=4)
        status.pack(fill="x", side="bottom")

    # --------------------------------------------------------- routines tab
    def _build_routines_tab(self, root):
        # Left: routine list
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="Routines", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.routine_listbox = tk.Listbox(left, width=26, height=18, exportselection=False)
        style_listbox(self.routine_listbox)
        self.routine_listbox.pack(fill="y", expand=True)
        self.routine_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_routine_select())
        rb = ttk.Frame(left)
        rb.pack(fill="x", pady=4)
        ttk.Button(rb, text="New", command=self._new_routine).pack(side="left", expand=True, fill="x")
        ttk.Button(rb, text="Delete", command=self._delete_routine).pack(side="left", expand=True, fill="x")
        rp = ttk.Frame(left)
        rp.pack(fill="x")
        self.routine_play_btn = ttk.Button(rp, text="▶ Play routine", command=self._play_routine)
        self.routine_play_btn.pack(side="left", expand=True, fill="x")
        self.routine_stop_btn = ttk.Button(rp, text="■ Stop", command=self._stop, state="disabled")
        self.routine_stop_btn.pack(side="left", expand=True, fill="x")

        # Right: routine details
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)

        name_row = ttk.Frame(right)
        name_row.pack(fill="x", pady=(0, 6))
        ttk.Label(name_row, text="Name", width=8).pack(side="left")
        self.routine_name_var = tk.StringVar()
        e = ttk.Entry(name_row, textvariable=self.routine_name_var)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<FocusOut>", lambda _e: self._routine_apply_name())
        e.bind("<Return>", lambda _e: self._routine_apply_name())

        cfg = ttk.Frame(right)
        cfg.pack(fill="x", pady=2)
        ttk.Label(cfg, text="Mode").pack(side="left")
        self.routine_mode_var = tk.StringVar(value=list(ROUTINE_MODES.keys())[0])
        ttk.Combobox(cfg, textvariable=self.routine_mode_var, values=list(ROUTINE_MODES.keys()),
                     state="readonly", width=22).pack(side="left", padx=4)
        ttk.Label(cfg, text="Repeat (0=∞)").pack(side="left", padx=(10, 0))
        self.routine_repeat_var = tk.StringVar(value="0")
        ttk.Spinbox(cfg, from_=0, to=999999, width=7, textvariable=self.routine_repeat_var).pack(side="left", padx=4)
        ttk.Label(cfg, text="Scan (s)").pack(side="left")
        self.routine_scan_var = tk.StringVar(value="0.4")
        ttk.Spinbox(cfg, from_=0.05, to=10, increment=0.05, width=5, textvariable=self.routine_scan_var).pack(side="left", padx=4)

        hk = ttk.Frame(right)
        hk.pack(fill="x", pady=2)
        ttk.Label(hk, text="Start hotkey").pack(side="left")
        self.routine_hotkey_var = tk.StringVar(value="none")
        ttk.Label(hk, textvariable=self.routine_hotkey_var, width=18, relief="sunken", anchor="center").pack(side="left", padx=4)
        ttk.Button(hk, text="Set", command=self._set_routine_hotkey).pack(side="left", padx=2)
        ttk.Button(hk, text="Clear", command=self._clear_routine_hotkey).pack(side="left", padx=2)

        # Steps table
        steps_frame = ttk.LabelFrame(right, text="Steps (image → macro, top to bottom)", padding=6)
        steps_frame.pack(fill="both", expand=True, pady=4)
        cols = ("num", "img", "macro", "after")
        self.steps_tree = ttk.Treeview(steps_frame, columns=cols, show="headings", height=6, selectmode="browse")
        for c, txt, w in [("num", "#", 34), ("img", "Image", 56), ("macro", "Macro", 160), ("after", "After", 150)]:
            self.steps_tree.heading(c, text=txt)
            self.steps_tree.column(c, width=w, anchor="w" if c in ("macro", "after") else "center")
        self.steps_tree.pack(side="left", fill="both", expand=True)
        self.steps_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_step_select())
        sbtn = ttk.Frame(steps_frame)
        sbtn.pack(side="left", fill="y", padx=4)
        ttk.Button(sbtn, text="Add", width=8, command=self._add_step).pack(pady=1)
        ttk.Button(sbtn, text="Remove", width=8, command=self._remove_step).pack(pady=1)
        ttk.Button(sbtn, text="↑", width=8, command=lambda: self._move_step(-1)).pack(pady=1)
        ttk.Button(sbtn, text="↓", width=8, command=lambda: self._move_step(1)).pack(pady=1)

        # Selected-step editor
        se = ttk.LabelFrame(right, text="Selected step", padding=6)
        se.pack(fill="x", pady=4)
        r1 = ttk.Frame(se)
        r1.pack(fill="x")
        self.step_thumb = ttk.Label(r1, text="No image", relief="sunken", width=16, anchor="center")
        self.step_thumb.pack(side="left", padx=(0, 8))
        sc = ttk.Frame(r1)
        sc.pack(side="left", fill="x", expand=True)
        b = ttk.Frame(sc)
        b.pack(fill="x")
        ttk.Button(b, text="Crop", command=self._step_crop_image).pack(side="left", padx=1)
        ttk.Button(b, text="Paste", command=self._step_paste_image).pack(side="left", padx=1)
        ttk.Button(b, text="Clear", command=self._step_clear_image).pack(side="left", padx=1)
        ttk.Button(b, text="Test", command=self._step_test_match).pack(side="left", padx=1)
        m = ttk.Frame(sc)
        m.pack(fill="x", pady=(4, 0))
        ttk.Label(m, text="Play macro").pack(side="left")
        self.step_macro_var = tk.StringVar()
        self.step_macro_combo = ttk.Combobox(m, textvariable=self.step_macro_var, state="readonly", width=20)
        self.step_macro_combo.pack(side="left", padx=4)
        self.step_macro_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_step_fields())
        a = ttk.Frame(sc)
        a.pack(fill="x", pady=(4, 0))
        ttk.Label(a, text="After").pack(side="left")
        self.step_after_var = tk.StringVar(value=list(AFTER_LABELS.keys())[0])
        ac = ttk.Combobox(a, textvariable=self.step_after_var, values=list(AFTER_LABELS.keys()),
                          state="readonly", width=22)
        ac.pack(side="left", padx=4)
        ac.bind("<<ComboboxSelected>>", lambda _e: self._apply_step_fields())
        ttk.Label(a, text="Match %").pack(side="left", padx=(10, 0))
        self.step_thresh_var = tk.IntVar(value=80)
        ttk.Spinbox(a, from_=50, to=100, width=5, textvariable=self.step_thresh_var,
                    command=self._apply_step_fields).pack(side="left", padx=4)

    # --------------------------------------------------------- list handling
    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for m in self.macros:
            tag = "🖼" if m.has_image else "  "
            hk = f"  [{m.hotkey}]" if m.hotkey else ""
            self.listbox.insert("end", f"{tag} {m.name}  ({len(m.events)}){hk}")

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
        self.hotkey_var.set(m.hotkey or "none")
        self.speed_var.set(str(m.speed))
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
        try:
            m.speed = max(0.1, float(self.speed_var.get()))
        except ValueError:
            m.speed = 1.0

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
        self._refresh_hotkeys()
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
        self.hotkeys.pause()  # don't trigger macros from keys being recorded
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
        self.hotkeys.resume()
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

        self._set_running(True)
        self.player.play(
            events=m.events,
            repeat=m.repeat,
            loop_delay=m.loop_delay,
            match_mode=m.match_mode,
            template=self._current_image,
            threshold=m.threshold,
            wait_timeout=m.wait_timeout,
            speed=m.speed,
            on_status=lambda s: self.after(0, self._set_status, s),
            on_finished=lambda: self.after(0, self._on_play_finished),
        )

    def _stop(self):
        self.player.stop()

    def _set_running(self, running: bool):
        pstate = "disabled" if running else "normal"
        sstate = "normal" if running else "disabled"
        for w in (self.play_btn, self.routine_play_btn):
            w.config(state=pstate)
        for w in (self.stop_btn, self.routine_stop_btn):
            w.config(state=sstate)

    def _on_play_finished(self):
        self._set_running(False)

    # ----------------------------------------------------------- step editor
    def _edit_steps(self):
        if not self.current:
            return
        if self.recorder.recording:
            messagebox.showinfo("Edit steps", "Stop recording first.")
            return

        def on_save(events):
            self.current.events = events
            self.events_label.config(text=f"{len(events)} events")
            self._refresh_list_preserve()
            self._save()
            self._set_status(f"Saved {len(events)} steps")

        EventEditor(self, self.current.events, on_save)

    # --------------------------------------------------------- global hotkeys
    def _set_hotkey(self):
        if not self.current:
            self._new_macro()
        self.hotkeys.pause()  # don't let the manager swallow keys while capturing

        def on_done(combo):
            self.hotkeys.resume()
            if combo is None:
                return
            owner = self._hotkey_owner(combo, exclude_macro=self.current)
            if owner:
                messagebox.showwarning("Hotkey in use", f"{combo} is already used by '{owner}'.")
                return
            self.current.hotkey = combo
            self.hotkey_var.set(combo)
            self._refresh_list_preserve()
            self._save()
            self._refresh_hotkeys()
            self._set_status(f"Hotkey set to {combo}")

        HotkeyCapture(self, on_done)

    def _clear_hotkey(self):
        if self.current:
            self.current.hotkey = ""
            self.hotkey_var.set("none")
            self._refresh_list_preserve()
            self._save()
            self._refresh_hotkeys()

    def _refresh_hotkeys(self):
        mapping = {}
        for m in self.macros:
            if m.hotkey:
                mapping[m.hotkey] = self._make_hotkey_callback(m.id)
        for r in self.routines:
            if r.hotkey:
                mapping[r.hotkey] = self._make_routine_hotkey_callback(r.id)
        self.hotkeys.set_bindings(mapping)

    def _hotkey_owner(self, combo: str, exclude_macro=None, exclude_routine=None) -> Optional[str]:
        """Return the name of whatever already uses ``combo``, else None."""
        for m in self.macros:
            if m is not exclude_macro and m.hotkey == combo:
                return m.name
        for r in self.routines:
            if r is not exclude_routine and r.hotkey == combo:
                return f"routine '{r.name}'"
        return None

    def _make_hotkey_callback(self, macro_id: str):
        # Hotkeys fire on the listener thread; bounce to the Tk thread.
        return lambda: self.after(0, self._toggle_macro_by_id, macro_id)

    def _toggle_macro_by_id(self, macro_id: str):
        # Same hotkey starts the macro, or stops it if it's already running.
        if self.player.running:
            self.player.stop()
            return
        idx = next((i for i, m in enumerate(self.macros) if m.id == macro_id), None)
        if idx is None:
            return
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self._on_select()
        self._play()

    # --------------------------------------------------------- export/import
    def _export_macro(self):
        if not self.current:
            messagebox.showinfo("Export", "Select a macro to export.")
            return
        self._commit_current()
        code = encode_macro(self.current, self._current_image)
        self.clipboard_clear()
        self.clipboard_append(code)
        self._show_code_dialog(
            "Export macro",
            f"Share code for '{self.current.name}' (copied to clipboard):",
            code, readonly=True,
        )
        self._set_status("Share code copied to clipboard")

    def _import_macro(self):
        self._show_code_dialog(
            "Import macro",
            "Paste a macro share code below, then click Import:",
            "", readonly=False, on_import=self._do_import,
        )

    def _do_import(self, code: str):
        try:
            macro, image = decode_macro(code)
        except ValueError as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        self._commit_current()
        self.macros.append(macro)
        if image is not None:
            self.storage.save_image(macro, image)
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")
        self._on_select()
        self._save()
        self._set_status(f"Imported macro '{macro.name}'")

    def _show_code_dialog(self, title, label, text, readonly, on_import=None):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("520x260")
        dlg.transient(self)
        ttk.Label(dlg, text=label, padding=8, wraplength=500).pack(anchor="w")
        dlg.configure(bg=FROST_BG)
        box = tk.Text(dlg, height=8, wrap="char")
        style_text(box)
        box.pack(fill="both", expand=True, padx=8)
        box.insert("1.0", text)
        if readonly:
            box.config(state="disabled")
        bar = ttk.Frame(dlg, padding=8)
        bar.pack(fill="x")
        if on_import:
            def do():
                on_import(box.get("1.0", "end"))
                dlg.destroy()
            ttk.Button(bar, text="Paste from clipboard", command=lambda: self._paste_into(box)).pack(side="left")
            ttk.Button(bar, text="Import", command=do).pack(side="right")
        else:
            ttk.Button(bar, text="Copy again", command=lambda: self._copy_text(text)).pack(side="left")
        ttk.Button(bar, text="Close", command=dlg.destroy).pack(side="right", padx=4)

    def _paste_into(self, box):
        try:
            box.delete("1.0", "end")
            box.insert("1.0", self.clipboard_get())
        except Exception:
            pass

    def _copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("Copied to clipboard")

    # ========================================================== ROUTINES =====
    def _macro_label(self, m: Macro) -> str:
        return f"{m.name}  ·{m.id[:4]}"

    def _update_step_macro_combo(self):
        self._macro_by_label = {self._macro_label(m): m.id for m in self.macros}
        self.step_macro_combo["values"] = list(self._macro_by_label.keys())

    def _label_for_macro_id(self, macro_id: str) -> str:
        for m in self.macros:
            if m.id == macro_id:
                return self._macro_label(m)
        return ""

    # ---------------------------------------------------------- routine list
    def _refresh_routine_list(self):
        self.routine_listbox.delete(0, "end")
        for r in self.routines:
            hk = f"  [{r.hotkey}]" if r.hotkey else ""
            self.routine_listbox.insert("end", f"{r.name}  ({len(r.steps)} steps){hk}")

    def _selected_routine_index(self) -> Optional[int]:
        sel = self.routine_listbox.curselection()
        return sel[0] if sel else None

    def _on_routine_select(self):
        idx = self._selected_routine_index()
        if idx is None:
            return
        self._commit_current_routine()
        self.current_routine = self.routines[idx]
        self.current_step = None
        self._load_routine_into_form(self.current_routine)

    def _load_routine_into_form(self, r: Routine):
        self.routine_name_var.set(r.name)
        self.routine_mode_var.set(MODE_LABELS.get(r.mode, list(ROUTINE_MODES.keys())[0]))
        self.routine_repeat_var.set(str(r.repeat))
        self.routine_scan_var.set(str(r.scan_interval))
        self.routine_hotkey_var.set(r.hotkey or "none")
        self._update_step_macro_combo()
        self._reload_steps_tree()
        self._show_step_thumb(None)

    def _commit_current_routine(self):
        r = self.current_routine
        if not r:
            return
        r.name = self.routine_name_var.get().strip() or "Untitled"
        r.mode = ROUTINE_MODES.get(self.routine_mode_var.get(), "sequence")
        try:
            r.repeat = max(0, int(float(self.routine_repeat_var.get())))
        except ValueError:
            r.repeat = 0
        try:
            r.scan_interval = max(0.05, float(self.routine_scan_var.get()))
        except ValueError:
            r.scan_interval = 0.4

    def _routine_apply_name(self):
        if self.current_routine:
            self.current_routine.name = self.routine_name_var.get().strip() or "Untitled"
            self._refresh_routine_list_preserve()

    def _refresh_routine_list_preserve(self):
        idx = self._selected_routine_index()
        self._refresh_routine_list()
        if idx is not None and idx < len(self.routines):
            self.routine_listbox.selection_set(idx)

    def _new_routine(self):
        self._commit_current_routine()
        r = Routine(name=f"Routine {len(self.routines) + 1}")
        self.routines.append(r)
        self._refresh_routine_list()
        self.routine_listbox.selection_clear(0, "end")
        self.routine_listbox.selection_set("end")
        self._on_routine_select()
        self._save_routines()

    def _delete_routine(self):
        idx = self._selected_routine_index()
        if idx is None:
            return
        r = self.routines[idx]
        if not messagebox.askyesno("Delete", f"Delete routine '{r.name}'?"):
            return
        for step in r.steps:
            self.storage.delete_step_image(step)
        del self.routines[idx]
        self.current_routine = None
        self.current_step = None
        self._refresh_routine_list()
        self._save_routines()
        self._refresh_hotkeys()
        if self.routines:
            self.routine_listbox.selection_set(min(idx, len(self.routines) - 1))
            self._on_routine_select()

    # ---------------------------------------------------------- steps table
    def _reload_steps_tree(self):
        self.steps_tree.delete(*self.steps_tree.get_children())
        if not self.current_routine:
            return
        for i, step in enumerate(self.current_routine.steps):
            macro_name = self._label_for_macro_id(step.get("macro_id", "")) or "— none —"
            img = "✓" if step.get("has_image") else "✗"
            after = AFTER_BY_VALUE.get(step.get("after", "once"), "once")
            self.steps_tree.insert("", "end", iid=step["id"],
                                   values=(i + 1, img, macro_name, after))

    def _add_step(self):
        if not self.current_routine:
            self._new_routine()
        step = new_step()
        self.current_routine.steps.append(step)
        self._reload_steps_tree()
        self.steps_tree.selection_set(step["id"])
        self._on_step_select()
        self._save_routines()
        self._refresh_routine_list_preserve()

    def _remove_step(self):
        sel = self.steps_tree.selection()
        if not sel or not self.current_routine:
            return
        sid = sel[0]
        step = next((s for s in self.current_routine.steps if s["id"] == sid), None)
        if step:
            self.storage.delete_step_image(step)
            self.current_routine.steps.remove(step)
        self.current_step = None
        self._reload_steps_tree()
        self._show_step_thumb(None)
        self._save_routines()
        self._refresh_routine_list_preserve()

    def _move_step(self, delta: int):
        sel = self.steps_tree.selection()
        if not sel or not self.current_routine:
            return
        steps = self.current_routine.steps
        idx = next((i for i, s in enumerate(steps) if s["id"] == sel[0]), None)
        if idx is None:
            return
        new = idx + delta
        if not (0 <= new < len(steps)):
            return
        steps[idx], steps[new] = steps[new], steps[idx]
        self._reload_steps_tree()
        self.steps_tree.selection_set(sel[0])
        self._save_routines()

    def _selected_step(self) -> Optional[dict]:
        sel = self.steps_tree.selection()
        if not sel or not self.current_routine:
            return None
        return next((s for s in self.current_routine.steps if s["id"] == sel[0]), None)

    def _on_step_select(self):
        step = self._selected_step()
        self.current_step = step
        if not step:
            return
        self.step_macro_var.set(self._label_for_macro_id(step.get("macro_id", "")))
        self.step_after_var.set(AFTER_BY_VALUE.get(step.get("after", "once"), list(AFTER_LABELS.keys())[0]))
        self.step_thresh_var.set(int(step.get("threshold", 0.8) * 100))
        self._show_step_thumb(self.storage.load_step_image(step))

    def _apply_step_fields(self):
        step = self.current_step
        if not step:
            return
        label = self.step_macro_var.get()
        step["macro_id"] = getattr(self, "_macro_by_label", {}).get(label, step.get("macro_id", ""))
        step["after"] = AFTER_LABELS.get(self.step_after_var.get(), "once")
        try:
            step["threshold"] = max(0.5, min(1.0, int(self.step_thresh_var.get()) / 100.0))
        except (ValueError, tk.TclError):
            step["threshold"] = 0.8
        self._reload_steps_tree()
        self.steps_tree.selection_set(step["id"])
        self._save_routines()

    # --------------------------------------------------------- step images
    def _show_step_thumb(self, image: Optional[Image.Image]):
        if image is None:
            self._step_thumb = None
            self.step_thumb.config(image="", text="No image")
            return
        preview = image.copy()
        preview.thumbnail((110, 70))
        self._step_thumb = ImageTk.PhotoImage(preview)
        self.step_thumb.config(image=self._step_thumb, text="")

    def _step_crop_image(self):
        if not self.current_step:
            messagebox.showinfo("Step image", "Add and select a step first.")
            return
        self.iconify()
        self.after(250, lambda: ScreenCropper(self, self._on_step_cropped))

    def _on_step_cropped(self, image: Optional[Image.Image]):
        self.deiconify()
        if image is None:
            self._set_status("Crop cancelled")
            return
        self._set_step_image(image)

    def _step_paste_image(self):
        if not self.current_step:
            messagebox.showinfo("Step image", "Add and select a step first.")
            return
        try:
            grabbed = ImageGrab.grabclipboard()
        except Exception as exc:  # pragma: no cover - platform specific
            messagebox.showerror("Paste failed", str(exc))
            return
        if isinstance(grabbed, Image.Image):
            self._set_step_image(grabbed)
        elif isinstance(grabbed, list) and grabbed:
            try:
                self._set_step_image(Image.open(grabbed[0]))
            except Exception as exc:
                messagebox.showerror("Paste failed", str(exc))
        else:
            messagebox.showinfo("Paste", "No image found on the clipboard.")

    def _set_step_image(self, image: Image.Image):
        img = image.convert("RGB")
        self.storage.save_step_image(self.current_step, img)
        self._show_step_thumb(img)
        self._reload_steps_tree()
        self.steps_tree.selection_set(self.current_step["id"])
        self._save_routines()
        self._set_status("Step image saved")

    def _step_clear_image(self):
        if self.current_step:
            self.storage.delete_step_image(self.current_step)
            self._show_step_thumb(None)
            self._reload_steps_tree()
            self.steps_tree.selection_set(self.current_step["id"])
            self._save_routines()

    def _step_test_match(self):
        if not self.current_step:
            return
        image = self.storage.load_step_image(self.current_step)
        if image is None:
            messagebox.showinfo("Test match", "Attach an image to this step first.")
            return
        threshold = self.current_step.get("threshold", 0.8)
        self._set_status("Testing step match in 1s…")
        self.after(1000, lambda: self._do_step_test(image, threshold))

    def _do_step_test(self, image, threshold):
        score, center = self.matcher.score(image)
        verdict = "MATCH" if score >= threshold else "no match"
        self._set_status(f"Step similarity {score * 100:.1f}% at {center} — {verdict} (need {threshold * 100:.0f}%)")

    # ------------------------------------------------------- routine playback
    def _play_routine(self):
        if not self.current_routine:
            messagebox.showinfo("Play routine", "Select a routine first.")
            return
        self._commit_current_routine()
        self._save_routines()
        r = self.current_routine

        macro_events = {m.id: m.events for m in self.macros}
        built = []
        skipped = 0
        for i, step in enumerate(r.steps):
            template = self.storage.load_step_image(step)
            events = macro_events.get(step.get("macro_id", ""))
            if template is None or events is None:
                skipped += 1
                continue
            built.append({
                "name": self._label_for_macro_id(step.get("macro_id", "")) or f"step {i + 1}",
                "template": template,
                "threshold": step.get("threshold", 0.8),
                "events": events,
                "after": step.get("after", "once"),
            })
        if not built:
            messagebox.showinfo("Play routine",
                                "No runnable steps. Each step needs an image and a chosen macro.")
            return
        if skipped:
            self._set_status(f"Note: {skipped} step(s) skipped (missing image or macro)")

        self._set_running(True)
        self.player.play_routine(
            steps=built,
            mode=r.mode,
            repeat=r.repeat,
            scan_interval=r.scan_interval,
            wait_timeout=r.wait_timeout,
            on_status=lambda s: self.after(0, self._set_status, s),
            on_finished=lambda: self.after(0, self._on_play_finished),
        )

    def _set_routine_hotkey(self):
        if not self.current_routine:
            self._new_routine()
        self.hotkeys.pause()

        def on_done(combo):
            self.hotkeys.resume()
            if combo is None:
                return
            owner = self._hotkey_owner(combo, exclude_routine=self.current_routine)
            if owner:
                messagebox.showwarning("Hotkey in use", f"{combo} is already used by '{owner}'.")
                return
            self.current_routine.hotkey = combo
            self.routine_hotkey_var.set(combo)
            self._refresh_routine_list_preserve()
            self._save_routines()
            self._refresh_hotkeys()
            self._set_status(f"Routine hotkey set to {combo}")

        HotkeyCapture(self, on_done)

    def _clear_routine_hotkey(self):
        if self.current_routine:
            self.current_routine.hotkey = ""
            self.routine_hotkey_var.set("none")
            self._refresh_routine_list_preserve()
            self._save_routines()
            self._refresh_hotkeys()

    def _toggle_routine_by_id(self, routine_id: str):
        if self.player.running:
            self.player.stop()
            return
        idx = next((i for i, r in enumerate(self.routines) if r.id == routine_id), None)
        if idx is None:
            return
        self.nb.select(1)
        self.routine_listbox.selection_clear(0, "end")
        self.routine_listbox.selection_set(idx)
        self._on_routine_select()
        self._play_routine()

    def _make_routine_hotkey_callback(self, routine_id: str):
        return lambda: self.after(0, self._toggle_routine_by_id, routine_id)

    def _save_routines(self):
        self._commit_current_routine()
        self.storage.save_routines(self.routines)

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
        self.hotkeys.stop()
        self._save()
        self._save_routines()
        self.destroy()


def main():
    app = MacroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
