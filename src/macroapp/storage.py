"""Persistence for macros and routines: JSON indexes plus PNG trigger images.

Layout (next to the executable / project root, in a ``data`` folder):

    data/
        macros.json             # list of macro dicts (without raw image bytes)
        routines.json           # list of routine dicts (chains of image->macro)
        images/
            <macro_id>.png      # optional trigger image per macro
            step_<step_id>.png  # trigger image per routine step
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from PIL import Image

from .player import MATCH_NONE


@dataclass
class Macro:
    name: str = "New Macro"
    events: List[dict] = field(default_factory=list)
    repeat: int = 1                     # 0 == infinite
    loop_delay: float = 0.5
    match_mode: str = MATCH_NONE
    threshold: float = 0.8
    wait_timeout: float = 30.0
    has_image: bool = False
    hotkey: str = ""                    # global start hotkey, e.g. "<ctrl>+<alt>+1"
    speed: float = 1.0                  # playback speed multiplier (delays divided by this)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Macro":
        known = {f: d.get(f) for f in cls.__dataclass_fields__ if f in d}
        return cls(**known)


def new_step(macro_id: str = "") -> dict:
    """A routine step: wait for an image, then play a chosen macro."""
    return {
        "id": uuid.uuid4().hex[:12],
        "macro_id": macro_id,
        "threshold": 0.8,
        "after": "once",        # 'once' or 'repeat_until_next'
        "has_image": False,
    }


@dataclass
class Routine:
    """An ordered chain of image-triggered macro steps."""
    name: str = "New Routine"
    mode: str = "sequence"              # 'sequence' or 'reactive'
    steps: List[dict] = field(default_factory=list)
    repeat: int = 0                     # 0 == forever
    scan_interval: float = 0.4          # seconds between screen checks
    wait_timeout: float = 60.0          # max seconds to wait for an image (sequence)
    hotkey: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Routine":
        known = {f: d.get(f) for f in cls.__dataclass_fields__ if f in d}
        return cls(**known)


class Storage:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, "images")
        self.index_path = os.path.join(base_dir, "macros.json")
        self.routines_path = os.path.join(base_dir, "routines.json")
        os.makedirs(self.images_dir, exist_ok=True)

    # ----------------------------------------------------------- macro index
    def load(self) -> List[Macro]:
        if not os.path.exists(self.index_path):
            return []
        try:
            with open(self.index_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
        return [Macro.from_dict(d) for d in raw]

    def save(self, macros: List[Macro]) -> None:
        tmp = self.index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([m.to_dict() for m in macros], fh, indent=2)
        os.replace(tmp, self.index_path)

    # ---------------------------------------------------------- trigger image
    def image_path(self, macro: Macro) -> str:
        return os.path.join(self.images_dir, f"{macro.id}.png")

    def save_image(self, macro: Macro, image: Image.Image) -> None:
        image.convert("RGB").save(self.image_path(macro), "PNG")
        macro.has_image = True

    def load_image(self, macro: Macro) -> Optional[Image.Image]:
        path = self.image_path(macro)
        if macro.has_image and os.path.exists(path):
            return Image.open(path).copy()
        return None

    def delete_image(self, macro: Macro) -> None:
        path = self.image_path(macro)
        if os.path.exists(path):
            os.remove(path)
        macro.has_image = False

    # --------------------------------------------------------- routine index
    def load_routines(self) -> List["Routine"]:
        if not os.path.exists(self.routines_path):
            return []
        try:
            with open(self.routines_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
        return [Routine.from_dict(d) for d in raw]

    def save_routines(self, routines: List["Routine"]) -> None:
        tmp = self.routines_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([r.to_dict() for r in routines], fh, indent=2)
        os.replace(tmp, self.routines_path)

    # ------------------------------------------------------ routine step image
    def step_image_path(self, step_id: str) -> str:
        return os.path.join(self.images_dir, f"step_{step_id}.png")

    def save_step_image(self, step: dict, image: Image.Image) -> None:
        image.convert("RGB").save(self.step_image_path(step["id"]), "PNG")
        step["has_image"] = True

    def load_step_image(self, step: dict) -> Optional[Image.Image]:
        path = self.step_image_path(step["id"])
        if step.get("has_image") and os.path.exists(path):
            return Image.open(path).copy()
        return None

    def delete_step_image(self, step: dict) -> None:
        path = self.step_image_path(step["id"])
        if os.path.exists(path):
            os.remove(path)
        step["has_image"] = False
