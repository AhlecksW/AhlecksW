"""Persistence for macros: a JSON index plus PNG files for trigger images.

Layout (next to the executable / project root, in a ``data`` folder):

    data/
        macros.json        # list of macro dicts (without raw image bytes)
        images/
            <macro_id>.png # optional trigger image per macro
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


class Storage:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, "images")
        self.index_path = os.path.join(base_dir, "macros.json")
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
