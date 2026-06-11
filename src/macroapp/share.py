"""Export/import a macro as a single copy-paste 'share code'.

A share code is ``CRYO1:`` followed by base64 of a zlib-compressed JSON blob
containing the macro fields and, if present, its trigger image embedded as
base64 PNG. This makes a macro portable as one chunk of text that someone else
can paste into the app to use it (image included).
"""

from __future__ import annotations

import base64
import io
import json
import zlib
from typing import Optional, Tuple

from PIL import Image

from .storage import Macro

PREFIX = "CRYO1:"


def encode_macro(macro: Macro, image: Optional[Image.Image] = None) -> str:
    payload = macro.to_dict()
    # The receiver gets a fresh id and binds their own hotkey.
    payload.pop("id", None)
    payload.pop("hotkey", None)
    if image is not None:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "PNG")
        payload["image_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
        payload["has_image"] = True
    else:
        payload["has_image"] = False

    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    comp = zlib.compress(raw, 9)
    return PREFIX + base64.b64encode(comp).decode("ascii")


def decode_macro(text: str) -> Tuple[Macro, Optional[Image.Image]]:
    text = (text or "").strip()
    if not text.startswith(PREFIX):
        raise ValueError("That doesn't look like a macro share code (missing CRYO1: header).")
    try:
        comp = base64.b64decode(text[len(PREFIX):], validate=True)
        raw = zlib.decompress(comp)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not read share code: {exc}") from exc

    image_b64 = payload.pop("image_b64", None)
    image: Optional[Image.Image] = None
    if image_b64:
        try:
            image = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
        except Exception:
            image = None

    # 'id' was stripped on export, so from_dict assigns a fresh one.
    macro = Macro.from_dict(payload)
    macro.has_image = image is not None
    return macro, image
