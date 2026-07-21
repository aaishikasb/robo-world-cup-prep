import time

from arduino.app_utils import App
from robot_client import MiniAutoRobot

robot = MiniAutoRobot()

print(f"health   : {robot.health()}")
print(f"sensors  : {robot.read_sensors()}")


def drive(direction: str, speed: int = 150, ms: int = 500) -> None:
    """Drive and wait for the move to finish before continuing."""
    print(f"  {direction} speed={speed} ms={ms}")
    robot.drive(direction, speed, ms)
    time.sleep(ms / 1000.0 + 0.1)


def wait_for_button() -> None:
    """Wait until Modulino A is pressed and the sketch enables the program.
    The sketch handles all LED feedback — Python stays silent here.
    If no Modulino is connected, skips the wait and starts immediately."""
    sensors = robot.read_sensors()
    if not sensors.get("modulino_buttons"):
        print("[INFO] no Modulino detected - starting immediately")
        return
    print("[INFO] waiting for Modulino button A to start...")
    while not robot.read_sensors().get("program_enabled"):
        time.sleep(0.1)
    print("[INFO] program enabled - starting")


def loop() -> None:
    # --- Move ---
    drive("forward",      speed=150, ms=500)
    drive("backward",     speed=150, ms=500)
    drive("left",         speed=150, ms=500)   # strafe left
    drive("right",        speed=150, ms=500)   # strafe right
    drive("rotate_left",  speed=255, ms=3250)  # spin in place, 255 firmware cap on speed
    time.sleep(0.5)
    drive("rotate_right", speed=255, ms=3250)

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
    raise SystemExit


try:
    wait_for_button()
    App.run(user_loop=loop)
finally:
    robot.stop()

