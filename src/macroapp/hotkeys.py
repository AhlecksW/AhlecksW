"""Global (system-wide) hotkeys.

``HotkeyManager`` keeps a single ``pynput`` ``GlobalHotKeys`` listener alive and
rebuilds it whenever the set of bindings changes. ``HotkeyCaptureSession`` records
the next key combination the user presses (used for inline capture in the main
window) and reports it in pynput's canonical string form (e.g. ``"<ctrl>+<alt>+1"``).
``pretty_hotkey`` turns that canonical form into a friendly label for display.
"""

from __future__ import annotations

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

# Friendly display names for Windows virtual-key codes that pynput reports
# without a usable name (numpad keys are the common case).
_VK_NAMES = {
    96: "Num0", 97: "Num1", 98: "Num2", 99: "Num3", 100: "Num4",
    101: "Num5", 102: "Num6", 103: "Num7", 104: "Num8", 105: "Num9",
    106: "Num*", 107: "Num+", 109: "Num-", 110: "Num.", 111: "Num/",
    144: "NumLock", 145: "ScrollLock",
}


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


def pretty_hotkey(combo: Optional[str]) -> str:
    """Turn a canonical hotkey string into a friendly label, e.g.
    '<ctrl>+<alt>+<105>' -> 'Ctrl+Alt+Num9'."""
    if not combo:
        return ""
    out = []
    for part in combo.split("+"):
        if part.startswith("<") and part.endswith(">"):
            inner = part[1:-1]
            if inner.isdigit():
                out.append(_VK_NAMES.get(int(inner), f"Key{inner}"))
            else:
                out.append(inner.replace("_", " ").title())
        else:
            out.append(part.upper() if len(part) == 1 else part)
    return "+".join(out)


class HotkeyCaptureSession:
    """Records the next key combo via a temporary listener (no UI of its own).

    ``on_change`` is called with the in-progress canonical string as modifiers
    are pressed/released; ``on_done`` is called once with the final combo (or
    None if cancelled with Esc). Both fire on the listener thread — the caller
    is responsible for marshalling onto the UI thread.
    """

    def __init__(self, on_change: Callable[[str], None], on_done: Callable[[Optional[str]], None]):
        self.on_change = on_change
        self.on_done = on_done
        self._mods: set = set()
        self._listener: Optional[keyboard.Listener] = None

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _press(self, key):
        name = getattr(key, "name", None)
        if name == "esc":
            self._finish(None)
            return
        if name in _MOD_CANON:
            self._mods.add(_MOD_CANON[name])
            self.on_change(combo_to_string(self._mods, "…"))
            return
        main = _key_token(key)
        if main is None:
            return
        self._finish(combo_to_string(self._mods, main))

    def _release(self, key):
        name = getattr(key, "name", None)
        if name in _MOD_CANON:
            self._mods.discard(_MOD_CANON[name])
            self.on_change(combo_to_string(self._mods, "…"))

    def _finish(self, combo: Optional[str]):
        self.stop()
        self.on_done(combo)
