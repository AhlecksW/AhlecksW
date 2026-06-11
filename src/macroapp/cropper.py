"""Full-screen 'drag a box' tool to crop a region of the screen into an image.

We freeze the screen by displaying a screenshot on a fullscreen canvas, let the
user rubber-band a rectangle, then crop those coordinates out of the screenshot.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from PIL import Image, ImageGrab, ImageTk


class ScreenCropper(tk.Toplevel):
    def __init__(self, master, on_done: Callable[[Optional[Image.Image]], None]):
        super().__init__(master)
        self.on_done = on_done

        # Capture the whole screen first, then show it so the user crops a
        # frozen frame rather than a live (and changing) desktop.
        self._screenshot = ImageGrab.grab()
        self._photo = ImageTk.PhotoImage(self._screenshot)

        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.configure(cursor="cross")

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.create_text(
            self._screenshot.width // 2, 30,
            text="Drag to select a region  •  Esc to cancel",
            fill="#ffcc00", font=("Segoe UI", 16, "bold"),
        )

        self._start_x = self._start_y = 0
        self._rect = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda _e: self._finish(None))

        self.focus_force()

    def _on_press(self, event):
        self._start_x, self._start_y = event.x, event.y
        if self._rect:
            self.canvas.delete(self._rect)
        self._rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00d0ff", width=2,
        )

    def _on_drag(self, event):
        if self._rect:
            self.canvas.coords(self._rect, self._start_x, self._start_y, event.x, event.y)

    def _on_release(self, event):
        x1, x2 = sorted((self._start_x, event.x))
        y1, y2 = sorted((self._start_y, event.y))
        if x2 - x1 < 3 or y2 - y1 < 3:
            self._finish(None)
            return
        cropped = self._screenshot.crop((x1, y1, x2, y2))
        self._finish(cropped)

    def _finish(self, image: Optional[Image.Image]):
        self.destroy()
        self.on_done(image)
