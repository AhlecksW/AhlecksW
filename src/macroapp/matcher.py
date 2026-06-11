"""Screen image recognition via OpenCV template matching.

Given a target image, grab the current screen and look for the best-matching
region. ``TM_CCOEFF_NORMED`` returns a normalized score in [0, 1] which we treat
as a similarity percentage, so the user's "80% or more" maps to threshold=0.8.

A small multi-scale sweep makes matching robust to minor size differences
(e.g. DPI scaling) without the cost of a full pyramid search.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - cv2 missing only in odd envs
    cv2 = None

from PIL import Image, ImageGrab


class ImageMatcher:
    SCALES = (1.0, 0.9, 1.1, 0.8, 1.2)

    def __init__(self):
        if cv2 is None:
            raise RuntimeError(
                "opencv-python is required for image matching. "
                "Install it with: pip install opencv-python"
            )

    def grab_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """Return the current screen as a BGR numpy array."""
        shot = ImageGrab.grab(bbox=region)
        return cv2.cvtColor(np.array(shot.convert("RGB")), cv2.COLOR_RGB2BGR)

    def score(
        self,
        template: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[float, Tuple[int, int]]:
        """Return (best_score, center_xy) for the template on screen."""
        if template is None:
            return 0.0, (0, 0)

        screen = self.grab_screen(region)
        tmpl = cv2.cvtColor(np.array(template.convert("RGB")), cv2.COLOR_RGB2BGR)

        best_score = -1.0
        best_center = (0, 0)
        sh, sw = screen.shape[:2]
        ox, oy = (region[0], region[1]) if region else (0, 0)

        for scale in self.SCALES:
            th = max(1, int(tmpl.shape[0] * scale))
            tw = max(1, int(tmpl.shape[1] * scale))
            if th > sh or tw > sw:
                continue
            resized = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_center = (ox + max_loc[0] + tw // 2, oy + max_loc[1] + th // 2)

        return float(max(best_score, 0.0)), best_center

    def find(
        self,
        template: Image.Image,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[bool, Tuple[int, int]]:
        """Return (matched, center_xy). ``matched`` is True when score >= threshold."""
        score, center = self.score(template, region)
        return score >= threshold, center
