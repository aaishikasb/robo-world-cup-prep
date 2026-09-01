# Robot Soccer Cup — miniAuto FOMO Edition

This repository contains the complete hardware-control software for the Hiwonder miniAuto robot used in the Robot Soccer Cup hosted by the Qualcomm Developer Relations Team.

Camera streaming, HSV wall-tape detection, Edge Impulse FOMO model inference, and start/stop button control are **already integrated**. You can run the example out of the box and build soccer logic on top of the working foundation.

For questions or concerns, please create GitHub Issues.

## Contents

- [Robot Soccer Cup — miniAuto FOMO Edition](#robot-soccer-cup--miniauto-fomo-edition)
  - [Contents](#contents)
  - [System overview](#system-overview)
  - [Repository layout](#repository-layout)
  - [Quick start](#quick-start)
  - [Python driver API](#python-driver-api)
  - [Camera and inference API](#camera-and-inference-api)
  - [Wall / Field-Side Detection](#wall--field-side-detection)
  - [Edge Impulse FOMO integration](#edge-impulse-fomo-integration)
  - [Start/stop button and team toggle](#startstop-button-and-team-toggle)
  - [Sensor and health payloads](#sensor-and-health-payloads)
  - [Hardware map](#hardware-map)
  - [Environment variables](#environment-variables)
  - [UNO Q robot setup](#uno-q-robot-setup)
    - [Path A — Arduino App Lab](#path-a--arduino-app-lab)
    - [Path B — SSH from your laptop](#path-b--ssh-from-your-laptop-no-app-lab-needed)
    - [Path C — USB-C / ADB](#path-c--usb-c--adb)
  - [Serial command reference](#serial-command-reference)
  - [Hiwonder protocol compatibility](#hiwonder-protocol-compatibility)
  - [Camera setup and flashing](#camera-setup-and-flashing)
  - [Building your Edge Impulse model](#building-your-edge-impulse-model)
  - [Safety and troubleshooting](#safety-and-troubleshooting)

---

## System overview

The project has two independently flashed controllers and a Linux application layer:

1. **Arduino UNO Q** runs `sketch/sketch.ino`. Controls motors, mecanum drive, RGB lights, buzzer, servo/gripper, ultrasonic distance sensor, line sensor, battery reading, serial interface, Router Bridge RPC, and the CAM button start/stop/team-toggle.
2. **Hiwonder ESP32S3-CAM V1.0** runs `camera/HiwonderCamStream.ino`. Creates a Wi-Fi access point and serves the GC2145 camera as an MJPEG stream.
3. **Linux Python app** runs `python/main.py`, which uses `python/robot_client.py` for Bridge RPC, `python/camera.py` for the camera stream and inference, and `python/wall_detector.py` for HSV colour classification.

---

## Repository layout

```text
.
├── .agents/
│   └── skills/
│       └── uno-q-miniauto/          # Agent skill for extending this robot
├── references/
│   └── architecture.md              # Module contracts, Bridge API, extension patterns
├── SKILL.md                         # FOMO-edition agent skill (this repo's variant)
├── app.yaml                         # UNO Q App Lab application metadata
├── camera/
│   └── HiwonderCamStream.ino        # ESP32-S3 GC2145 camera firmware
├── python/
│   ├── main.py                      # Example: motion, camera, inference, sensors
│   ├── robot_client.py              # MiniAutoRobot Bridge wrapper
│   ├── camera.py                    # Camera thread, EI runner, wall detect, preview
│   ├── wall_detector.py             # HSV red/blue tape classifier
│   ├── requirements.txt             # Python package dependencies
│   └── *.eim                        # Your Edge Impulse model (not included by default)
└── sketch/
    ├── sketch.ino                   # Complete UNO Q miniAuto hardware driver
    └── sketch.yaml                  # Zephyr platform and Bridge dependency
```

---

## Quick start

1. Import this repository as a UNO Q App Lab application.
2. Build and upload `sketch/sketch.ino` to the Arduino UNO Q.
3. Flash the ESP32-S3 camera with `camera/HiwonderCamStream.ino` (see [Camera setup and flashing](#camera-setup-and-flashing)).
4. Install Python dependencies on the UNO Q Linux side:

   ```bash
   pip install -r python/requirements.txt
   ```

5. *(Optional)* Drop your Edge Impulse `.eim` file for Linux aarch64 into `python/`. It is auto-discovered.
6. Start the App Lab application. The robot prints health and sensor data, waits for the BOOT button, then runs the example loop.

Keep wheels clear of the ground during the first test. Press the BOOT button on the camera module to start/stop the program. Hold the BOOT button for 5 seconds to toggle team color (RED ↔ BLUE).

---

## Python driver API

`python/robot_client.py` exposes `MiniAutoRobot`, a typed wrapper around the Bridge RPC methods registered by the Arduino sketch.

```python
from robot_client import MiniAutoRobot

robot = MiniAutoRobot()
print(robot.health())
print(robot.read_sensors())

robot.drive("forward", speed=150, ms=700)
robot.stop()

team = "BLUE" if robot.hold_toggle() else "RED"
print(f"active team: {team}")
```

| Method | Behavior |
| --- | --- |
| `drive(command, speed=150, ms=500)` | Drives in a named direction. Speed is `0..255`; duration is clamped to `0..5000` ms. Duration `0` continues until stopped. Raises `ProgramStopped` if the program is disabled mid-move. |
| `stop()` | Stops all motors and disables obstacle avoidance. |
| `read_sensors()` | Returns the parsed sensor JSON as a dict, or `{}` on failure. |
| `servo(angle)` | Moves the servo/gripper; sketch clamps `0..180` degrees. |
| `buzz()` | Plays a three-part buzzer chirp. |
| `led(on)` | Sets onboard RGB and ultrasonic RGB to white or off. |
| `drive_raw(m0, m1, m2, m3, ms=500)` | Sets individual motor inputs clamped to `-255..255` with an optional auto-stop. |
| `health()` | Returns the parsed driver identity and interface status. |
| `is_running()` | Returns `True` when `program_enabled` is set in sensor JSON. |
| `hold_toggle()` | Returns `False` for RED team, `True` for BLUE team (CAM button 5-second hold state). |
| `run_program(routine)` | Use as `App.run(user_loop=lambda: robot.run_program(loop))`. Runs `routine()` once per start-button press; always calls `stop()` in `finally`. |

Accepted `drive` directions:

| Motion | Accepted values |
| --- | --- |
| Forward | `forward`, `f` |
| Backward | `backward`, `back`, `reverse`, `b` |
| Strafe left | `left`, `strafe_left`, `a` |
| Strafe right | `right`, `strafe_right`, `d` |
| Rotate left | `rotate_left`, `turn_left`, `q` |
| Rotate right | `rotate_right`, `turn_right`, `e` |
| Stop | `stop`, `x` |

---

## Camera and inference API

`python/camera.py` runs a background daemon thread that connects to the MJPEG stream and keeps the latest frame in memory.

```python
from camera import _start_camera, _copy_frame, _detect_wall, _run_inference

_start_camera()          # call once at startup

frame = _copy_frame()    # PIL.Image or None
```

| Function | Returns | Notes |
| --- | --- | --- |
| `_start_camera()` | `None` | Starts the background MJPEG reader. Call once. |
| `_copy_frame()` | `PIL.Image \| None` | Thread-safe copy of the latest frame. `None` until the first frame arrives. |
| `_detect_wall(pil_frame)` | `(side: str, coverage: dict)` | `side` is `"RED"`, `"BLUE"`, or `"UNKNOWN"`. `coverage` has `red`, `blue`, `total_pixels`. |
| `_run_inference(pil_frame)` | `list[dict]` | Bounding boxes: `{label, value, x, y, width, height}`. Returns `[]` when no model is loaded. |
| `get_preview_image()` | `dict` | `{"image": base64_jpeg, "result": {...}}` for the web preview endpoint. |

**Camera URL** is read from `ROBOCUP_CAMERA_URL` (default `http://192.168.5.1:81/stream`).

**Model auto-discovery**: `camera.py` globs for the first `*.eim` in its own directory. Drop your model file there and restart.

**Confidence threshold**: `_run_inference` filters detections to `value >= 0.55`. Adjust the constant in `camera.py` to tune precision vs. recall.

---

## Wall / Field-Side Detection

The soccer field has coloured tape strips on the walls — **red tape** on one side, **blue tape** on the other. Use the camera stream to detect which wall the robot is facing.

### How it works

1. Grab a frame with `_copy_frame()`.
2. Call `_detect_wall(frame)` (or use `WallDetector` directly from `wall_detector.py`).
3. The detector converts the frame to HSV and applies two colour masks.
4. If either colour exceeds 2% of frame pixels, it returns the dominant side.

### HSV colour ranges

OpenCV uses Hue 0–179, Saturation 0–255, Value 0–255. Red wraps around 0/180 and needs two masks.

| Colour | Hue range | Sat min | Val min |
| --- | --- | --- | --- |
| Red | 0–10 and 160–179 | 120 | 70 |
| Blue | 100–130 | 120 | 70 |

### Usage

```python
from camera import _copy_frame, _detect_wall

frame = _copy_frame()
if frame is not None:
    side, coverage = _detect_wall(frame)
    print(f"[FIELD] wall={side}  red={coverage['red']:.1%}  blue={coverage['blue']:.1%}")
```

Or use `WallDetector` directly for unit-testable logic:

```python
from wall_detector import WallDetector
import cv2, numpy as np

detector = WallDetector(min_coverage=0.02)
bgr_frame = cv2.cvtColor(np.asarray(pil_frame), cv2.COLOR_RGB2BGR)
side = detector.detect(bgr_frame)
```

### Expected output

```
[FIELD] wall=RED   red=5.2%  blue=0.0%
[FIELD] wall=BLUE  red=0.1%  blue=3.8%
[FIELD] wall=UNKNOWN  red=0.3%  blue=0.2%
```

### Tuning tips

- Detector reports UNKNOWN when tape is visible: lower `min_coverage` or widen the hue range.
- False positives on robot jerseys or the floor: raise saturation minimum or narrow hue range.
- Dark wall registers as very dark blue: raise value minimum (≥ 70 is the default).
- Print coverage percentages for a few seconds at startup to calibrate for your lighting.

---

## Edge Impulse FOMO integration

FOMO (Faster Objects, More Objects) is a lightweight object-detection model that runs well on edge hardware.

### Deploy your model

1. Export your trained model from Edge Impulse Studio as **Linux (AARCH64)** → `.eim` file.
2. Place the `.eim` file in `python/`. The runner is auto-discovered.
3. Restart the application.

### Call inference

```python
from camera import _copy_frame, _run_inference

frame = _copy_frame()
if frame is not None:
    detections = _run_inference(frame)
    for d in detections:
        print(f"  {d['label']}  conf={d['value']:.2f}  x={d['x']}  y={d['y']}")
```

Detection dict fields:

| Field | Type | Description |
| --- | --- | --- |
| `label` | `str` | Class label, e.g. `"soccerball"`, `"robot"`, `"goal"` |
| `value` | `float` | Confidence score (0.0–1.0) |
| `x` | `int` | Bounding box left edge (pixels) |
| `y` | `int` | Bounding box top edge (pixels) |
| `width` | `int` | Bounding box width (pixels) |
| `height` | `int` | Bounding box height (pixels) |

### Safe inference patterns

```python
# Always guard against no frame
frame = _copy_frame()
if frame is None:
    robot.stop()
    return

# Filter by label and minimum confidence
BALL_CONFIDENCE = 0.60
balls = [d for d in _run_inference(frame) if d["label"] == "soccerball" and d["value"] >= BALL_CONFIDENCE]

if not balls:
    robot.stop()   # safe default: stop when nothing detected
    return

# Use the highest-confidence detection
best = max(balls, key=lambda d: d["value"])
# ... steer toward best["x"], best["y"] ...
```

### Prerequisites

```bash
pip install edge-impulse-linux ai-edge-litert
```

Both are listed in `python/requirements.txt`. If `edge_impulse_linux` is not installed, `_run_inference` silently returns `[]`.

---

## Start/stop button and team toggle

The CAM button on the ESP32-S3 camera module controls the program:

- **Short press**: toggle program on/off. LED signals: red → yellow → green (starting), off (stopped).
- **Hold 5 seconds**: toggle team color. Onboard RGB: red = RED team, blue = BLUE team.

```python
from robot_client import MiniAutoRobot
from arduino.app_utils import App

robot = MiniAutoRobot()

def loop():
    team = "BLUE" if robot.hold_toggle() else "RED"
    print(f"[TEAM] {team}")
    # ... soccer logic here ...
    robot.stop()

App.run(user_loop=lambda: robot.run_program(loop))
```

`run_program` fires `loop()` once per start-button press, waits idly for the next press, catches `ProgramStopped` (raised by `drive`/`servo` when the program is disabled mid-move), and always calls `stop()` in `finally`.

---

## Sensor and health payloads

`read_sensors()` returns:

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

- `program_enabled`: `true` while the start button is active.
- `hold_toggle`: `false` = RED team, `true` = BLUE team.
- `line_digital` and `trace_digital` carry the same four bits (dual field for caller compatibility).
- `line_ok`: `false` if the I2C line-sensor read failed; bits are zeroed.
- `ultrasonic_mm` / `ultrasonic_cm`: `-1` if the I2C read failed.
- `ir`: reserved compatibility field, always `-1`.
- `battery_mv`: estimated from A3 using the miniAuto divider calibration; not a precision fuel gauge.

`health()` returns:

```json
{
  "robot": "hiwonder_miniauto",
  "mcu": "uno_q",
  "bridge": true,
  "serial": true
}
```

---

## Hardware map

| Part | Pin or address |
| --- | --- |
| Motor PWM channels M0, M1, M2, M3 | D10, D9, D6, D11 |
| Motor direction channels M0, M1, M2, M3 | D12, D8, D7, D13 |
| Onboard WS2812 RGB data | D2 |
| Passive buzzer | D3 |
| Servo/gripper | D5 |
| Battery divider | A3 |
| Glowing ultrasonic sensor | I2C `0x77` |
| Four-channel line sensor | I2C `0x78` |
| Camera / button controller | I2C `0x79` |

---

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROBOCUP_CAMERA_URL` | `http://192.168.5.1:81/stream` | MJPEG stream URL |
| `ROBOCUP_CAMERA_WIFI_AUTO_CONNECT` | `1` | Activate the most recently used saved camera Wi-Fi with NetworkManager before opening the stream; set to `0` to disable |
| `ROBOCUP_CAMERA_WIFI_PREFIX` | `miniAuto_CAM_` | Prefix used to identify saved camera Wi-Fi profiles |
| `ROBOCUP_CAMERA_WIFI_HELPER_SOCKET` | `/app/.camera_wifi.sock` | Unix socket used by App Lab to ask the UNO Q host to switch Wi-Fi |
| `ROBOCUP_SPEED` | `150` | Default motion speed (0–255) |
| `ROBOCUP_PULSE_MS` | `700` | Default motion duration in milliseconds |
| `ROBOCUP_PAUSE_SEC` | `0.25` | Pause before and between movements |

---

## UNO Q robot setup

### Requirements

- Arduino UNO Q with pre-assembled Hiwonder miniAuto chassis
- Python packages (install on the UNO Q Linux side):

  ```bash
  pip install -r python/requirements.txt
  ```

- *(Optional)* Your Edge Impulse `.eim` file placed in `python/`

There are two paths to build and upload `sketch/sketch.ino`. **Pick one** — you do not need both.

---

### Path A — Arduino App Lab

App Lab is the recommended path for most attendees. It handles board package management, library resolution, network port discovery, and router daemon lifecycle automatically.

1. Import or open this repository as a UNO Q App Lab application.
2. Click **Verify** to compile `sketch/sketch.ino`.
3. Click **Upload** to flash the board.
4. Click **Run** (or start the application from App Lab) to launch `python/main.py`.

The example prints health and sensor data, starts the camera thread, and waits for the BOOT button. On each start press it runs the demo loop: motion, wall detection, sensor read, servo, and LEDs.

Keep wheels raised during the first test.

---

### Path B — SSH from your laptop (no App Lab needed)

Write code on your laptop, push it to the UNO Q over SSH, and run it there. The sketch is already flashed — no compile or upload step needed for Python-only changes.

Each robot has a fixed address and shared credentials:

| | Value |
| --- | --- |
| User | `arduino` |
| Address | `192.168.x.x` (check the label on your robot, or run `arduino-cli board list`) |
| Password | `Q<number>pass!` — matches the robot number, e.g. robot 01 → `Q01pass!`, robot 32 → `Q32pass!` |

#### 1. SSH in and confirm the router is running

```bash
ssh arduino@192.168.x.x
# enter password when prompted
sudo systemctl status arduino-router
```

If it shows `inactive` or `failed`:

```bash
sudo systemctl start arduino-router
```

#### 2. Write code on your laptop, copy it to the board

From your laptop (not the SSH session), sync your `python/` directory to the board:

```bash
# one-time copy
scp -r python/ arduino@192.168.x.x:~/app/python/

# or keep it in sync as you edit (rsync, re-run after each change)
rsync -av --delete python/ arduino@192.168.x.x:~/app/python/
```

Then run it over SSH:

```bash
ssh arduino@192.168.x.x 'cd ~/app/python && python main.py'
```

Or stay inside the SSH session and run directly:

```bash
# inside the ssh session
cd ~/app/python
python main.py
```

#### 3. Iterate

Edit files on your laptop → `rsync` → re-run `python main.py` over SSH. No reboot or router restart needed between Python changes.

---

#### Re-flashing the sketch (only needed if you modify `sketch/sketch.ino`)

If you change the Arduino firmware, you need `arduino-cli` installed on the board itself (or another machine on the same network) and must stop the router during the upload.

**Install arduino-cli** (if not present on the board):

```bash
# run inside ssh session on the board
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
sudo mv bin/arduino-cli /usr/local/bin/
```

**Install the board package and libraries** (one-time):

```bash
arduino-cli core update-index
arduino-cli core install arduino:zephyr
arduino-cli lib update-index
arduino-cli lib install Arduino_RouterBridge Arduino_RPC
```

**Copy the sketch to the board and compile:**

```bash
# from your laptop
scp -r sketch/ arduino@192.168.x.x:~/app/sketch/

# inside ssh session
cd ~/app/sketch
arduino-cli compile --fqbn arduino:zephyr:unoq .
```

**Stop the router, upload, restart:**

```bash
PORT=$(arduino-cli board list | awk '/arduino:zephyr:unoq/ {print $1}')
sudo systemctl stop arduino-router
arduino-cli upload -p "$PORT" --fqbn arduino:zephyr:unoq .
sudo systemctl start arduino-router
```

---

### Path C — USB-C / ADB

Connect the UNO Q directly to your laptop with a USB-C cable. ADB gives you a shell on the board and lets you push files without needing Wi-Fi or knowing the board's IP address.

#### 1. Install ADB on your laptop

| OS | Command |
| --- | --- |
| macOS | `brew install android-platform-tools` |
| Windows | `winget install Google.PlatformTools` |
| Linux | `sudo apt-get install android-sdk-platform-tools` |

Verify: `adb version`

#### 2. Connect and open a shell

Plug the USB-C cable into the board and your laptop, then:

```bash
adb devices          # wait up to ~60 s for the board to appear
adb shell            # opens a terminal on the board
```

Default ADB password is `arduino` (only prompted if the board hasn't been set up via App Lab before). You should land at a shell on the board.

#### 3. Confirm the router is running

```bash
# inside adb shell
sudo systemctl status arduino-router
sudo systemctl start arduino-router   # if inactive
```

#### 4. Copy your Python files from laptop to board

Open a second terminal on your laptop (keep the `adb shell` session open in the first):

```bash
# push entire python/ directory to the board
adb push python/ /home/arduino/app/python/
```

To push a single file after a change:

```bash
adb push python/main.py /home/arduino/app/python/main.py
```

#### 5. Run your code

Back in the `adb shell` session:

```bash
cd /home/arduino/app/python
python main.py
```

#### Iterate

Edit on your laptop → `adb push` the changed file → re-run `python main.py` in the shell. No reboot or router restart needed between Python changes.

---



Open the UNO Q monitor at `9600` baud. The sketch accepts newline-terminated commands, single-key commands, Hiwonder pipe commands (`A|2|&`), and parenthesized commands. Buffered input is flushed after an 80 ms idle timeout.

### Single-key commands

| Key | Action |
| --- | --- |
| `?` | Print command help. |
| `r` | Print sensor JSON. |
| `l` | Blink onboard and ultrasonic RGB lights. |
| `z` | Play a buzzer chirp. |
| `u` | Print ultrasonic distance in millimeters. |
| `v` | Run servo center-open-close-center test. |
| `1`, `2`, `3`, `4` | Pulse one motor channel forward and backward for hardware mapping. |
| `f`, `b`, `a`, `d` | Drive forward, backward, left, or right using default settings. |
| `q`, `e` | Rotate left or right using default settings. |
| `x` | Stop all motors and disable obstacle avoidance. |

Single-key motion uses speed `180` and a `700` ms pulse.

### Line commands

| Command | Example | Notes |
| --- | --- | --- |
| `drive <dir> [speed] [ms]` | `drive forward 180 700` | Defaults to speed `180`; omitted duration = `0` (continuous). |
| `stop` | `stop` | Stops motors and obstacle avoidance. |
| `read_sensors` | `read_sensors` | Prints sensor JSON. |
| `servo <angle>` | `servo 90` | Clamped to `0..180`. |
| `buzz` | `buzz` | Plays a chirp. |
| `led <0/1>` | `led 1` | Sets both RGB paths to white or off. |
| `rgb <r> <g> <b>` | `rgb 255 0 0` | Each channel clamped `0..255`. |
| `drive_raw <m0> <m1> <m2> <m3> [ms]` | `drive_raw 120 120 120 120 500` | Each motor clamped `-255..255`. |
| `health` | `health` | Prints health JSON. |

### Motor diagnostics

Lift the wheels and keep hands, cables, and tools clear before using these.

| Command | Purpose |
| --- | --- |
| `dir_sweep <0..3>` | Tests direction-pin candidates for one sketch motor. |
| `dir_scan <0..3>` | Scans the broader non-PWM header-pin set for a direction signal. |
| `combo_scan` | Tries all PWM-channel combinations as fallback movement tests. |
| `pwm_combo <mask> <m2dir> <ms> <speed>` | Runs one PWM-only combination. Mask bits: `1=M0`, `2=M1`, `4=M2`, `8=M3`. |

---

## Hiwonder protocol compatibility

| Command | Action |
| --- | --- |
| `A\|state\|&` | Select a motion state (0–11). |
| `B\|r\|g\|b\|&` | Set both RGB light paths. |
| `C\|speed\|&` | Set speed percent, clamped `10..100`. |
| `D\|&` | Print `$ultrasonic_mm,battery_mv$`. |
| `E\|increase\|&` | Move servo to `90 + increase`; increase clamped `0..60`. |
| `F\|0\|&` / `F\|1\|&` | Disable / enable obstacle avoidance. |

Motion states for `A`: 0=left, 1=fwd-left, 2=forward, 3=fwd-right, 4=right, 5=bwd-right, 6=backward, 7=bwd-left, 8=stop, 9=rotate-left, 10=rotate-right, 11=stop.

---

## Camera setup and flashing

`camera/HiwonderCamStream.ino` is the firmware for the **Hiwonder ESP32S3-CAM V1.0 with GC2145 sensor**.

### Optional vendor tools

- [CH341/CH34x camera serial driver](https://drive.google.com/drive/folders/1CJBYFEaHWPLZ6eSSgGjHhziZFMqmF-mv)
- [Camera flash erase tool](https://drive.google.com/drive/folders/1iDdatjYswiquF1eNqKYVFBq68VrKZV_U)
- [Original `image_transmit.bin`](https://drive.google.com/drive/folders/1YOCjBNvqUxpelmbY5Be6dNHE6siZCAke)

Review downloaded software per your organization's security policy before running.

### One-time Arduino IDE setup

1. Go to **Tools → Board → Boards Manager**.
2. Search for `esp32`.
3. Install **esp32 by Espressif Systems**, version **2.0.11** (NOT 3.x — GC2145 init fails on 3.x).

### Board settings for each upload

| Setting | Value |
| --- | --- |
| Board | `ESP32S3 Dev Module` |
| PSRAM | `OPI PSRAM` |
| Flash Size | `8MB (64Mb)` |
| Partition Scheme | `Huge APP (3MB No OTA/1MB SPIFFS)` |
| USB CDC On Boot | `Disabled` |
| Flash Mode | `DIO` |
| Upload Speed | `921600` |
| Port | The serial/COM port assigned to the camera |

### Flash procedure

1. Open `camera/HiwonderCamStream.ino`.
2. Set a unique `CAMERA_SSID` (default `miniAuto_CAM_01`; use `_02`, `_03`, etc. for additional cameras).
3. Set `CAMERA_PASS` if needed (default `hiwonder123`).
4. Click **Upload**. Confirm verified hash + hard reset, then power-cycle the camera.

### Test the stream

1. Connect a device to the camera's Wi-Fi SSID.
2. Open `http://192.168.5.1:81/` → **Start Stream**.
3. Direct MJPEG endpoint: `http://192.168.5.1:81/stream`

```python
CAMERA_URL = "http://192.168.5.1:81/stream"
```

### Camera configuration

Soft AP at `192.168.5.1/24`, port `81`, QVGA (`320×240`), RGB565 → JPEG quality 80, two PSRAM frame buffers.

| Signal | GPIO | Signal | GPIO |
| --- | ---: | --- | ---: |
| PWDN | `-1` | RESET | `-1` |
| XCLK | `15` | PCLK | `13` |
| SIOD/SDA | `4` | SIOC/SCL | `5` |
| Y2 | `11` | Y3 | `9` |
| Y4 | `8` | Y5 | `10` |
| Y6 | `12` | Y7 | `18` |
| Y8 | `17` | Y9 | `16` |
| VSYNC | `6` | HREF | `7` |

---

## Building your Edge Impulse model

### 1. Start a project

Create an Edge Impulse project or clone the [pre-labelled capture dataset](https://studio.edgeimpulse.com/public/1085406/live).

### 2. Label bounding boxes

Label objects in your captured images:

- `soccerball` — bounding box around each visible ball.
- `robot` — bounding box around each visible robot.
- `goal` — bounding box around each goal.

Keep boxes tight. Consistent labeling improves FOMO accuracy.

### 3. Create an impulse

**Input block** — Image:
- Image size: **96 × 96**
- Color depth: **RGB**
- Resize mode: **squash**

**Processing block**: Image

**Learning block** — Object Detection (Images):
- Output features: 3 (goal, robot, soccerball)

### 4. Generate features

Run the image processing block to generate features before training.

### 5. Train the neural network

- Training cycles: **150–180**
- Learning rate: **0.001**
- Training processor: **CPU**

Review validation metrics and per-class behavior before exporting.

### 6. Export and deploy

1. Go to **Deployment** in Edge Impulse Studio.
2. Deployment target: **Linux (AARCH64)**
3. Click **Build** and download the `.eim` file.
4. Place the `.eim` file in `python/`.

Recommended path:

```text
python/
  your-model-linux-aarch64.eim
```

The model is loaded automatically on next startup.

---

## Safety and troubleshooting

### Robot safety behavior

- Named and raw drive durations are clamped to `0..5000` ms.
- A nonzero duration arms an automatic stop timer; `0` means continuous motion.
- Speed and motor inputs are clamped before PWM output.
- `stop()`, serial `stop`, and serial `x` stop every motor and disable obstacle avoidance.
- `ProgramStopped` is raised by `drive`/`servo` mid-routine if the program is disabled; `run_program` catches it and calls `stop()`.
- The battery value is an estimate; it is not a precision fuel gauge.

Always begin with wheels raised, use short timed commands, and keep a physical power disconnect within reach.

### Robot does not respond to Python

- **App Lab:** confirm the sketch built successfully and the application is running.
- **SSH path:** confirm `arduino-router` is running on the board (`sudo systemctl status arduino-router`); restart it if inactive.
- Confirm `Arduino_RouterBridge` was installed (App Lab reads `sketch/sketch.yaml`; CLI requires `arduino-cli lib install Arduino_RouterBridge`).
- Run `health` in the serial monitor at 9600 baud; `serial` and `bridge` should both be `true`.
- Run single-motor tests with wheels raised to verify physical mapping.

### Camera initialization fails

- Confirm Espressif ESP32 board package is version **2.0.11**, not 3.x.
- Confirm board, PSRAM, flash, partition, USB CDC, and flash-mode settings match the table.
- Upload again and fully power-cycle the camera.

### Camera serial port is missing

- Try a data-capable USB cable and another USB port.
- On Windows, install the CH34x driver if Device Manager shows an unknown USB serial device.
- Reopen Arduino IDE after driver installation.

### Stream is slow or choppy

The GC2145 delivers RGB565; the ESP32-S3 converts every frame to JPEG in software. Stay close to the access point, disconnect unused clients, and keep the default QVGA frame size while diagnosing.

### Edge Impulse runner fails to load

- Confirm `edge-impulse-linux` and `ai-edge-litert` are installed: `pip install -r python/requirements.txt`.
- Confirm the `.eim` is the **Linux aarch64** build, not x86 or WASM.
- Check the console for import errors at startup; missing packages cause `_run_inference` to silently return `[]`.

### Camera returns `None` frames at startup

`_copy_frame()` returns `None` until the first MJPEG frame is decoded. Add a warmup wait in your loop or guard inference calls with `if frame is not None`.
