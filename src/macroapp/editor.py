"""Step editor: view every recorded event, the delay before it, and edit timing.

Shows the macro as a table of steps. The "Delay (s)" column is the gap before
each step (its frequency relative to the previous one) and is editable inline —
double-click a row's delay, type a new value, Enter to apply. Editing a delay
shifts that step and everything after it, preserving the rest of the timing.
A "Scale all delays" control multiplies every gap at once (slower/faster).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional


def _details(ev: dict) -> str:
    t = ev.get("type")
    if t == "move":
        return f"move to ({ev.get('x')}, {ev.get('y')})"
    if t == "click":
        updown = "down" if ev.get("pressed") else "up"
        return f"{ev.get('button')} {updown} @ ({ev.get('x')}, {ev.get('y')})"
    if t == "scroll":
        return f"scroll dx={ev.get('dx')} dy={ev.get('dy')} @ ({ev.get('x')}, {ev.get('y')})"
    if t == "key":
        return f"key {ev.get('action')}: {ev.get('value')!r}"
    return str(ev)


class EventEditor(tk.Toplevel):
    def __init__(self, master, events: List[dict], on_save: Callable[[List[dict]], None]):
        super().__init__(master)
        self.on_save = on_save
        self.title("Edit steps")
        self.geometry("560x460")
        self.transient(master)

        # Working copy so edits aren't applied until Save.
        self.work: List[dict] = [dict(e) for e in events]
        self.delays: List[float] = self._compute_delays(self.work)

        self._build()
        self._reload()

    # ---------------------------------------------------------------- build
    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)

        cols = ("num", "delay", "type", "details")
        self.tree = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("num", text="#")
        self.tree.heading("delay", text="Delay (s)")
        self.tree.heading("type", text="Type")
        self.tree.heading("details", text="Details")
        self.tree.column("num", width=40, anchor="center", stretch=False)
        self.tree.column("delay", width=80, anchor="center", stretch=False)
        self.tree.column("type", width=70, anchor="center", stretch=False)
        self.tree.column("details", width=320, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self._on_double_click)

        ttk.Label(
            self, text="Double-click a Delay to edit the gap before that step.",
            padding=(8, 0), foreground="#555",
        ).pack(anchor="w")

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Delete step", command=self._delete).pack(side="left")
        ttk.Label(bar, text="Scale all delays ×").pack(side="left", padx=(16, 2))
        self.scale_var = tk.StringVar(value="1.0")
        ttk.Spinbox(bar, from_=0.1, to=10, increment=0.1, width=6, textvariable=self.scale_var).pack(side="left")
        ttk.Button(bar, text="Apply", command=self._scale_all).pack(side="left", padx=4)
        ttk.Button(bar, text="Save & Close", command=self._save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=4)

        self.total_var = tk.StringVar()
        ttk.Label(self, textvariable=self.total_var, padding=(8, 0, 8, 8), foreground="#555").pack(anchor="w")

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _compute_delays(events: List[dict]) -> List[float]:
        delays, prev = [], 0.0
        for e in events:
            t = e.get("t", prev)
            delays.append(round(max(0.0, t - prev), 3))
            prev = t
        return delays

    def _rebuild_times(self):
        t = 0.0
        for i, e in enumerate(self.work):
            t += self.delays[i]
            e["t"] = round(t, 4)

    def _reload(self):
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.work):
            self.tree.insert(
                "", "end", iid=str(i),
                values=(i + 1, f"{self.delays[i]:.3f}", e.get("type"), _details(e)),
            )
        total = sum(self.delays)
        self.total_var.set(f"{len(self.work)} steps · total runtime ≈ {total:.2f}s")

    # --------------------------------------------------------------- actions
    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#2":  # only the Delay column
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(item)
        x, y, w, h = self.tree.bbox(item, "#2")
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, f"{self.delays[idx]:.3f}")
        entry.select_range(0, "end")
        entry.focus_set()

        def commit(_e=None):
            try:
                val = max(0.0, float(entry.get()))
                self.delays[idx] = round(val, 3)
                self._rebuild_times()
                self._reload()
            except ValueError:
                pass
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", lambda _e: entry.destroy())
        entry.bind("<Escape>", lambda _e: entry.destroy())

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        del self.work[idx]
        del self.delays[idx]
        self._rebuild_times()
        self._reload()

    def _scale_all(self):
        try:
            factor = float(self.scale_var.get())
        except ValueError:
            return
        if factor <= 0:
            return
        self.delays = [round(d * factor, 3) for d in self.delays]
        self._rebuild_times()
        self._reload()

    def _save(self):
        self._rebuild_times()
        self.on_save(self.work)
        self.destroy()
