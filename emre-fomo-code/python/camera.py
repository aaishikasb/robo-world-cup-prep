import base64
import io
import os
import shutil
import socket
import subprocess
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
CAMERA_WIFI_PREFIX = os.getenv("ROBOCUP_CAMERA_WIFI_PREFIX", "miniAuto_CAM_")
CAMERA_WIFI_AUTO_CONNECT = os.getenv(
    "ROBOCUP_CAMERA_WIFI_AUTO_CONNECT", "1"
).strip().lower() not in {"0", "false", "no", "off"}
CAMERA_WIFI_HELPER_SOCKET = os.getenv(
    "ROBOCUP_CAMERA_WIFI_HELPER_SOCKET", "/app/.camera_wifi.sock"
)

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

_NMCLI = shutil.which("nmcli")
if _NMCLI is None and Path("/usr/bin/nmcli").is_file():
    _NMCLI = "/usr/bin/nmcli"


def _run_nmcli(*args: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    if _NMCLI is None:
        raise FileNotFoundError("nmcli was not found in PATH or at /usr/bin/nmcli")
    result = subprocess.run(
        [_NMCLI, *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )
    command = " ".join(args)
    stdout = result.stdout.strip().replace("\n", " | ")
    stderr = result.stderr.strip().replace("\n", " | ")
    print(
        f"[WIFI DEBUG] nmcli {command!s} -> rc={result.returncode}"
        f" stdout={stdout!r} stderr={stderr!r}"
    )
    return result


def _request_host_wifi_switch() -> bool:
    """Ask the UNO Q host helper to switch Wi-Fi from the App Lab container."""
    print(f"[WIFI DEBUG] requesting host switch via {CAMERA_WIFI_HELPER_SOCKET}")
    last_error: Exception | None = None
    for attempt in range(1, 21):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(25)
                client.connect(CAMERA_WIFI_HELPER_SOCKET)
                client.sendall((CAMERA_WIFI_PREFIX + "\n").encode("utf-8"))
                response = client.recv(4096).decode("utf-8", errors="replace").strip()
            break
        except (OSError, TimeoutError) as e:
            last_error = e
            if attempt < 20:
                time.sleep(0.5)
    else:
        print(f"[WARN] camera Wi-Fi host helper unavailable after 10 s: {last_error}")
        return False

    if response.startswith("OK "):
        print(f"[INFO] host switched to camera Wi-Fi: {response[3:]}")
        return True
    print(f"[WARN] camera Wi-Fi host helper failed: {response or 'empty response'}")
    return False


def _switch_to_camera_wifi() -> bool:
    """Activate the most recently used saved miniAuto camera Wi-Fi profile."""
    print(
        f"[WIFI DEBUG] auto_connect={CAMERA_WIFI_AUTO_CONNECT} "
        f"prefix={CAMERA_WIFI_PREFIX!r} nmcli={_NMCLI!r} "
        f"uid={os.geteuid() if hasattr(os, 'geteuid') else 'unknown'}"
    )
    if not CAMERA_WIFI_AUTO_CONNECT:
        print("[INFO] camera Wi-Fi auto-connect disabled")
        return False
    if not CAMERA_WIFI_PREFIX:
        print("[WARN] camera Wi-Fi prefix is empty")
        return False
    if _NMCLI is None:
        return _request_host_wifi_switch()

    try:
        active = _run_nmcli("-t", "-f", "ACTIVE,SSID", "device", "wifi")
        if active.returncode == 0:
            for line in active.stdout.splitlines():
                is_active, _, ssid = line.partition(":")
                if is_active == "yes" and ssid.startswith(CAMERA_WIFI_PREFIX):
                    print(f"[INFO] already connected to camera Wi-Fi: {ssid}")
                    return True

        profiles = _run_nmcli(
            "-t", "--escape", "no", "-f", "UUID,TYPE,TIMESTAMP", "connection", "show"
        )
        if profiles.returncode != 0:
            print(f"[WARN] could not list saved Wi-Fi profiles: {profiles.stderr.strip()}")
            return False

        candidates: list[tuple[int, str, str]] = []
        for line in profiles.stdout.splitlines():
            try:
                uuid, connection_type, timestamp_text = line.rsplit(":", 2)
                timestamp = int(timestamp_text or 0)
            except ValueError:
                continue
            if connection_type not in {"802-11-wireless", "wifi"}:
                continue

            ssid_result = _run_nmcli(
                "-g", "802-11-wireless.ssid", "connection", "show", "uuid", uuid
            )
            ssid = ssid_result.stdout.strip()
            if ssid_result.returncode == 0 and ssid.startswith(CAMERA_WIFI_PREFIX):
                print(
                    f"[WIFI DEBUG] saved camera profile: "
                    f"ssid={ssid!r} uuid={uuid} timestamp={timestamp}"
                )
                candidates.append((timestamp, uuid, ssid))

        if not candidates:
            print(f"[WARN] no saved camera Wi-Fi matching {CAMERA_WIFI_PREFIX}* was found")
            return False

        _, uuid, ssid = max(candidates)
        print(f"[INFO] switching Wi-Fi to camera: {ssid}")
        connected = _run_nmcli("--wait", "15", "connection", "up", "uuid", uuid, timeout=20)
        if connected.returncode != 0:
            detail = connected.stderr.strip() or connected.stdout.strip()
            print(f"[WARN] could not connect to camera Wi-Fi {ssid}: {detail}")
            return False

        print(f"[INFO] connected to camera Wi-Fi: {ssid}")
        _run_nmcli("-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device", "show")
        return True
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[WARN] camera Wi-Fi auto-connect failed: {e}")
        return False


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
    _switch_to_camera_wifi()
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
