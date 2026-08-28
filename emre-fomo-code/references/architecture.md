# UNO Q miniAuto architecture

Read this reference before modifying the robot. Re-check the live files because the repository may evolve after this reference was written.

## System boundaries

- `sketch/sketch.ino`: Arduino UNO Q MCU firmware. Owns direct hardware I/O, mecanum mixing, command parsing, motor timeouts, start/stop state, sensors, servo, buzzer, LEDs, and Router Bridge RPC providers.
- `python/robot_client.py`: Linux-side typed facade. Owns Bridge serialization, program-running guards, routine interruption, and caller-friendly return values. Also exposes `hold_toggle()` (reads the CAM button 5-second hold state for team selection).
- `python/camera.py`: Camera thread, MJPEG frame parser, WallDetector integration, Edge Impulse runner wrapper, and web preview API. Runs a background daemon thread; main.py calls `_start_camera()` once at startup and reads frames with `_copy_frame()`.
- `python/wall_detector.py`: Stateless HSV-based wall tape colour classifier. Accepts a BGR numpy frame, returns `("RED"|"BLUE"|"UNKNOWN", coverage_dict)`. No VideoCapture dependency.
- `python/main.py`: Example App Lab behavior. Demonstrates start/stop button control, team toggle, camera wall detection, sensors, motion, servo, and LED. Use as a starting point for custom soccer policies.
- `python/requirements.txt`: Python package dependencies: `numpy`, `pillow`, `requests`, `opencv-python` (cv2), `edge-impulse-linux`, `ai-edge-litert`.
- `sketch/sketch.yaml`: UNO Q `arduino:zephyr` platform and `Arduino_RouterBridge` dependency.
- `app.yaml`: App Lab application metadata.
- `camera/HiwonderCamStream/HiwonderCamStream.ino`: Independent Hiwonder ESP32-S3 GC2145 camera firmware. Hosts an MJPEG stream and exposes its button state to the UNO Q over I2C `0x79`.
- `README.md`: Software setup, API, payload, protocol, camera, wall detection, Edge Impulse model import, and troubleshooting.
- `docs/MANUAL.md`: Physical assembly, wiring illustrations, charging, battery, and handling guidance.
- `miniAutoDriver.zip`: Distribution snapshot, not the editable source of truth. Modify the unpacked repository files unless the user explicitly asks to rebuild the archive.

## Current hardware map

| Device | UNO Q pin or bus address |
| --- | --- |
| Motor PWM M0..M3 | D10, D9, D6, D11 |
| Motor direction M0..M3 | D12, D8, D7, D13 |
| Onboard WS2812 RGB | D2 |
| Passive buzzer | D3 |
| Servo/gripper | D5 |
| Battery divider | A3 |
| Glowing ultrasonic sensor | I2C `0x77` |
| Four-channel line sensor | I2C `0x78` |
| Camera/button controller | I2C `0x79` |

Do not assume a different miniAuto revision shares this map. When hardware differs, require a pin/address table or a verified wiring diagram and retain a safe stop path while remapping.

## Current Bridge contract

The sketch registers these providers with `Bridge.provide_safe(...)` and `MiniAutoRobot` wraps them:

- `drive(command, speed, duration_ms)`
- `stop()`
- `read_sensors()` returning JSON
- `servo(angle)`
- `buzz()`
- `led(on)`
- `drive_raw(m0, m1, m2, m3, duration_ms)`
- `health()` returning JSON

`MiniAutoRobot.drive`, `servo`, and `drive_raw` are guarded by `_require_running()`. Timed `drive` waits for completion and checks again so the CAM button can interrupt a routine. Keep this behavior for user-facing motion APIs.

The sensor JSON currently includes: `robot`, `mcu`, `ir` (reserved, always `-1`), `line_ok`, `line_digital` (4 bits), `trace_digital` (same 4 bits, for compat), `ultrasonic_mm`, `ultrasonic_cm`, `battery_mv`, `program_enabled`, and `hold_toggle` (team color state from 5-second CAM button hold). Inspect `readSensorsJson()` in `sketch/sketch.ino` for the live field names and types.

## Python module details

### `MiniAutoRobot` (`python/robot_client.py`)

Key methods beyond the Bridge wrappers:
- `is_running()` — polls `program_enabled` from sensor JSON.
- `hold_toggle()` — reads `hold_toggle` from sensor JSON; `False` = RED team, `True` = BLUE team.
- `run_program(routine)` — use as `App.run(user_loop=lambda: robot.run_program(loop))`. Fires `routine()` exactly once per start-button press; waits idly for the next press; catches `ProgramStopped`; always calls `robot.stop()` in `finally`.

### `camera.py`

- `_start_camera()` — starts the background MJPEG reader thread. Call once at startup.
- `_copy_frame()` — returns a copy of the latest `PIL.Image.Image` frame (or `None` if none received yet).
- `_detect_wall(pil_frame)` — converts to BGR and calls `WallDetector.detect_with_coverage()`. Returns `(side_str, coverage_dict)`.
- `_run_inference(pil_frame)` — runs Edge Impulse classification if `runner` is initialized. Returns a list of bounding-box dicts with keys `label`, `value`, `x`, `y`, `width`, `height`. Returns `[]` when the model is unavailable.
- `get_preview_image()` — returns `{"image": base64_jpeg, "result": {...}}` for the web UI.
- `CAMERA_URL` — read from `ROBOCUP_CAMERA_URL` env var; defaults to `http://192.168.5.1:81/stream`.
- `MODEL_PATH` — auto-discovered: the first `*.eim` file found in the same directory as `camera.py`.

### `WallDetector` (`python/wall_detector.py`)

- `detect(frame_bgr)` — returns `"RED"`, `"BLUE"`, or `"UNKNOWN"`.
- `detect_with_coverage(frame_bgr)` — returns `(side, {"red": float, "blue": float, "total_pixels": int})`.
- `coverage(frame_bgr)` — returns the coverage dict alone.
- Default `min_coverage` is `0.02` (2% of frame pixels).
- HSV ranges: Red uses two bands (hue 0–10 and 160–179), Blue uses hue 100–130; both require saturation ≥ 120 and value ≥ 70.

### Edge Impulse runner (`camera.py`)

- Requires `edge-impulse-linux` and `ai-edge-litert` packages (see `requirements.txt`).
- Place the exported `.eim` file (Linux aarch64) inside `python/`. The runner is auto-initialized when a `.eim` is found.
- `_run_inference` resizes the frame to the model's expected input using `get_features_from_image_auto_studio_settings`, classifies, and filters boxes with confidence ≥ `0.55`.
- If `edge_impulse_linux` is not installed, the import is silently skipped and `_run_inference` returns `[]`.

## Extension patterns

### Add high-level robot behavior

1. Read state through `MiniAutoRobot` and `_copy_frame()` / `_detect_wall()` / `_run_inference()`.
2. Make a bounded decision in Python.
3. Issue short timed actions rather than unbounded motion where possible.
4. Stop on completion, exception, disabled program state, invalid sensor data, or loss of the expected condition.
5. Keep the `App.run(user_loop=...)` callback responsive; split large behavior into testable functions or modules.

### Integrate an Edge Impulse model

1. Export the `.eim` for Linux aarch64 from Edge Impulse Studio.
2. Place it in `python/`. `camera.py` auto-discovers the first `*.eim` in that directory.
3. Call `_run_inference(frame)` where `frame` is a `PIL.Image` from `_copy_frame()`.
4. Filter detections by `value` (confidence) and `label`. Map labels to robot actions.
5. Define safe behavior for empty detection lists, stale frames, and model load failure.
6. Never hard-code the model path; rely on the glob auto-discovery or `MODEL_PATH`.

### Add a sensor or actuator

1. Define pins, addresses, units, ranges, and failure values near the existing hardware constants in `sketch.ino`.
2. Search the entire sketch for every use of a proposed pin before assigning it.
3. Implement bounded MCU access and a safe failure mode. Integrate actuator shutdown with stop, program disable, startup, timeout, and sensor-loss paths.
4. Add data to `readSensorsJson()` or create a focused RPC; register with `Bridge.provide_safe(...)`.
5. Wrap in `MiniAutoRobot`; use precise types and units.
6. Add a call-site example and update the README contract.

### Add or change motion

1. Confirm physical wheel order, polarity, and mecanum orientation before changing mixing math.
2. Preserve per-channel clamping and the timer-driven stop.
3. Add a named command to `driveCommand(...)` for stable public motions; use `drive_raw` only for diagnostics or carefully bounded experiments.
4. Update accepted aliases and README tables.
5. Test individual channels, then translation, then rotation, then combined motion.

### Add vision or an ML model

1. Keep camera capture/stream transport separate from the movement fail-safe.
2. Put inference and policy code on the Linux/Python side.
3. Make camera endpoint, confidence threshold, labels, and team selection configurable.
4. Define behavior for stale frames, no detections, ambiguous detections, and unavailable models; the safe default is stop.
5. Keep model artifacts (`.eim`) outside this repository or in `.gitignore`; document how the user supplies them at runtime.

## Static inspection shortcuts

```bash
rg -n 'Bridge\.provide_safe|Bridge\.call' sketch/sketch.ino python
rg -n 'MOTOR_|PIN_|I2C_ADDR|MAX_DRIVE_MS|DEFAULT_' sketch/sketch.ino
rg -n 'CAMERA_SSID|CAMERA_PASS|AP_IP|STREAM_PORT|GPIO|I2C' camera/HiwonderCamStream/HiwonderCamStream.ino
rg -n 'program_enabled|hold_toggle|_require_running|run_program' python/robot_client.py python/main.py
rg -n '_start_camera|_copy_frame|_detect_wall|_run_inference|MODEL_PATH' python/camera.py
rg -n '^#{1,4} ' README.md docs/MANUAL.md
```

Use the bundled checker after any firmware, wrapper, or configuration change:

```bash
python3 -m py_compile python/*.py
python3 .agents/skills/uno-q-miniauto/scripts/check_robot_contract.py --strict
```

It statically checks that the baseline RPCs remain present, Python calls have firmware providers, the Python files parse, and the UNO Q profile still declares the required platform and Bridge library.
