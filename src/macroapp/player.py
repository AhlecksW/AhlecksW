"""Replays a recorded list of events, with optional image-trigger gating.

The player runs on a background thread so the UI stays responsive and so the
user can stop it at any time (Stop button or the global F9 hotkey).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode

from .matcher import ImageMatcher

# Match modes that decide how an attached trigger image affects playback.
MATCH_NONE = "none"
MATCH_RUN_IF_PRESENT = "run_if_present"   # check before each loop; skip if not found
MATCH_WAIT_FOR_IMAGE = "wait_for_image"   # block until image appears, then run
MATCH_CLICK_IMAGE = "click_image"         # ignore recorded events, just click the image


class MacroPlayer:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._hotkey_listener: Optional[keyboard.Listener] = None

        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()
        self.matcher = ImageMatcher()

        self.stop_key = Key.f9

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ API
    def play(
        self,
        events: List[dict],
        repeat: int = 1,
        loop_delay: float = 0.5,
        match_mode: str = MATCH_NONE,
        template=None,
        threshold: float = 0.8,
        wait_timeout: float = 30.0,
        speed: float = 1.0,
        on_status: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        """Start playback. ``repeat`` of 0 means loop forever (until stopped)."""
        if self.running:
            return
        self._stop.clear()

        def status(msg: str) -> None:
            if on_status:
                on_status(msg)

        def worker():
            self._start_hotkey()
            try:
                count = 0
                while not self._stop.is_set():
                    if repeat and count >= repeat:
                        break
                    count += 1
                    label = f"{count}/{repeat}" if repeat else f"{count}/∞"
                    status(f"Run {label}")

                    if match_mode == MATCH_RUN_IF_PRESENT:
                        found, _ = self.matcher.find(template, threshold)
                        if not found:
                            status(f"Run {label}: image not found, skipping")
                            if self._sleep(loop_delay):
                                break
                            continue
                    elif match_mode == MATCH_WAIT_FOR_IMAGE:
                        status(f"Run {label}: waiting for image…")
                        if not self._wait_for_image(template, threshold, wait_timeout):
                            status(f"Run {label}: image not found within {wait_timeout:.0f}s")
                            break
                    elif match_mode == MATCH_CLICK_IMAGE:
                        found, loc = self.matcher.find(template, threshold)
                        if found:
                            self.mouse.position = loc
                            time.sleep(0.05)
                            self.mouse.click(mouse.Button.left, 1)
                        else:
                            status(f"Run {label}: image not found")
                        if self._sleep(loop_delay):
                            break
                        continue

                    self._play_once(events, speed)
                    if self._sleep(loop_delay):
                        break

                status("Stopped" if self._stop.is_set() else "Finished")
            finally:
                self._stop_hotkey()
                if on_finished:
                    on_finished()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def play_routine(
        self,
        steps: List[dict],
        mode: str = "sequence",
        repeat: int = 0,
        scan_interval: float = 0.4,
        wait_timeout: float = 60.0,
        on_status: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        """Run a chain of image-triggered macro steps.

        Each step is a dict: ``{"name", "template", "threshold", "events",
        "after"}`` where ``after`` is ``"once"`` or ``"repeat_until_next"``.
        ``mode`` is ``"sequence"`` (wait for each image in order) or
        ``"reactive"`` (watch every image and run whichever is seen).
        """
        if self.running:
            return
        self._stop.clear()
        steps = [s for s in steps if s.get("template") is not None and s.get("events") is not None]

        def status(msg: str) -> None:
            if on_status:
                on_status(msg)

        def worker():
            self._start_hotkey()
            try:
                if not steps:
                    status("Routine has no usable steps (need an image and a macro)")
                    return
                if mode == "reactive":
                    self._run_reactive(steps, repeat, scan_interval, status)
                else:
                    self._run_sequence(steps, repeat, scan_interval, wait_timeout, status)
                status("Stopped" if self._stop.is_set() else "Routine finished")
            finally:
                self._stop_hotkey()
                if on_finished:
                    on_finished()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _run_sequence(self, steps, repeat, scan_interval, wait_timeout, status):
        loop = 0
        while not self._stop.is_set():
            if repeat and loop >= repeat:
                break
            loop += 1
            label = f"{loop}/{repeat}" if repeat else f"{loop}/∞"
            for i, step in enumerate(steps):
                if self._stop.is_set():
                    return
                name = step.get("name", f"step {i + 1}")
                status(f"Routine {label}: waiting for '{name}' image…")
                if not self._wait_for_image(step["template"], step["threshold"], wait_timeout):
                    status(f"Routine {label}: '{name}' image not found within {wait_timeout:.0f}s")
                    return
                # 'repeat_until_next' keeps running this macro until the *next*
                # step's image shows up — your "do this until you see that".
                if step.get("after") == "repeat_until_next" and i + 1 < len(steps):
                    nxt = steps[i + 1]
                    status(f"Routine {label}: running '{name}' until next image…")
                    while not self._stop.is_set():
                        if self.matcher.find(nxt["template"], nxt["threshold"])[0]:
                            break
                        self._play_once(step["events"])
                        if self._sleep(scan_interval):
                            return
                else:
                    status(f"Routine {label}: running '{name}'")
                    self._play_once(step["events"])
                    if self._sleep(scan_interval):
                        return

    def _run_reactive(self, steps, repeat, scan_interval, status):
        acted = 0
        while not self._stop.is_set():
            if repeat and acted >= repeat:
                break
            matched = False
            for i, step in enumerate(steps):
                if self._stop.is_set():
                    return
                if self.matcher.find(step["template"], step["threshold"])[0]:
                    acted += 1
                    name = step.get("name", f"step {i + 1}")
                    status(f"Reactive: saw '{name}' → running ({acted}{'/' + str(repeat) if repeat else ''})")
                    self._play_once(step["events"])
                    matched = True
                    break  # rescan from the top after acting
            if not matched:
                status("Reactive: watching for trigger images…")
            if self._sleep(scan_interval):
                return

    def stop(self) -> None:
        self._stop.set()

    # -------------------------------------------------------------- internals
    def _play_once(self, events: List[dict], speed: float = 1.0) -> None:
        speed = speed if speed and speed > 0 else 1.0
        last_t = 0.0
        for ev in events:
            if self._stop.is_set():
                return
            # Reproduce original gaps between events, scaled by playback speed.
            gap = (ev.get("t", last_t) - last_t) / speed
            if gap > 0:
                if self._sleep(min(gap, 5.0)):  # cap absurd gaps
                    return
            last_t = ev.get("t", last_t)
            self._dispatch(ev)

    def _dispatch(self, ev: dict) -> None:
        etype = ev.get("type")
        if etype == "move":
            self.mouse.position = (ev["x"], ev["y"])
        elif etype == "click":
            self.mouse.position = (ev["x"], ev["y"])
            button = getattr(mouse.Button, ev.get("button", "left"), mouse.Button.left)
            if ev.get("pressed"):
                self.mouse.press(button)
            else:
                self.mouse.release(button)
        elif etype == "scroll":
            self.mouse.position = (ev["x"], ev["y"])
            self.mouse.scroll(ev.get("dx", 0), ev.get("dy", 0))
        elif etype == "key":
            key = _dict_to_key(ev)
            if key is None:
                return
            if ev.get("action") == "press":
                self.keyboard.press(key)
            else:
                self.keyboard.release(key)

    def _wait_for_image(self, template, threshold, timeout) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop.is_set():
                return False
            found, _ = self.matcher.find(template, threshold)
            if found:
                return True
            if self._sleep(0.3):
                return False
        return False

    def _sleep(self, seconds: float) -> bool:
        """Sleep but wake early if stopped. Returns True if we were stopped."""
        return self._stop.wait(timeout=max(0.0, seconds))

    # --------------------------------------------------------- stop hotkey
    def _start_hotkey(self) -> None:
        def on_press(key):
            if key == self.stop_key:
                self.stop()

        self._hotkey_listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener.start()

    def _stop_hotkey(self) -> None:
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None


def _dict_to_key(ev: dict):
    kind = ev.get("kind")
    value = ev.get("value")
    if kind == "char":
        return KeyCode.from_char(value)
    if kind == "key":
        return getattr(Key, value, None)
    if kind == "vk" and value is not None:
        return KeyCode.from_vk(value)
    return None
