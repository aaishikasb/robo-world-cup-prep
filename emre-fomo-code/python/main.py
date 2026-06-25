import base64
import io, os
import json
import requests
import stat
import threading
import time

from pathlib import Path
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from edge_impulse_linux.image import ImageImpulseRunner
from PIL import Image, ImageDraw, ImageFont
import numpy as np


# for Hiwonder specifically, this is the standard IP/URL address to connect to,
# don't connect another device to .1:81 or it will interrupt the code stream
CAMERA_URL = "http://192.168.5.1:81/stream"
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_FOLDER / "python" / "miniauto-soccer-robo-world-cup-training-v2-linux-aarch64-v1-impulse-#1.eim"

# Basic tuning values for image quality, loop timing, and detection confidence
LOOP_DELAY_SECONDS = 0.03
MIN_SCORE = 0.55
PREVIEW_JPEG_QUALITY = 85

# ── Ball-chasing tuning ───────────────────────────────────────────────────────
# Label your Edge Impulse model uses for the soccer ball — adjust if needed
BALL_LABEL = "soccer_ball"

# How fast the robot drives forward when it sees the ball (0–255)
BALL_DRIVE_SPEED = 150

# Duration of each forward pulse sent to the Arduino (milliseconds).
# Keep this short — the loop re-triggers every LOOP_DELAY_SECONDS, so the
# robot moves continuously as long as the ball stays in frame.
BALL_DRIVE_MS = 200
# ─────────────────────────────────────────────────────────────────────────────

# Shared state that gets updated while the camera and app loop are running
current_image = None
image_lock = threading.Lock()
preview_image = b""
preview_result = {}
preview_updated_at = 0

camera_response = None
camera_stop = threading.Event()

runner = ImageImpulseRunner(str(MODEL_PATH))

# Robot drive state — tracks whether we're currently chasing the ball
_robot_chasing = False


# ── Robot helpers ─────────────────────────────────────────────────────────────

class MiniAutoRobot:
    def drive(self, command: str, speed: int = 150, ms: int = 500) -> bool:
        return bool(Bridge.call("drive", command, int(speed), int(ms)))

    def stop(self) -> bool:
        return bool(Bridge.call("stop"))

    def read_sensors(self) -> dict:
        raw = Bridge.call("read_sensors")
        if not raw:
            return {}
        return json.loads(raw)

    def servo(self, angle: int) -> bool:
        return bool(Bridge.call("servo", int(angle)))

    def buzz(self) -> bool:
        return bool(Bridge.call("buzz"))

    def led(self, on: bool) -> bool:
        return bool(Bridge.call("led", bool(on)))

    def drive_raw(self, m0: int, m1: int, m2: int, m3: int, ms: int = 500) -> bool:
        return bool(Bridge.call("drive_raw", int(m0), int(m1), int(m2), int(m3), int(ms)))

    def health(self) -> dict:
        raw = Bridge.call("health")
        if not raw:
            return {}
        return json.loads(raw)


robot = MiniAutoRobot()


def react_to_detections(summary: dict) -> None:
    """Drive the robot forward when the ball is visible; stop immediately when it isn't."""
    global _robot_chasing

    ball_detected = any(
        d["label"] == BALL_LABEL for d in summary.get("detections", [])
    )

    if ball_detected:
        if not _robot_chasing:
            print(f"[ROBOT] ball detected — chasing")
            _robot_chasing = True
        # Send a fresh forward pulse every loop tick while the ball is visible.
        robot.drive("forward", BALL_DRIVE_SPEED, BALL_DRIVE_MS)
    else:
        if _robot_chasing:
            print(f"[ROBOT] ball lost — stopping immediately")
            robot.stop()
            _robot_chasing = False


# ── Model helpers ─────────────────────────────────────────────────────────────

def make_model_executable(model_path):
    if not os.path.exists(model_path):
        return
    os.chmod(
        model_path,
        os.stat(model_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
    )


# ── Camera helpers ────────────────────────────────────────────────────────────

def turn_frame_into_jpeg(frame, quality):
    buffer = io.BytesIO()
    frame.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def camera_reader():
    global current_image, camera_response

    while not camera_stop.is_set():
        # MJPEG stream comes in as bytes; buffer collects bytes that haven't
        # formed a complete JPEG yet.
        buffer = b""

        try:
            print(f"[INFO] connecting to camera: {CAMERA_URL}")
            camera_response = requests.get(CAMERA_URL, stream=True, timeout=(5, None))
            camera_response.raise_for_status()
            print(f"[INFO] camera connected: {CAMERA_URL}")

            for chunk in camera_response.iter_content(chunk_size=1024):
                if camera_stop.is_set():
                    break

                buffer += chunk

                while True:
                    # JPEG frames start with FF D8 and end with FF D9.
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start + 2)

                    if start == -1 or end == -1:
                        break

                    jpg = buffer[start:end + 2]
                    buffer = buffer[end + 2:]

                    try:
                        frame = Image.open(io.BytesIO(jpg)).convert("RGB")
                        with image_lock:
                            current_image = frame
                    except Exception as e:
                        print(f"[WARN] skipped bad MJPEG frame: {e}")

        except requests.exceptions.RequestException as e:
            print(f"[WARN] camera stream interrupted: {e}")

        finally:
            if camera_response is not None:
                camera_response.close()

        if not camera_stop.is_set():
            print("[INFO] reconnecting to camera in 1 second")
            time.sleep(1)


def start_camera():
    camera_thread = threading.Thread(target=camera_reader, daemon=True)
    camera_thread.start()


def stop_camera():
    camera_stop.set()
    if camera_response is not None:
        camera_response.close()


def copy_current_image():
    with image_lock:
        return None if current_image is None else current_image.copy()


def update_browser_preview(frame, result):
    global preview_image, preview_result, preview_updated_at
    with image_lock:
        preview_image = turn_frame_into_jpeg(frame, PREVIEW_JPEG_QUALITY)
        preview_result = result
        preview_updated_at = int(time.time() * 1000)


def get_preview_image():
    with image_lock:
        image_bytes = preview_image
        result = preview_result

    if not image_bytes:
        return {"image": "", "status": "waiting for camera"}

    return {
        "image": base64.b64encode(image_bytes).decode("ascii"),
        "result": result,
    }


# ── Inference helpers ─────────────────────────────────────────────────────────

def draw_detections(frame, result):
    image = frame.convert("RGB")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default()
    except Exception as e:
        print(f"[WARN] default font unavailable: {e}")
        font = None

    boxes = result.get("result", {}).get("bounding_boxes", [])

    for box in boxes:
        score = float(box.get("value", 0))
        if score < MIN_SCORE:
            continue

        label = box.get("label", "object")
        x = int(box.get("x", 0))
        y = int(box.get("y", 0))
        width = int(box.get("width", 0))
        height = int(box.get("height", 0))

        # Highlight soccer ball detections in a different colour
        color = (255, 200, 0) if label == BALL_LABEL else (0, 255, 80)

        text = f"{label} {score:.2f}"
        text_width = max(120, len(text) * 7)

        draw.rectangle([(x, y), (x + width, y + height)], outline=color, width=3)
        draw.rectangle([(x, max(0, y - 18)), (x + text_width, y)], fill=color)
        draw.text((x + 3, max(0, y - 16)), text, fill=(0, 0, 0), font=font)

    return image


def summarize_detections(result):
    boxes = result.get("result", {}).get("bounding_boxes", [])
    detections = []

    for box in boxes:
        score = float(box.get("value", 0))
        if score < MIN_SCORE:
            continue
        detections.append({
            "label": box.get("label"),
            "score": score,
            "x": box.get("x"),
            "y": box.get("y"),
            "width": box.get("width"),
            "height": box.get("height"),
        })

    return {
        "detections": detections,
        "timing": result.get("timing", {}),
    }


def run_inference(frame):
    image = np.asarray(frame.convert("RGB"))
    features, cropped = runner.get_features_from_image_auto_studio_settings(image)
    result = runner.classify(features)

    display_image = Image.fromarray(cropped.astype(np.uint8)).convert("RGB")
    display_image = draw_detections(display_image, result)

    summary = summarize_detections(result)

    if summary["detections"]:
        print(f"[DETECT] {summary['detections']}")

    return display_image, summary


# ── Main loop ─────────────────────────────────────────────────────────────────

def loop():
    frame = copy_current_image()

    if frame is None:
        time.sleep(LOOP_DELAY_SECONDS)
        return

    try:
        display_image, summary = run_inference(frame)
    except Exception as e:
        print(f"[WARN] inference failed: {e}")
        display_image = frame
        summary = {"error": str(e)}

    # React to whatever the model found this frame.
    react_to_detections(summary)

    update_browser_preview(display_image, summary)
    time.sleep(LOOP_DELAY_SECONDS)


# ── Startup ───────────────────────────────────────────────────────────────────

print(f"[INFO] model: {MODEL_PATH}")
print(f"[INFO] camera: {CAMERA_URL}")
print(f"[INFO] chasing label: '{BALL_LABEL}' (speed={BALL_DRIVE_SPEED}, pulse={BALL_DRIVE_MS}ms, stop=immediate)")

make_model_executable(MODEL_PATH)

ui = WebUI(assets_dir_path=PROJECT_FOLDER / "assets")
ui.expose_api("GET", "/preview", get_preview_image)

try:
    model_info = runner.init()
    print(f"[INFO] loaded Edge Impulse model: {model_info['project']['name']}")

    start_camera()
    App.run(user_loop=loop)

finally:
    robot.stop()
    stop_camera()
    runner.stop()