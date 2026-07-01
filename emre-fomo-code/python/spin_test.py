import os
import time

from arduino.app_utils import App

from robot_client import MiniAutoRobot


# Isolated spin test tuning
# mode=cycle auto-rotates through numbered spin configs.
# mode=left_two uses only the first two motors (left side test).
# mode=raw uses all 4 motors via raw mixing.
# mode=cmd uses the drive command string directly (firmware dependent).
# Default to TEST 4 directly: raw + pattern d.
SPIN_MODE = os.getenv("ROBOCUP_SPIN_MODE", "raw").lower()
SPIN_COMMAND = os.getenv("ROBOCUP_SPIN_COMMAND", "right")
SPIN_DIRECTION = os.getenv("ROBOCUP_SPIN_DIRECTION", "cw").lower()
SPIN_RAW_PATTERN = os.getenv("ROBOCUP_SPIN_RAW_PATTERN", "d").lower()
SPIN_SPEED = int(os.getenv("ROBOCUP_SPIN_SPEED", "120"))
SPIN_MS = int(os.getenv("ROBOCUP_SPIN_MS", "350"))
SPIN_PAUSE_SECONDS = float(os.getenv("ROBOCUP_SPIN_PAUSE_SECONDS", "0.02"))
CYCLE_HOLD_SECONDS = float(os.getenv("ROBOCUP_CYCLE_HOLD_SECONDS", "2.0"))


# Numbered configs for quick "best is #N" feedback.
_CYCLE_CONFIGS: list[tuple[str, str, str, str]] = [
    ("raw", "cw", "a", "raw pattern a"),
    ("raw", "cw", "b", "raw pattern b"),
    ("raw", "cw", "c", "raw pattern c"),
    ("raw", "cw", "d", "raw pattern d"),
    ("left_two", "cw", "c", "left_two"),
]

_cycle_index = -1
_cycle_next_switch_at = 0.0


robot = MiniAutoRobot()


def _run_spin(mode: str, direction: str, raw_pattern: str) -> None:
    if mode == "left_two":
        s = max(0, min(255, SPIN_SPEED))

        # Left-side-only test: run first two motors opposite each other.
        if direction == "ccw":
            robot.drive_raw(-s, s, 0, 0, SPIN_MS)
        else:
            robot.drive_raw(s, -s, 0, 0, SPIN_MS)
    elif mode == "raw":
        s = max(0, min(255, SPIN_SPEED))

        # Try different raw mixes because motor index/order can vary by build.
        # a/b = alternating wheel signs, c/d = front-vs-rear sign split.
        if raw_pattern == "a":
            cw = (s, -s, s, -s)
            ccw = (-s, s, -s, s)
        elif raw_pattern == "b":
            cw = (-s, s, -s, s)
            ccw = (s, -s, s, -s)
        elif raw_pattern == "d":
            cw = (-s, -s, s, s)
            ccw = (s, s, -s, -s)
        else:
            cw = (s, s, -s, -s)
            ccw = (-s, -s, s, s)

        motors = ccw if direction == "ccw" else cw
        robot.drive_raw(motors[0], motors[1], motors[2], motors[3], SPIN_MS)
    else:
        robot.drive(SPIN_COMMAND, SPIN_SPEED, SPIN_MS)


def loop() -> None:
    global _cycle_index, _cycle_next_switch_at

    if SPIN_MODE == "cycle":
        now = time.monotonic()
        if now >= _cycle_next_switch_at:
            _cycle_index = (_cycle_index + 1) % len(_CYCLE_CONFIGS)
            _cycle_next_switch_at = now + CYCLE_HOLD_SECONDS

            mode, direction, pattern, label = _CYCLE_CONFIGS[_cycle_index]
            print(f"[TEST {_cycle_index + 1}] {label} mode={mode} dir={direction} pattern={pattern}")

        mode, direction, pattern, _ = _CYCLE_CONFIGS[_cycle_index]
        _run_spin(mode, direction, pattern)
    else:
        _run_spin(SPIN_MODE, SPIN_DIRECTION, SPIN_RAW_PATTERN)

    time.sleep((SPIN_MS / 1000.0) + SPIN_PAUSE_SECONDS)


print("[INFO] isolated spin test starting")
print(
    f"[INFO] spin mode={SPIN_MODE} direction={SPIN_DIRECTION} "
    f"pattern={SPIN_RAW_PATTERN} command={SPIN_COMMAND} "
    f"speed={SPIN_SPEED} pulse_ms={SPIN_MS} hold_s={CYCLE_HOLD_SECONDS}"
)
print(f"[INFO] health={robot.health()}")
print(f"[INFO] sensors={robot.read_sensors()}")

try:
    App.run(user_loop=loop)
finally:
    robot.stop()
    print("[INFO] isolated spin test stopped")
