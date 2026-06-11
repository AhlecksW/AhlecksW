"""Records mouse and keyboard activity into a serializable list of events.

Each event is a plain dict so it can be saved straight to JSON:

    {"t": 1.234, "type": "click",  "x": 10, "y": 20, "button": "left", "pressed": true}
    {"t": 1.500, "type": "move",   "x": 11, "y": 21}
    {"t": 1.800, "type": "scroll", "x": 11, "y": 21, "dx": 0, "dy": -1}
    {"t": 2.000, "type": "key",    "action": "press",   "kind": "char", "value": "a"}
    {"t": 2.100, "type": "key",    "action": "release", "kind": "key",  "value": "shift"}

``t`` is seconds elapsed since recording started, so playback can reproduce
the original timing.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from pynput import keyboard, mouse


class MacroRecorder:
    def __init__(self, capture_moves: bool = False, move_min_interval: float = 0.03):
        # Mouse-move events are extremely chatty. They are off by default and,
        # when enabled, throttled so we don't store hundreds of points a second.
        self.capture_moves = capture_moves
        self.move_min_interval = move_min_interval

        self.events: List[dict] = []
        self.recording = False

        self._start = 0.0
        self._last_move = 0.0
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kbd_listener: Optional[keyboard.Listener] = None

        # Key that ends recording (never written into the macro itself).
        self.stop_key = keyboard.Key.f9
        self._on_stop: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------ API
    def start(self, on_stop: Optional[Callable[[], None]] = None) -> None:
        if self.recording:
            return
        self.events = []
        self._start = time.time()
        self._last_move = 0.0
        self._on_stop = on_stop
        self.recording = True

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
            on_move=self._on_move if self.capture_moves else None,
        )
        self._kbd_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._mouse_listener.start()
        self._kbd_listener.start()

    def stop(self) -> List[dict]:
        if not self.recording:
            return self.events
        self.recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._kbd_listener:
            self._kbd_listener.stop()
            self._kbd_listener = None
        return self.events

    # --------------------------------------------------------------- helpers
    def _t(self) -> float:
        return round(time.time() - self._start, 4)

    def _add(self, event: dict) -> None:
        if self.recording:
            self.events.append(event)

    # ---------------------------------------------------------- mouse hooks
    def _on_click(self, x, y, button, pressed):
        self._add({
            "t": self._t(),
            "type": "click",
            "x": int(x),
            "y": int(y),
            "button": button.name,
            "pressed": bool(pressed),
        })

    def _on_scroll(self, x, y, dx, dy):
        self._add({
            "t": self._t(),
            "type": "scroll",
            "x": int(x),
            "y": int(y),
            "dx": int(dx),
            "dy": int(dy),
        })

    def _on_move(self, x, y):
        now = time.time()
        if now - self._last_move < self.move_min_interval:
            return
        self._last_move = now
        self._add({
            "t": self._t(),
            "type": "move",
            "x": int(x),
            "y": int(y),
        })

    # ------------------------------------------------------- keyboard hooks
    def _on_press(self, key):
        if key == self.stop_key:
            self.stop()
            if self._on_stop:
                self._on_stop()
            return False  # stop the keyboard listener
        self._add({"t": self._t(), "type": "key", "action": "press", **_key_to_dict(key)})

    def _on_release(self, key):
        if key == self.stop_key:
            return
        self._add({"t": self._t(), "type": "key", "action": "release", **_key_to_dict(key)})


def _key_to_dict(key) -> dict:
    """Serialize a pynput key (KeyCode or Key) to a JSON-friendly dict."""
    char = getattr(key, "char", None)
    if char is not None:
        return {"kind": "char", "value": char}
    name = getattr(key, "name", None)
    if name is not None:
        return {"kind": "key", "value": name}
    # Fallback: virtual key code (e.g. some media keys).
    return {"kind": "vk", "value": getattr(key, "vk", None)}
