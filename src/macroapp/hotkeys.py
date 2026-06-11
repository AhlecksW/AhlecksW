"""Global (system-wide) hotkeys.

``HotkeyManager`` keeps a single ``pynput`` ``GlobalHotKeys`` listener alive and
rebuilds it whenever the set of bindings changes. ``HotkeyCapture`` is a small
modal dialog that records the next key combination the user presses and returns
it in pynput's canonical string form (e.g. ``"<ctrl>+<alt>+1"``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from pynput import keyboard

# Map every modifier variant onto a single canonical token.
_MOD_CANON = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
}
_MOD_ORDER = ["ctrl", "alt", "shift", "cmd"]


class HotkeyManager:
    """Holds a live GlobalHotKeys listener built from {hotkey_str: callback}."""

    def __init__(self):
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._mapping: Dict[str, Callable[[], None]] = {}
        self._paused = False

    def set_bindings(self, mapping: Dict[str, Callable[[], None]]) -> None:
        self._mapping = {k: v for k, v in mapping.items() if k}
        self._rebuild()

    def pause(self) -> None:
        """Temporarily stop listening (e.g. while recording or capturing)."""
        self._paused = True
        self._stop_listener()

    def resume(self) -> None:
        self._paused = False
        self._rebuild()

    def stop(self) -> None:
        self._paused = True
        self._stop_listener()

    # ------------------------------------------------------------- internals
    def _rebuild(self) -> None:
        self._stop_listener()
        if self._paused or not self._mapping:
            return
        try:
            self._listener = keyboard.GlobalHotKeys(dict(self._mapping))
            self._listener.start()
        except Exception:
            # An invalid combo shouldn't take the whole app down.
            self._listener = None

    def _stop_listener(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None


def _key_token(key) -> Optional[str]:
    """Return the canonical token for a pressed key, or None to ignore."""
    name = getattr(key, "name", None)
    if name in _MOD_CANON:
        return None  # modifiers handled separately
    char = getattr(key, "char", None)
    if char:
        c = char.lower()
        # Control characters come through as e.g. '\x01' for ctrl+a; fall back to vk.
        if c.isprintable() and not c.isspace():
            return c
    if name:
        return f"<{name}>"
    vk = getattr(key, "vk", None)
    if vk is not None:
        return f"<{vk}>"
    return None


def combo_to_string(mods: set, main: str) -> str:
    parts = [f"<{m}>" for m in _MOD_ORDER if m in mods]
    parts.append(main)
    return "+".join(parts)


class HotkeyCapture(tk.Toplevel):
    """Modal dialog: records the next key combo and reports it via ``on_done``."""

    def __init__(self, master, on_done: Callable[[Optional[str]], None]):
        super().__init__(master)
        self.on_done = on_done
        self.title("Set hotkey")
        self.resizable(False, False)
        try:
            from .theme import FROST_BG
            self.configure(bg=FROST_BG)
        except Exception:
            pass
        self.transient(master)
        self.grab_set()

        self._mods: set = set()

        ttk.Label(
            self, text="Press the key combination…\n(Esc to cancel)",
            justify="center", padding=20, font=("Segoe UI", 11),
        ).pack()
        self._preview = ttk.Label(self, text="", font=("Segoe UI", 12, "bold"))
        self._preview.pack(pady=(0, 14))

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        self.update_idletasks()
        self._center_on(master)

    def _center_on(self, master):
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    def _on_press(self, key):
        name = getattr(key, "name", None)
        if name == "esc":
            self._finish(None)
            return
        if name in _MOD_CANON:
            self._mods.add(_MOD_CANON[name])
            self._update_preview(None)
            return
        main = _key_token(key)
        if main is None:
            return
        combo = combo_to_string(self._mods, main)
        self._update_preview(main)
        self._finish(combo)

    def _on_release(self, key):
        name = getattr(key, "name", None)
        if name in _MOD_CANON:
            self._mods.discard(_MOD_CANON[name])
            self._update_preview(None)

    def _update_preview(self, main: Optional[str]):
        shown = combo_to_string(self._mods, main if main else "…")
        try:
            self.after(0, lambda: self._preview.config(text=shown))
        except Exception:
            pass

    def _finish(self, combo: Optional[str]):
        try:
            self._listener.stop()
        except Exception:
            pass
        self.grab_release()
        self.destroy()
        self.on_done(combo)
