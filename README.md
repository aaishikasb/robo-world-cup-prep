# QC Robo World Cup Drivers and Tools

This repository contains UNO Q driver code and clients for the Hiwonder miniAuto robot used in the Robo World Cup Prep.

The main driver lives in `sketch/sketch.ino`. It controls the motors, RGB
lights, buzzer, servo/gripper, ultrasonic sensor, line sensor, battery readout,
and the command interfaces used by the Python app and serial monitor.

## Project Layout

- `sketch/sketch.ino`: Arduino driver for the Hiwonder miniAuto.
- `sketch/sketch.yaml`: Arduino profile using `arduino:zephyr` and
  `Arduino_RouterBridge`.
- `python/robot_client.py`: Python wrapper around the Bridge RPC calls exposed
  by the sketch.
- `python/main.py`: Example motion sequence that reads health/sensors and drives
  forward, left, right, and backward.
- `app.yaml`: App configuration.

## Hardware Map

The sketch targets an Arduino UNO Q running the Zephyr Arduino platform.

| Part | Pin or Address |
| --- | --- |
| Motor PWM pins | D10, D9, D6, D11 |
| Motor direction pins | D12, D8, D7, D13 |
| Onboard WS2812 RGB data | D2 |
| Passive buzzer | D3 |
| Servo/gripper | D5 |
| Battery divider | A3 |
| Ultrasonic sensor | I2C `0x77` |
| 4-channel line sensor | I2C `0x78` |

Observed motor connector mapping:

| Sketch Motor | PWM Pin | Board Connector | Notes |
| --- | --- | --- | --- |
| M0 | D10 | M3 | Forward only with current direction map |
| M1 | D9 | M2 | Backward only with current direction map |
| M2 | D6 | M1 | Forward/backward works with DIR D7 |
| M3 | D11 | M4 | Forward only with current direction map |

## Python Driver API

`python/robot_client.py` exposes the `MiniAutoRobot` class. These methods call
the Arduino driver through `Arduino_RouterBridge`:

```python
from robot_client import MiniAutoRobot

robot = MiniAutoRobot()
robot.drive("forward", speed=150, ms=700)
robot.stop()
print(robot.read_sensors())
```

Available methods:

| Method | What it does |
| --- | --- |
| `drive(command, speed=150, ms=500)` | Drives in a named direction for an optional duration. |
| `stop()` | Stops all motors and disables obstacle avoidance. |
| `read_sensors()` | Returns parsed sensor JSON. |
| `servo(angle)` | Moves the servo/gripper to `0..180` degrees. |
| `buzz()` | Plays a short buzzer chirp. |
| `led(on)` | Turns the white status LEDs on or off. |
| `drive_raw(m0, m1, m2, m3, ms=500)` | Sets raw per-motor speeds from `-255..255`. |
| `health()` | Returns driver identity and connection status. |

Drive commands accepted by the sketch:

- `forward` or `f`
- `backward`, `back`, `reverse`, or `b`
- `left`, `strafe_left`, or `a`
- `right`, `strafe_right`, or `d`
- `rotate_left`, `turn_left`, or `q`
- `rotate_right`, `turn_right`, or `e`
- `stop` or `x`

The example in `python/main.py` runs one motion sequence, using these optional
environment variables:

- `ROBOCUP_SPEED`: default `150`
- `ROBOCUP_PULSE_MS`: default `700`
- `ROBOCUP_PAUSE_SEC`: default `0.25`

## Sensor Payload

`read_sensors()` returns a dictionary shaped like this:

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
  "battery_mv": 7400
}
```

`line_digital` and `trace_digital` contain the same four line sensor bits for
compatibility with different callers. Ultrasonic reads return `-1` when the I2C
read fails.

## Serial Commands

The sketch also accepts commands from the serial monitor at `9600` baud.

Single-key commands:

| Command | Action |
| --- | --- |
| `?` | Print help. |
| `r` | Print sensor JSON. |
| `l` | Blink RGB/status LEDs. |
| `z` | Play buzzer chirp. |
| `u` | Print ultrasonic distance in millimeters. |
| `v` | Run a servo center-open-close-center test. |
| `1`, `2`, `3`, `4` | Pulse one motor channel for hardware testing. |
| `f`, `b`, `a`, `d` | Drive forward, backward, left, or right. |
| `q`, `e` | Rotate left or right. |
| `x` | Stop all motors. |

Line commands:

| Command | Example |
| --- | --- |
| `drive <direction> [speed] [ms]` | `drive forward 180 700` |
| `stop` | `stop` |
| `read_sensors` or `sensors` | `read_sensors` |
| `servo <angle>` | `servo 90` |
| `buzz` | `buzz` |
| `led <0|1>` | `led 1` |
| `rgb <r> <g> <b>` | `rgb 255 0 0` |
| `drive_raw <m0> <m1> <m2> <m3> [ms]` | `drive_raw 120 120 120 120 500` |
| `health` | `health` |

Diagnostic commands:

| Command | Use |
| --- | --- |
| `dir_sweep <0..3>` | Tests known direction pin candidates for one motor. |
| `dir_scan <0..3>` | Scans a broader set of header pins for direction control. |
| `combo_scan` | Tries PWM-only motor combinations to find fallback movement. |
| `pwm_combo <mask> <m2dir> <ms> <speed>` | Runs one PWM-only diagnostic combination. |

For `pwm_combo`, mask bits are `1=M0`, `2=M1`, `4=M2`, and `8=M3`.

## Hiwonder Protocol Compatibility

The sketch accepts Hiwonder-style pipe-delimited commands ending in `&`:

| Command | Action |
| --- | --- |
| `A|state|&` | Motion state. |
| `B|r|g|b|&` | RGB color. |
| `C|speed|&` | Set speed percent, clamped to `10..100`. |
| `D|&` | Print ultrasonic distance and battery millivolts. |
| `E|increase|&` | Move servo to `90 + increase`, clamped through servo limits. |
| `F|0|&` or `F|1|&` | Disable or enable obstacle avoidance. |

Motion states for `A`:

| State | Motion |
| --- | --- |
| `0` | Left |
| `1` | Forward-left |
| `2` | Forward |
| `3` | Forward-right |
| `4` | Right |
| `5` | Backward-right |
| `6` | Backward |
| `7` | Backward-left |
| `8` | Stop |
| `9` | Rotate left |
| `10` | Rotate right |
| `11` | Stop |

## Safety Behavior

- Drive durations are clamped to `0..5000` ms.
- A nonzero drive duration arms an automatic motor stop timer.
- Speeds are clamped before they are sent to PWM.
- `stop()` and serial `x` stop all motors and disable obstacle avoidance.
- Obstacle avoidance checks the ultrasonic sensor every 100 ms. When enabled, it
  rotates if an object is closer than 400 mm and otherwise drives forward.
