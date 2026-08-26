import json
import time
from typing import Any, Callable

from arduino.app_utils import Bridge


class ProgramStopped(Exception):
    """Raised when the start/stop button disables the program mid-routine."""


class MiniAutoRobot:
    def __init__(self) -> None:
        self._session_active = False

    def is_running(self) -> bool:
        return bool(self.read_sensors().get("program_enabled"))

    def hold_toggle(self) -> bool:
        """Read-only state of the CAM boot button's 5-second-hold toggle (red/blue LED)."""
        return bool(self.read_sensors().get("hold_toggle"))

    def _require_running(self) -> None:
        if not self._session_active:
            raise ProgramStopped

    def drive(self, command: str, speed: int = 150, ms: int = 500) -> None:
        Bridge.call("drive", command, int(speed), int(ms))

    def stop(self) -> bool:
        return bool(Bridge.call("stop"))

    def read_sensors(self) -> dict[str, Any]:
        raw = Bridge.call("read_sensors")
        return json.loads(raw) if raw else {}

    def servo(self, angle: int) -> None:
        Bridge.call("servo", int(angle))

    def buzz(self) -> bool:
        return bool(Bridge.call("buzz"))

    def led(self, on: bool) -> bool:
        return bool(Bridge.call("led", bool(on)))

    def drive_raw(self, m0: int, m1: int, m2: int, m3: int, ms: int = 500) -> None:
        Bridge.call("drive_raw", int(m0), int(m1), int(m2), int(m3), int(ms))

    def drive_diagonal(self, direction: str, speed: int = 150, ms: int = 500) -> None:
        """Diagonal mecanum drive. direction: 'forward_left' | 'forward_right' | 'back_left' | 'back_right'."""
        s = max(0, min(255, int(speed)))
        if direction == "forward_left":
            Bridge.call("drive_raw", 0, s, s, 0, int(ms))
        elif direction == "forward_right":
            Bridge.call("drive_raw", s, 0, 0, s, int(ms))
        elif direction == "back_left":
            Bridge.call("drive_raw", 0, -s, -s, 0, int(ms))
        else:  # back_right
            Bridge.call("drive_raw", -s, 0, 0, -s, int(ms))

    def health(self) -> dict[str, Any]:
        raw = Bridge.call("health")
        return json.loads(raw) if raw else {}

    def run_program(self, routine: Callable[[], None]) -> None:
        """Pass this as App.run's user_loop. Button press starts the program; a second
        press between routine calls stops it. _session_active is the authoritative stop
        flag during a move (avoids false-stop on transient sensor read failures)."""
        currently_enabled = self.is_running()
        if not currently_enabled:
            if self._session_active:
                # firmware just flipped off — user pressed stop between calls
                self._session_active = False
                self.stop()
                print("[INFO] program stopped - press the button again to restart")
                print(f"[INFO] hold_toggle: {'blue' if self.hold_toggle() else 'red'}")
            return
        if not self._session_active:
            self._session_active = True
            print("[INFO] program enabled - starting")
        try:
            routine()
        except ProgramStopped:
            self.stop()
            self._session_active = False
            print("[INFO] program stopped mid-sequence - press the button again to restart")
