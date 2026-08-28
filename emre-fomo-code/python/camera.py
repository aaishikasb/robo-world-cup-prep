import base64
import io
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

from wall_detector import WallDetector

# --- Edge Impulse (optional) ---
try:
    from edge_impulse_linux.image import ImageImpulseRunner
    _EI_AVAILABLE = True
except ImportError:
    _EI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CAMERA_URL = os.getenv("ROBOCUP_CAMERA_URL", "http://192.168.5.1:81/stream")

_python_dir = Path(__file__).resolve().parent
_eim_files  = list(_python_dir.glob("*.eim"))
MODEL_PATH  = _eim_files[0] if _eim_files else None

# ---------------------------------------------------------------------------
# Shared camera state
# ---------------------------------------------------------------------------

_current_image: Image.Image | None = None
_image_lock = threading.Lock()
_camera_stop = threading.Event()
_camera_response = None

_preview_image: bytes = b""
_preview_result: dict = {}
_preview_lock = threading.Lock()


def _camera_reader() -> None:
    global _current_image, _camera_response

    while not _camera_stop.is_set():
        buffer = b""
        try:
            print(f"[INFO] connecting to camera: {CAMERA_URL}")
            _camera_response = requests.get(CAMERA_URL, stream=True, timeout=(5, 10))
            _camera_response.raise_for_status()
            print(f"[INFO] camera connected")

            for chunk in _camera_response.iter_content(chunk_size=1024):
                if _camera_stop.is_set():
                    break
                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end   = buffer.find(b"\xff\xd9", start + 2)
                    if start == -1 or end == -1:
                        break
                    jpg    = buffer[start:end + 2]
                    buffer = buffer[end + 2:]
                    try:
                        frame = Image.open(io.BytesIO(jpg)).convert("RGB")
                        with _image_lock:
                            _current_image = frame
                        _push_preview(frame)
                    except Exception as e:
                        print(f"[WARN] bad frame: {e}")

        except requests.exceptions.RequestException as e:
            print(f"[WARN] camera stream interrupted: {e}")
        finally:
            if _camera_response is not None:
                _camera_response.close()

        if not _camera_stop.is_set():
            time.sleep(1)


def _push_preview(frame: Image.Image, result: dict | None = None) -> None:
    buf = io.BytesIO()
    frame.save(buf, "JPEG", quality=70)
    with _preview_lock:
        global _preview_image, _preview_result
        _preview_image = buf.getvalue()
        _preview_result = result or {}


def get_preview_image() -> dict:
    with _preview_lock:
        img   = _preview_image
        result = _preview_result
    if not img:
        return {"image": "", "status": "waiting for camera"}
    return {
        "image":  base64.b64encode(img).decode("ascii"),
        "result": result,
    }


def _start_camera() -> None:
    threading.Thread(target=_camera_reader, daemon=True).start()


def _copy_frame() -> Image.Image | None:
    with _image_lock:
        return _current_image.copy() if _current_image is not None else None


# ---------------------------------------------------------------------------
# Wall detector
# ---------------------------------------------------------------------------

_wall = WallDetector()


def _detect_wall(pil_frame: Image.Image) -> tuple[str, dict]:
    bgr = cv2.cvtColor(np.asarray(pil_frame), cv2.COLOR_RGB2BGR)
    return _wall.detect_with_coverage(bgr)


# ---------------------------------------------------------------------------
# Optional Edge Impulse runner
# ---------------------------------------------------------------------------

runner = None
if _EI_AVAILABLE and MODEL_PATH is not None and MODEL_PATH.exists():
    runner = ImageImpulseRunner(str(MODEL_PATH))


def _run_inference(frame: Image.Image) -> list:
    if runner is None:
        return []
    try:
        image       = np.asarray(frame.convert("RGB"))
        features, cropped = runner.get_features_from_image_auto_studio_settings(image)
        result      = runner.classify(features)
        boxes       = result.get("result", {}).get("bounding_boxes", [])
        detections  = [b for b in boxes if float(b.get("value", 0)) >= 0.55]
        display = Image.fromarray(cropped.astype(np.uint8)).convert("RGB")
        _push_preview(display, {"detections": detections, "timing": result.get("timing", {})})
        return detections
    except Exception as e:
        print(f"[WARN] inference error: {e}")
        return []
