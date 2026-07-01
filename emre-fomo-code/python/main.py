import base64
import io
import os
import requests
import stat
import threading
import time

from pathlib import Path
from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from edge_impulse_linux.image import ImageImpulseRunner
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from robot_client import MiniAutoRobot


CAMERA_URL = os.getenv("ROBOCUP_CAMERA_URL", "http://192.168.5.1:81/stream")
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_FOLDER / "python" / os.getenv(
    "ROBOCUP_MODEL_FILE",
    "miniauto-soccer-robo-world-cup-training-v2-linux-aarch64-v1-impulse-#1.eim",
)

LOOP_DELAY_SECONDS = float(os.getenv("ROBOCUP_LOOP_DELAY", "0.02"))
MIN_SCORE = float(os.getenv("ROBOCUP_MIN_SCORE", "0.55"))
PREVIEW_JPEG_QUALITY = int(os.getenv("ROBOCUP_PREVIEW_QUALITY", "70"))
DETECT_LOG_INTERVAL_SECONDS = float(os.getenv("ROBOCUP_DETECT_LOG_EVERY", "0.35"))

BALL_LABEL = os.getenv("ROBOCUP_BALL_LABEL", "soccer_ball")
BALL_DRIVE_SPEED = int(os.getenv("ROBOCUP_DRIVE_SPEED", "155"))
BALL_TURN_SPEED = int(os.getenv("ROBOCUP_TURN_SPEED", "120"))
BALL_DRIVE_MS = int(os.getenv("ROBOCUP_DRIVE_MS", "200"))
BALL_CHARGE_MS = int(os.getenv("ROBOCUP_CHARGE_MS", str(BALL_DRIVE_MS * 2)))
BALL_CENTER_DEADBAND = int(os.getenv("ROBOCUP_CENTER_DEADBAND", "8"))
BALL_CENTER_BIAS_PX = int(os.getenv("ROBOCUP_CENTER_BIAS_PX", "0"))
BALL_CHARGE_DEADBAND = int(os.getenv("ROBOCUP_CHARGE_DEADBAND", "18"))
BALL_CORRECTION_MS = int(os.getenv("ROBOCUP_CORRECTION_MS", "120"))
BALL_CHARGE_SPEED_NEAR = int(os.getenv("ROBOCUP_CHARGE_SPEED_NEAR", "150"))
BALL_CHARGE_SPEED_MID = int(os.getenv("ROBOCUP_CHARGE_SPEED_MID", "170"))
BALL_CHARGE_SPEED_FAR = int(os.getenv("ROBOCUP_CHARGE_SPEED_FAR", "190"))
BALL_ALIGN_DEADBAND = int(os.getenv("ROBOCUP_ALIGN_DEADBAND", "12"))
BALL_ALIGN_TURN_SPEED = int(os.getenv("ROBOCUP_ALIGN_TURN_SPEED", "85"))
BALL_ALIGN_TURN_MS = int(os.getenv("ROBOCUP_ALIGN_TURN_MS", "180"))
BALL_CORRECTION_COOLDOWN_SECONDS = float(os.getenv("ROBOCUP_CORRECTION_COOLDOWN", "0.12"))
BALL_EMA_ALPHA = float(os.getenv("ROBOCUP_BALL_EMA_ALPHA", "0.45"))
BALL_AREA_FAR = float(os.getenv("ROBOCUP_BALL_AREA_FAR", "80"))
BALL_AREA_NEAR = float(os.getenv("ROBOCUP_BALL_AREA_NEAR", "220"))
BALL_AREA_CONTACT = float(os.getenv("ROBOCUP_BALL_AREA_CONTACT", "420"))
BALL_COMMIT_SECONDS = float(os.getenv("ROBOCUP_BALL_COMMIT_SECONDS", "0.55"))
BALL_COMMIT_SPEED = int(os.getenv("ROBOCUP_BALL_COMMIT_SPEED", "205"))
BALL_COMMIT_MS = int(os.getenv("ROBOCUP_BALL_COMMIT_MS", "420"))
BALL_VECTOR_ALPHA = float(os.getenv("ROBOCUP_BALL_VECTOR_ALPHA", "0.45"))

OPPONENT_LABEL = os.getenv("ROBOCUP_OPPONENT_LABEL", "robot")
OPPONENT_AVOID_AREA = float(os.getenv("ROBOCUP_OPPONENT_AVOID_AREA", "220"))
OPPONENT_AVOID_BIAS_PX = int(os.getenv("ROBOCUP_OPPONENT_AVOID_BIAS_PX", "8"))

BALL_LOST_GRACE_SECONDS = float(os.getenv("ROBOCUP_LOST_GRACE", "0.6"))
BALL_LOST_VECTOR_CHASE_SECONDS = float(os.getenv("ROBOCUP_LOST_VECTOR_CHASE_SECONDS", "1.8"))
BALL_LOST_VECTOR_TURN_SPEED = int(os.getenv("ROBOCUP_LOST_VECTOR_TURN_SPEED", "78"))
BALL_LOST_VECTOR_TURN_MS = int(os.getenv("ROBOCUP_LOST_VECTOR_TURN_MS", "260"))
BALL_LOST_VECTOR_FORWARD_SPEED = int(os.getenv("ROBOCUP_LOST_VECTOR_FORWARD_SPEED", "170"))
BALL_LOST_VECTOR_FORWARD_MS = int(os.getenv("ROBOCUP_LOST_VECTOR_FORWARD_MS", "240"))
BALL_LOST_VECTOR_X_DEADBAND = int(os.getenv("ROBOCUP_LOST_VECTOR_X_DEADBAND", "10"))
SEARCH_TURN_SPEED = int(os.getenv("ROBOCUP_SEARCH_SPEED", "95"))
SEARCH_TURN_MS = int(os.getenv("ROBOCUP_SEARCH_MS", "440"))
SEARCH_SWEEP_SECONDS = float(os.getenv("ROBOCUP_SEARCH_SWEEP", "1.5"))
SEEK_TURN_DISTANCE_SCALE = float(os.getenv("ROBOCUP_SEEK_TURN_DISTANCE_SCALE", "2.0"))
SEARCH_RUNS_BEFORE_UTURN = int(os.getenv("ROBOCUP_SEARCH_RUNS_BEFORE_UTURN", "3"))
SEARCH_UTURN_SPEED = int(os.getenv("ROBOCUP_SEARCH_UTURN_SPEED", "120"))
SEARCH_UTURN_MS = int(os.getenv("ROBOCUP_SEARCH_UTURN_MS", "5000"))
SEARCH_WIDE_TURN_SPEED = int(os.getenv("ROBOCUP_SEARCH_WIDE_SPEED", "110"))
SEARCH_WIDE_TURN_MS = int(os.getenv("ROBOCUP_SEARCH_WIDE_MS", "340"))
SEARCH_FORWARD_SPEED = int(os.getenv("ROBOCUP_SEARCH_FORWARD_SPEED", "170"))
SEARCH_FORWARD_MS = int(os.getenv("ROBOCUP_SEARCH_FORWARD_MS", "260"))
SEARCH_FORWARD_INTERVAL_SECONDS = float(os.getenv("ROBOCUP_SEARCH_FORWARD_INTERVAL", "0.85"))
SEARCH_FORWARD_INTERVAL_TOP_SECONDS = float(os.getenv("ROBOCUP_SEARCH_FORWARD_INTERVAL_TOP", "0.55"))
SEARCH_FORWARD_INTERVAL_BOTTOM_SECONDS = float(os.getenv("ROBOCUP_SEARCH_FORWARD_INTERVAL_BOTTOM", "1.15"))

COMMAND_MIN_INTERVAL_SECONDS = float(os.getenv("ROBOCUP_COMMAND_MIN_INTERVAL", "0.05"))
FALLBACK_FRAME_WIDTH = int(os.getenv("ROBOCUP_FALLBACK_WIDTH", "96"))

NO_BALL_RECOVERY_SECONDS = float(os.getenv("ROBOCUP_NO_BALL_RECOVERY_SECONDS", "20"))
RECOVERY_ZIGZAG_SPEED = int(os.getenv("ROBOCUP_RECOVERY_ZIGZAG_SPEED", "255"))
RECOVERY_ZIGZAG_PHASE_SECONDS = float(os.getenv("ROBOCUP_RECOVERY_ZIGZAG_PHASE_SECONDS", "4.0"))

current_image = None
current_image_seq = 0
image_lock = threading.Lock()

preview_image = b""
preview_result = {}
preview_updated_at = 0

preview_job_lock = threading.Lock()
preview_job_frame = None
preview_job_result = None
preview_job_seq = -1
preview_job_event = threading.Event()
preview_stop = threading.Event()

camera_response = None
camera_stop = threading.Event()

runner = ImageImpulseRunner(str(MODEL_PATH))
robot = MiniAutoRobot()

_last_ball_seen_at = 0.0
_last_ball_center_x = None
_last_ball_quadrant = None
_last_command_at = 0.0
_last_detect_log_at = 0.0
_robot_mode = "idle"
_search_direction = 1
_last_search_switch_at = 0.0
_search_half_cycles = 0
_last_search_forward_at = 0.0
_last_preview_submit_at = 0.0
_last_preview_encoded_seq = -1
_recovery_mode_active = False
_recovery_phase_direction = -1
_recovery_phase_started_at = 0.0
_ball_center_x_ema = None
_ball_center_y_ema = None
_ball_area_ema = None
_commit_until = 0.0
_last_correction_at = 0.0
_last_ball_center_x_sample = None
_last_ball_center_y_sample = None
_last_ball_sample_at = 0.0
_ball_vx_ema = 0.0
_ball_vy_ema = 0.0
_motion_hold_until = 0.0


def resolve_web_assets_dir() -> Path | None:
    """Return a directory containing index.html for WebUI, if available."""
    candidates = [
        PROJECT_FOLDER / "assets",
        PROJECT_FOLDER,
    ]

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate

    return None


def _set_robot_mode(mode: str, message: str) -> None:
    global _robot_mode
    if _robot_mode != mode:
        print(message)
        _robot_mode = mode


def _drive_with_rate_limit(command: str, speed: int, ms: int, force: bool = False) -> None:
    global _last_command_at
    now = time.monotonic()
    if not force and now - _last_command_at < COMMAND_MIN_INTERVAL_SECONDS:
        return
    robot.drive(command, speed, ms)
    _last_command_at = now


def _seek_turn(command: str, speed: int, ms: int) -> None:
    """Turn farther during seek modes by scaling both speed and pulse duration."""
    scale = max(1.0, SEEK_TURN_DISTANCE_SCALE)
    scaled_speed = int(min(255, max(0, speed * scale)))
    scaled_ms = int(max(1, ms * scale))
    _drive_with_rate_limit(command, scaled_speed, scaled_ms)


def _drive_backward_diagonal(direction: int, speed: int, ms: int) -> None:
    """Drive diagonally backward; direction -1=back-left, +1=back-right."""
    s = max(0, min(255, int(speed)))

    if direction < 0:
        # back-left for mecanum: rear-right + front-left stop, opposite pair reverse
        robot.drive_raw(0, -s, -s, 0, int(ms))
    else:
        # back-right for mecanum
        robot.drive_raw(-s, 0, 0, -s, int(ms))


def _drive_spin_config4(direction: str, speed: int, ms: int) -> None:
    """Spin using the raw motor mix validated in spin_test config 4 (pattern d)."""
    global _last_command_at, _motion_hold_until

    s = max(0, min(255, int(speed)))
    if direction == "ccw":
        motors = (s, s, -s, -s)
    else:
        motors = (-s, -s, s, s)

    robot.drive_raw(motors[0], motors[1], motors[2], motors[3], int(ms))
    now = time.monotonic()
    _last_command_at = now
    _motion_hold_until = now + (max(1, int(ms)) / 1000.0)


def _start_recovery_phase(direction: int) -> None:
    global _last_command_at, _recovery_phase_direction, _recovery_phase_started_at

    phase_ms = int(RECOVERY_ZIGZAG_PHASE_SECONDS * 1000)
    _drive_backward_diagonal(direction, RECOVERY_ZIGZAG_SPEED, phase_ms)
    now = time.monotonic()
    _last_command_at = now
    _recovery_phase_direction = direction
    _recovery_phase_started_at = now


def _ema(previous: float | None, value: float, alpha: float) -> float:
    if previous is None:
        return value
    return (alpha * value) + ((1.0 - alpha) * previous)


def _safe_robot_probe(name: str, fn):
    """Run a robot probe without allowing startup to fail on unsupported bridge methods."""
    try:
        value = fn()
        print(f"[INFO] {name}={value}")
    except Exception as e:
        print(f"[WARN] {name} unavailable: {e}")


def make_model_executable(model_path: Path) -> None:
    if not os.path.exists(model_path):
        return
    os.chmod(
        model_path,
        os.stat(model_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
    )


def turn_frame_into_jpeg(frame: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    frame.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def camera_reader() -> None:
    global current_image, current_image_seq, camera_response

    while not camera_stop.is_set():
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
                            current_image_seq += 1
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


def start_camera() -> None:
    thread = threading.Thread(target=camera_reader, daemon=True)
    thread.start()


def stop_camera() -> None:
    camera_stop.set()
    if camera_response is not None:
        camera_response.close()


def copy_current_image():
    with image_lock:
        if current_image is None:
            return None, -1
        return current_image.copy(), current_image_seq


def update_browser_preview(frame: Image.Image, result: dict) -> None:
    global preview_image, preview_result, preview_updated_at
    with image_lock:
        preview_image = turn_frame_into_jpeg(frame, PREVIEW_JPEG_QUALITY)
        preview_result = result
        preview_updated_at = int(time.time() * 1000)


def request_preview_update(frame: Image.Image, result: dict, frame_seq: int) -> None:
    global _last_preview_submit_at

    now = time.monotonic()
    if now - _last_preview_submit_at < LOOP_DELAY_SECONDS:
        return
    _last_preview_submit_at = now

    with preview_job_lock:
        global preview_job_frame, preview_job_result, preview_job_seq
        preview_job_frame = frame
        preview_job_result = result
        preview_job_seq = frame_seq

    preview_job_event.set()


def preview_worker() -> None:
    global _last_preview_encoded_seq

    while not preview_stop.is_set():
        preview_job_event.wait(timeout=0.2)
        if preview_stop.is_set():
            break
        if not preview_job_event.is_set():
            continue

        with preview_job_lock:
            frame = preview_job_frame
            result = preview_job_result
            frame_seq = preview_job_seq
            preview_job_event.clear()

        if frame is None:
            continue
        if frame_seq == _last_preview_encoded_seq:
            continue

        update_browser_preview(frame, result)
        _last_preview_encoded_seq = frame_seq


def start_preview_worker() -> None:
    thread = threading.Thread(target=preview_worker, daemon=True)
    thread.start()


def stop_preview_worker() -> None:
    preview_stop.set()
    preview_job_event.set()


def get_preview_image() -> dict:
    with image_lock:
        image_bytes = preview_image
        result = preview_result

    if not image_bytes:
        return {"image": "", "status": "waiting for camera"}

    return {
        "image": base64.b64encode(image_bytes).decode("ascii"),
        "result": result,
    }


def draw_detections(frame: Image.Image, result: dict) -> Image.Image:
    image = frame.convert("RGB")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default()
    except Exception:
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

        color = (255, 200, 0) if label == BALL_LABEL else (0, 255, 80)
        text = f"{label} {score:.2f}"
        text_width = max(120, len(text) * 7)

        draw.rectangle([(x, y), (x + width, y + height)], outline=color, width=3)
        draw.rectangle([(x, max(0, y - 18)), (x + text_width, y)], fill=color)
        draw.text((x + 3, max(0, y - 16)), text, fill=(0, 0, 0), font=font)

    return image


def summarize_detections(result: dict) -> dict:
    boxes = result.get("result", {}).get("bounding_boxes", [])
    detections = []

    for box in boxes:
        score = float(box.get("value", 0))
        if score < MIN_SCORE:
            continue

        detections.append(
            {
                "label": box.get("label"),
                "score": score,
                "x": box.get("x"),
                "y": box.get("y"),
                "width": box.get("width"),
                "height": box.get("height"),
            }
        )

    return {"detections": detections, "timing": result.get("timing", {})}


def best_ball_detection(summary: dict):
    balls = [d for d in summary.get("detections", []) if d.get("label") == BALL_LABEL]
    if not balls:
        return None
    return max(balls, key=lambda d: float(d.get("score", 0)))


def best_detection_for_label(summary: dict, label: str):
    hits = [d for d in summary.get("detections", []) if d.get("label") == label]
    if not hits:
        return None
    return max(hits, key=lambda d: float(d.get("score", 0)))


def ball_quadrant(center_x: float, center_y: float, frame_width: int, frame_height: int) -> str:
    half_width = frame_width / 2
    half_height = frame_height / 2

    vertical = "top" if center_y < half_height else "bottom"
    horizontal = "left" if center_x < half_width else "right"
    return f"{vertical}_{horizontal}"


def react_to_detections(summary: dict) -> None:
    global _last_ball_seen_at, _last_ball_center_x, _search_direction, _last_search_switch_at
    global _last_search_forward_at, _search_half_cycles
    global _last_ball_quadrant
    global _recovery_mode_active, _recovery_phase_direction
    global _ball_center_x_ema, _ball_center_y_ema, _ball_area_ema
    global _commit_until, _last_correction_at
    global _last_ball_center_x_sample, _last_ball_center_y_sample, _last_ball_sample_at
    global _ball_vx_ema, _ball_vy_ema
    global _motion_hold_until

    now = time.monotonic()

    # Keep an active timed motion (e.g., 180 spin) from being interrupted by new commands.
    if now < _motion_hold_until:
        _set_robot_mode("uturn", "[ROBOT] search cycles complete - 180 turn")
        return

    frame_width = int(summary.get("frame_width", FALLBACK_FRAME_WIDTH))
    frame_height = int(summary.get("frame_height", FALLBACK_FRAME_WIDTH))
    half_width = frame_width / 2

    ball = best_ball_detection(summary)
    opponent = best_detection_for_label(summary, OPPONENT_LABEL)

    # Ball-visible behavior is fully vision-driven.
    if ball is not None:
        _recovery_mode_active = False

        center_x = int(ball.get("x", 0)) + (int(ball.get("width", 0)) / 2)
        center_y = int(ball.get("y", 0)) + (int(ball.get("height", 0)) / 2)
        ball_area = float(int(ball.get("width", 0)) * int(ball.get("height", 0)))

        _ball_center_x_ema = _ema(_ball_center_x_ema, center_x, BALL_EMA_ALPHA)
        _ball_center_y_ema = _ema(_ball_center_y_ema, center_y, BALL_EMA_ALPHA)
        _ball_area_ema = _ema(_ball_area_ema, ball_area, BALL_EMA_ALPHA)

        center_x_s = _ball_center_x_ema
        center_y_s = _ball_center_y_ema
        ball_area_s = _ball_area_ema

        _last_ball_seen_at = now
        _last_ball_center_x = center_x_s
        _last_ball_quadrant = ball_quadrant(center_x_s, center_y_s, frame_width, frame_height)

        # Track last observed image-space motion vector for short-term pursuit when ball is lost.
        if _last_ball_sample_at > 0:
            dt = max(1e-3, now - _last_ball_sample_at)
            raw_vx = (center_x_s - _last_ball_center_x_sample) / dt
            raw_vy = (center_y_s - _last_ball_center_y_sample) / dt
            _ball_vx_ema = _ema(_ball_vx_ema, raw_vx, BALL_VECTOR_ALPHA)
            _ball_vy_ema = _ema(_ball_vy_ema, raw_vy, BALL_VECTOR_ALPHA)
        _last_ball_center_x_sample = center_x_s
        _last_ball_center_y_sample = center_y_s
        _last_ball_sample_at = now

        if ball_area_s < BALL_AREA_FAR:
            forward_speed = BALL_CHARGE_SPEED_FAR
        elif ball_area_s < BALL_AREA_NEAR:
            forward_speed = BALL_CHARGE_SPEED_MID
        else:
            forward_speed = BALL_CHARGE_SPEED_NEAR

        x_error = center_x_s - (half_width + BALL_CENTER_BIAS_PX)

        if opponent is not None:
            opp_center_x = int(opponent.get("x", 0)) + (int(opponent.get("width", 0)) / 2)
            opp_area = float(int(opponent.get("width", 0)) * int(opponent.get("height", 0)))
            if opp_area >= OPPONENT_AVOID_AREA:
                if opp_center_x >= half_width:
                    x_error -= OPPONENT_AVOID_BIAS_PX
                else:
                    x_error += OPPONENT_AVOID_BIAS_PX

        # Commit shot: when ball is close and centered, ignore minor jitter and drive through.
        if now < _commit_until and ball_area_s >= BALL_AREA_NEAR:
            _drive_with_rate_limit("forward", BALL_COMMIT_SPEED, BALL_COMMIT_MS)
            _set_robot_mode("commit", "[ROBOT] ball detected - commit drive")
            return

        # Center first with short, gentle corrections; otherwise barrel forward.
        if abs(x_error) > BALL_ALIGN_DEADBAND and (now - _last_correction_at) >= BALL_CORRECTION_COOLDOWN_SECONDS:
            if x_error < 0:
                _drive_with_rate_limit("left", BALL_ALIGN_TURN_SPEED, BALL_ALIGN_TURN_MS)
            else:
                _drive_with_rate_limit("right", BALL_ALIGN_TURN_SPEED, BALL_ALIGN_TURN_MS)
            _last_correction_at = now
            _set_robot_mode("align", "[ROBOT] ball detected - aligning")
        else:
            if ball_area_s >= BALL_AREA_CONTACT and abs(x_error) <= BALL_ALIGN_DEADBAND:
                _commit_until = now + BALL_COMMIT_SECONDS
                _drive_with_rate_limit("forward", BALL_COMMIT_SPEED, BALL_COMMIT_MS)
                _set_robot_mode("commit", "[ROBOT] ball detected - commit drive")
            else:
                _drive_with_rate_limit("forward", forward_speed, BALL_CHARGE_MS)
                _set_robot_mode("chasing", "[ROBOT] ball detected - charging")
        return

    if _last_ball_seen_at > 0 and (now - _last_ball_seen_at) >= NO_BALL_RECOVERY_SECONDS:
        if not _recovery_mode_active:
            _recovery_mode_active = True

            if _last_ball_quadrant in ("top_left", "bottom_left"):
                start_direction = -1
            elif _last_ball_quadrant in ("top_right", "bottom_right"):
                start_direction = 1
            else:
                start_direction = _search_direction

            _start_recovery_phase(start_direction)
            _set_robot_mode("recover", "[ROBOT] ball missing 20s - zigzag back recovery")
            return

        if (now - _recovery_phase_started_at) >= RECOVERY_ZIGZAG_PHASE_SECONDS:
            _start_recovery_phase(-_recovery_phase_direction)

        _set_robot_mode("recover", "[ROBOT] ball missing 20s - zigzag back recovery")
        return

    if (now - _last_ball_seen_at) <= BALL_LOST_GRACE_SECONDS:
        # Keep momentum briefly instead of immediately strafing.
        _drive_with_rate_limit("forward", BALL_DRIVE_SPEED, BALL_DRIVE_MS)

        _set_robot_mode("grace", "[ROBOT] ball briefly lost - forward hold")
        return

    if _last_ball_seen_at > 0 and (now - _last_ball_seen_at) <= BALL_LOST_VECTOR_CHASE_SECONDS:
        lost_dt = now - _last_ball_seen_at
        predicted_x = _last_ball_center_x + (_ball_vx_ema * lost_dt)
        x_error_pred = predicted_x - (half_width + BALL_CENTER_BIAS_PX)

        if abs(x_error_pred) <= BALL_LOST_VECTOR_X_DEADBAND:
            _drive_with_rate_limit("forward", BALL_LOST_VECTOR_FORWARD_SPEED, BALL_LOST_VECTOR_FORWARD_MS)
        elif x_error_pred < 0:
            _seek_turn("left", BALL_LOST_VECTOR_TURN_SPEED, BALL_LOST_VECTOR_TURN_MS)
        else:
            _seek_turn("right", BALL_LOST_VECTOR_TURN_SPEED, BALL_LOST_VECTOR_TURN_MS)

        _set_robot_mode("vector", "[ROBOT] ball lost - vector pursuit")
        return

    if _robot_mode != "search":
        if _last_ball_quadrant in ("top_left", "bottom_left"):
            _search_direction = -1
        elif _last_ball_quadrant in ("top_right", "bottom_right"):
            _search_direction = 1
        elif _last_ball_center_x is not None and _last_ball_center_x < half_width:
            _search_direction = -1
        else:
            _search_direction = 1
        _last_search_switch_at = now
        _search_half_cycles = 0
    elif now - _last_search_switch_at >= SEARCH_SWEEP_SECONDS:
        _search_direction *= -1
        _last_search_switch_at = now
        _search_half_cycles += 1

        # One complete run is a left-right pair (two half-cycles).
        if _search_half_cycles >= (SEARCH_RUNS_BEFORE_UTURN * 2):
            _drive_spin_config4("cw", SEARCH_UTURN_SPEED, SEARCH_UTURN_MS)
            _search_half_cycles = 0
            _search_direction *= -1
            _set_robot_mode("uturn", "[ROBOT] search cycles complete - 180 turn")
            return

    # Once missing longer, recover with gentle sweep (toned down strafing).
    if _search_direction < 0:
        _seek_turn("left", SEARCH_TURN_SPEED, SEARCH_TURN_MS)
    else:
        _seek_turn("right", SEARCH_TURN_SPEED, SEARCH_TURN_MS)

    _set_robot_mode("search", "[ROBOT] ball lost - searching")


def run_inference(frame: Image.Image):
    global _last_detect_log_at

    image = np.asarray(frame.convert("RGB"))
    features, cropped = runner.get_features_from_image_auto_studio_settings(image)
    result = runner.classify(features)

    display_image = Image.fromarray(cropped.astype(np.uint8)).convert("RGB")
    display_image = draw_detections(display_image, result)

    summary = summarize_detections(result)
    summary["frame_width"] = int(display_image.width)
    summary["frame_height"] = int(display_image.height)

    now = time.monotonic()
    if summary["detections"] and (now - _last_detect_log_at) >= DETECT_LOG_INTERVAL_SECONDS:
        print(f"[DETECT] {summary['detections']}")
        _last_detect_log_at = now

    return display_image, summary


def loop() -> None:
    frame, frame_seq = copy_current_image()

    if frame is None:
        time.sleep(LOOP_DELAY_SECONDS)
        return

    try:
        display_image, summary = run_inference(frame)
    except Exception as e:
        print(f"[WARN] inference failed: {e}")
        display_image = frame
        summary = {"error": str(e)}

    react_to_detections(summary)
    request_preview_update(display_image, summary, frame_seq)
    time.sleep(LOOP_DELAY_SECONDS)


print(f"[INFO] model: {MODEL_PATH}")
print(f"[INFO] camera: {CAMERA_URL}")
print(f"[INFO] ball label: {BALL_LABEL}")
_safe_robot_probe("health", robot.health)
_safe_robot_probe("sensors", robot.read_sensors)

make_model_executable(MODEL_PATH)

assets_dir = resolve_web_assets_dir()
ui = None

if assets_dir is not None:
    print(f"[INFO] WebUI assets: {assets_dir}")
    ui = WebUI(assets_dir_path=assets_dir)
    ui.expose_api("GET", "/preview", get_preview_image)
else:
    print("[WARN] WebUI disabled: index.html not found in project assets locations")

try:
    model_info = runner.init()
    print(f"[INFO] loaded Edge Impulse model: {model_info['project']['name']}")

    start_camera()
    start_preview_worker()
    App.run(user_loop=loop)

finally:
    try:
        robot.stop()
    except Exception as e:
        print(f"[WARN] stop failed: {e}")
    stop_preview_worker()
    stop_camera()
    runner.stop()
