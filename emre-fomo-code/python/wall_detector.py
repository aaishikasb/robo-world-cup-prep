"""wall_detector.py

HSV-based wall tape colour detector for the miniAuto soccer field.

Usage (frame-by-frame, no VideoCapture needed):
    from wall_detector import WallDetector
    detector = WallDetector()
    side = detector.detect(bgr_frame)   # "RED", "BLUE", or "UNKNOWN"

Field convention:
  RED  tape  -> robot is on the RED  side
  BLUE tape  -> robot is on the BLUE side
  UNKNOWN    -> neither colour is dominant
"""

from __future__ import annotations

import cv2
import numpy as np

# HSV colour ranges  (Hue 0-179, Sat/Val 0-255)
_RED_LOWER_1 = np.array([0,   120,  70], dtype=np.uint8)
_RED_UPPER_1 = np.array([10,  255, 255], dtype=np.uint8)
_RED_LOWER_2 = np.array([160, 120,  70], dtype=np.uint8)
_RED_UPPER_2 = np.array([179, 255, 255], dtype=np.uint8)

_BLUE_LOWER  = np.array([100, 120,  70], dtype=np.uint8)
_BLUE_UPPER  = np.array([130, 255, 255], dtype=np.uint8)

_MIN_COVERAGE = 0.02   # 2% of frame pixels


class WallDetector:
    def __init__(self, min_coverage: float = _MIN_COVERAGE) -> None:
        self.min_coverage = min_coverage

    def detect(self, frame_bgr: np.ndarray) -> str:
        """Return 'RED', 'BLUE', or 'UNKNOWN' for a given BGR frame."""
        if frame_bgr is None or frame_bgr.size == 0:
            return "UNKNOWN"
        hsv   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        total = hsv.shape[0] * hsv.shape[1]
        red_f  = self._count_red(hsv)  / total
        blue_f = self._count_blue(hsv) / total
        if red_f < self.min_coverage and blue_f < self.min_coverage:
            return "UNKNOWN"
        return "RED" if red_f >= blue_f else "BLUE"

    def coverage(self, frame_bgr: np.ndarray) -> dict:
        """Return {'red': float, 'blue': float, 'total_pixels': int} for diagnostics."""
        if frame_bgr is None or frame_bgr.size == 0:
            return {"red": 0.0, "blue": 0.0, "total_pixels": 0}
        hsv   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        total = hsv.shape[0] * hsv.shape[1]
        return {
            "red":          self._count_red(hsv)  / total,
            "blue":         self._count_blue(hsv) / total,
            "total_pixels": total,
        }

    @staticmethod
    def _count_red(hsv: np.ndarray) -> int:
        m1 = cv2.inRange(hsv, _RED_LOWER_1, _RED_UPPER_1)
        m2 = cv2.inRange(hsv, _RED_LOWER_2, _RED_UPPER_2)
        return int(cv2.countNonZero(cv2.bitwise_or(m1, m2)))

    @staticmethod
    def _count_blue(hsv: np.ndarray) -> int:
        return int(cv2.countNonZero(cv2.inRange(hsv, _BLUE_LOWER, _BLUE_UPPER)))
