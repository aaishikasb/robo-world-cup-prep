import base64
import io
import os
import stat
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from robot_client import MiniAutoRobot
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
            _camera_response = requests.get(CAMERA_URL, stream=True, timeout=(5, None))
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
_last_wall_side = "UNKNOWN"


def _detect_wall(pil_frame: Image.Image) -> str:
    bgr = cv2.cvtColor(np.asarray(pil_frame), cv2.COLOR_RGB2BGR)
    return _wall.detect(bgr)


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
        # push annotated preview with detection data
        display = Image.fromarray(cropped.astype(np.uint8)).convert("RGB")
        _push_preview(display, {"detections": detections, "timing": result.get("timing", {})})
        return detections
    except Exception as e:
        print(f"[WARN] inference error: {e}")
        return []


# ---------------------------------------------------------------------------
# Robot + startup prints
# ---------------------------------------------------------------------------

robot = MiniAutoRobot()

print(f"health   : {robot.health()}")
print(f"sensors  : {robot.read_sensors()}")

_last_toggle = robot.hold_toggle()
print(f"[TEAM] active team: {'BLUE' if _last_toggle else 'RED'}  (hold CAM button 5 s to switch)")


# ---------------------------------------------------------------------------
# Drive helpers (blocking — wait for move to finish before next command)
# ---------------------------------------------------------------------------

def drive(direction: str, speed: int = 150, ms: int = 500) -> None:
    print(f"  {direction:14s} speed={speed} ms={ms}")
    robot.drive(direction, speed, ms)
    time.sleep(ms / 1000.0)


def drive_diag(direction: str, speed: int = 150, ms: int = 500) -> None:
    print(f"  {direction:14s} speed={speed} ms={ms}")
    robot.drive_diagonal(direction, speed, ms)
    time.sleep(ms / 1000.0)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def loop() -> None:
    global _last_toggle, _last_wall_side

    # Team toggle check
    current = robot.hold_toggle()
    if current != _last_toggle:
        _last_toggle = current
        print(f"[TEAM] switched to: {'BLUE' if current else 'RED'}")

    # Camera: wall detection + optional inference
    frame = _copy_frame()
    if frame is not None:
        side = _detect_wall(frame)
        if side != _last_wall_side:
            _last_wall_side = side
            print(f"[WALL] side: {side}")
        detections = _run_inference(frame)
        if detections:
            print(f"[DETECT] {detections}")

    # --- Movement sequence ---
    drive("forward",        speed=150, ms=500)
    drive("backward",       speed=150, ms=500)
    drive("left",           speed=150, ms=500)
    drive("right",          speed=150, ms=500)
    drive_diag("forward_left",  speed=150, ms=500)
    drive_diag("forward_right", speed=150, ms=500)
    drive_diag("back_left",     speed=150, ms=500)
    drive_diag("back_right",    speed=150, ms=500)
    drive("rotate_left",    speed=255, ms=3250)
    time.sleep(0.5)
    drive("rotate_right",   speed=255, ms=3250)

    robot.stop()
    time.sleep(0.5)

    # --- Sensors ---
    sensors = robot.read_sensors()
    print(f"ultrasonic : {sensors.get('ultrasonic_cm')} cm")
    print(f"battery    : {sensors.get('battery_mv')} mV")
    print(f"line       : {sensors.get('line_digital')}")

    # --- Extras ---
    robot.led(True)
    robot.servo(90)
    robot.servo(150)
    robot.servo(30)
    robot.servo(90)
    robot.led(False)

    robot.stop()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

_start_camera()

assets_dir = Path(__file__).resolve().parent.parent / "assets"
if (assets_dir / "index.html").exists():
    ui = WebUI(assets_dir_path=assets_dir)
    ui.expose_api("GET", "/preview", get_preview_image)
    print(f"[INFO] WebUI assets: {assets_dir}")
else:
    print("[WARN] WebUI disabled: assets/index.html not found")

if runner is not None:
    MODEL_PATH.chmod(MODEL_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    runner.init()
    print(f"[INFO] Edge Impulse model loaded: {MODEL_PATH.name}")
else:
    print("[INFO] no .eim model found - running camera + wall detection only")

print("[INFO] waiting for BOOT button to start...")
try:
    App.run(user_loop=lambda: robot.run_program(loop))
finally:
    robot.stop()
    _camera_stop.set()
    if _camera_response is not None:
        _camera_response.close()
    if runner is not None:
        runner.stop()
