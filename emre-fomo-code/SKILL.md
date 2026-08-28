---
name: uno-q-miniauto-fomo
description: Create and adapt Hiwonder miniAuto robots on Arduino UNO Q, with working camera stream, HSV wall detection, Edge Impulse FOMO model inference, and start/stop button control already in place. Use when extending soccer behavior, integrating a new or updated .eim model, tuning wall detection, adding sensor-driven policies, modifying the Bridge API, or validating related UNO Q changes. Do not use for unrelated robots or generic Arduino projects.
---

# Extend the UNO Q miniAuto

This repository already includes working camera streaming, HSV wall tape detection, Edge Impulse model inference, and start/stop button control. Extend the existing code rather than building a second stack. Preserve safety behavior and the firmware-to-Python contract while changing only the layer the request requires.

## What is already built

| Module | What it provides |
| --- | --- |
| `sketch/sketch.ino` | Motor control, mecanum mixing, Bridge RPC, sensors, buzzer, servo, LEDs, CAM button toggle, start/stop program enable |
| `python/robot_client.py` | `MiniAutoRobot` wrapper: `drive`, `stop`, `read_sensors`, `servo`, `buzz`, `led`, `drive_raw`, `health`, `is_running`, `hold_toggle`, `run_program` |
| `python/camera.py` | Background MJPEG reader thread, `_copy_frame()`, `_detect_wall()`, `_run_inference()`, web preview API, auto `.eim` discovery |
| `python/wall_detector.py` | `WallDetector`: HSV red/blue tape classifier, `detect()`, `detect_with_coverage()`, `coverage()` |
| `python/main.py` | Example loop: start button, team toggle, motion sequence, wall detection, sensor read, servo/LED |
| `python/requirements.txt` | `numpy`, `pillow`, `requests`, `edge-impulse-linux`, `ai-edge-litert` |

## Start here

1. Find the repository root with `git rev-parse --show-toplevel` and work from it.
2. Read [references/architecture.md](references/architecture.md) completely before editing. Treat the checked-out source as authoritative if it differs.
3. Inspect `git status --short`. Preserve user changes; avoid unrelated rewrites.
4. Translate the request into observable behavior, inputs, outputs, timing, and a safe stop condition. Ask only for a choice that would materially change the design and cannot be inferred from the repository.
5. Run the baseline contract check:

   ```bash
   python3 -m py_compile python/*.py
   python3 .agents/skills/uno-q-miniauto/scripts/check_robot_contract.py --strict
   ```

## Choose the customization layer

| Requested change | Primary files | Also change |
| --- | --- | --- |
| Soccer strategy, sensor-driven behavior, or any Python-only policy | `python/main.py` or a focused new module under `python/` | `python/robot_client.py` only if the existing API is insufficient |
| Edge Impulse model integration or inference policy | `python/camera.py` (`_run_inference`) and `python/main.py` | Model file placed in `python/`; update README model-placement note |
| Wall detection tuning (HSV ranges, threshold, logic) | `python/wall_detector.py` | `python/camera.py` if the call signature changes; README HSV table |
| Camera URL, warmup, frame format, preview API | `python/camera.py` | README camera endpoint docs |
| New actuator, sensor, safety rule, or MCU capability | `sketch/sketch.ino` | `python/robot_client.py` and application when exposed through Bridge |
| Bridge API addition or signature change | `sketch/sketch.ino` and `python/robot_client.py` | Call sites, payload docs, and validation |
| Camera AP, stream, button, or GC2145 behavior | `camera/HiwonderCamStream/HiwonderCamStream.ino` | Consumer config or docs that depend on URL/protocol |
| App identity or Arduino dependency | `app.yaml` or `sketch/sketch.yaml` | README only when setup or public behavior changes |
| Physical assembly or wiring guidance | `docs/MANUAL.md` | Firmware pin mapping if actual wiring changes |

Prefer Python-only for high-level behavior. Change firmware only when the hardware interface, real-time control, or safety boundary requires it. Keep camera firmware independent unless the feature explicitly couples it to the UNO Q.

## Sensor payload fields (current)

```json
{
  "robot": "hiwonder_miniauto",
  "mcu": "uno_q",
  "ir": -1,
  "line_ok": true,
  "line_digital": [0, 1, 1, 0],
  "trace_digital": [0, 1, 1, 0],
  "ultrasonic_mm": 250,
  "ultrasonic_cm": 25,
  "battery_mv": 7400,
  "program_enabled": true,
  "hold_toggle": false
}
```

- `program_enabled`: `true` while the start button is active; used by `_require_running()`.
- `hold_toggle`: `false` = RED team, `true` = BLUE team. Changed by holding the CAM button 5 seconds.

## Edge Impulse integration pattern

```python
# In main.py or a focused module:
from camera import _copy_frame, _run_inference, _start_camera

_start_camera()

frame = _copy_frame()
if frame is not None:
    detections = _run_inference(frame)
    # detections: list of {"label": str, "value": float, "x", "y", "width", "height"}
    balls = [d for d in detections if d["label"] == "soccerball" and d["value"] >= 0.6]
    if balls:
        # e.g. steer toward the closest ball
        pass
```

- Drop the `.eim` (Linux aarch64) into `python/`. `camera.py` discovers it automatically.
- `_run_inference` returns `[]` if no model is loaded or `edge_impulse_linux` is not installed.
- Always define safe behavior for empty detection lists and stale frames (`_copy_frame()` returning `None`).

## Wall detection pattern

```python
from camera import _copy_frame, _detect_wall

frame = _copy_frame()
if frame is not None:
    side, coverage = _detect_wall(frame)
    # side: "RED", "BLUE", or "UNKNOWN"
    # coverage: {"red": 0.052, "blue": 0.003, "total_pixels": 76800}
    print(f"[FIELD] wall={side}  red={coverage['red']:.1%}  blue={coverage['blue']:.1%}")
```

## Start/stop and team toggle pattern

```python
from robot_client import MiniAutoRobot
from arduino.app_utils import App

robot = MiniAutoRobot()

def loop():
    team = "BLUE" if robot.hold_toggle() else "RED"
    # ... behavior ...
    robot.stop()

App.run(user_loop=lambda: robot.run_program(loop))
```

- `run_program` runs `loop()` once per start-button press, waits for the next press, and always stops in `finally`.
- `hold_toggle()` returns the 5-second CAM button hold state; use it to pick team color or side assignment.

## Implement safely

- Preserve `robot.stop()` cleanup and the firmware's timed auto-stop behavior.
- Keep motor, servo, duration, and sensor inputs bounded at the firmware boundary.
- Keep long-running policy and inference work on the Python side. Keep direct I/O, motor mixing, and fail-safe timing on the MCU side.
- Reuse `MiniAutoRobot` rather than scattering raw `Bridge.call(...)` calls through application code.
- For a new Bridge operation, update all four contract points in one change: MCU implementation, `Bridge.provide_safe(...)` registration, typed `MiniAutoRobot` wrapper, and call site or documented payload.
- Make routines interruptible through the existing program-enabled flow.
- Keep the current health and sensor fields backward compatible. Add fields; do not silently rename or change units.
- Never embed `.eim` binaries or generated inference artifacts in the driver repository; `.gitignore` excludes common model formats.
- Never run commands that move motors, actuate the servo, flash boards, or alter a live robot unless the user has explicitly requested hardware execution and confirmed a safe physical setup.

## Validate in stages

```bash
python3 -m py_compile python/*.py
python3 .agents/skills/uno-q-miniauto/scripts/check_robot_contract.py --strict
```

Then:

1. Compile the UNO Q sketch with the repository's `arduino:zephyr` profile when that toolchain is available.
2. Compile the ESP32-S3 camera sketch only when camera code changed and its board libraries are available.
3. If hardware testing is authorized, start with wheels raised, low speed, short timed pulses, and a reachable stop control.
4. Test one motor or actuator at a time before combined motion.
5. Verify `health()`, `read_sensors()`, `hold_toggle()`, program enable/disable, interruption, and final stop before testing autonomous logic.
6. For camera and model features, confirm `_copy_frame()` returns a valid frame before enabling inference-driven motion.

Do not claim a hardware result from static checks or compilation alone. Report which layers changed, which checks passed, and which physical behaviors remain unverified.

## Keep the handoff usable

Update `README.md` when public APIs, setup, environment variables, commands, payloads, camera endpoints, or model placement conventions change. Keep `docs/MANUAL.md` focused on physical assembly and battery safety. Finish with a small usage example for the new variant and explicit first-run safety instructions.
