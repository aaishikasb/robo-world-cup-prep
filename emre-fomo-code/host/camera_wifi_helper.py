#!/usr/bin/env python3
"""UNO Q host helper for App Lab camera Wi-Fi switching."""

import os
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

APP_DIR = Path("/home/arduino/ArduinoApps/emre-fomo-code")
SOCKET_PATH = APP_DIR / ".camera_wifi.sock"
PID_PATH = APP_DIR / ".camera_wifi_helper.pid"
NMCLI = "/usr/bin/nmcli"
APP_CLI = "/usr/bin/arduino-app-cli"
APP_ID = "dXNlcjplbXJlLWZvbW8tY29kZQ"
RELAUNCH_LOG = APP_DIR / ".camera_wifi_relaunch.log"


def run_nmcli(*args: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NMCLI, *args], capture_output=True, check=False, text=True, timeout=timeout
    )


def relaunch_if_stopped() -> None:
    """Relaunch after App Lab loses its control connection during the Wi-Fi handoff."""
    time.sleep(15)
    listed = subprocess.run(
        [APP_CLI, "app", "list", "--format", "json"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    try:
        apps = json.loads(listed.stdout).get("apps", [])
        status = next(app["status"] for app in apps if app["id"] == APP_ID)
    except (json.JSONDecodeError, KeyError, StopIteration):
        print("could not determine app status after Wi-Fi switch", flush=True)
        return
    if status != "stopped":
        print(f"app status after Wi-Fi switch: {status}; no relaunch needed", flush=True)
        return
    print("app stopped during Wi-Fi handoff; relaunching locally", flush=True)
    with RELAUNCH_LOG.open("a", encoding="utf-8") as log:
        subprocess.run(
            [APP_CLI, "app", "start", str(APP_DIR)],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=180,
        )


def switch_wifi(prefix: str) -> str:
    active = run_nmcli("-t", "-f", "GENERAL.CONNECTION", "device", "show", "wlan0")
    active_connection = active.stdout.strip().removeprefix("GENERAL.CONNECTION:")
    profiles = run_nmcli(
        "-t", "--escape", "no", "-f", "UUID,TYPE,TIMESTAMP", "connection", "show"
    )
    if profiles.returncode != 0:
        return f"ERROR profile list: {profiles.stderr.strip()}"

    candidates: list[tuple[int, str, str]] = []
    for line in profiles.stdout.splitlines():
        try:
            uuid, connection_type, timestamp_text = line.rsplit(":", 2)
            timestamp = int(timestamp_text or 0)
        except ValueError:
            continue
        if connection_type != "802-11-wireless":
            continue
        result = run_nmcli(
            "-g", "802-11-wireless.ssid", "connection", "show", "uuid", uuid
        )
        ssid = result.stdout.strip()
        if result.returncode == 0 and ssid.startswith(prefix):
            candidates.append((timestamp, uuid, ssid))

    if not candidates:
        return f"ERROR no saved profile matching {prefix}*"

    _, uuid, ssid = max(candidates)
    connected = run_nmcli("--wait", "15", "connection", "up", "uuid", uuid)
    if connected.returncode != 0:
        detail = connected.stderr.strip() or connected.stdout.strip()
        return f"ERROR {ssid}: {detail}"
    if active_connection != ssid:
        threading.Thread(target=relaunch_if_stopped, daemon=True).start()
    return f"OK {ssid}"


def main() -> None:
    PID_PATH.write_text(str(os.getpid()), encoding="ascii")
    SOCKET_PATH.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o666)
        server.listen(4)
        print(f"camera Wi-Fi helper listening on {SOCKET_PATH}", flush=True)
        while True:
            connection, _ = server.accept()
            with connection:
                try:
                    prefix = connection.recv(256).decode("utf-8").strip()
                    response = switch_wifi(prefix) if prefix else "ERROR empty prefix"
                except Exception as e:
                    response = f"ERROR {type(e).__name__}: {e}"
                print(response, flush=True)
                try:
                    connection.sendall((response + "\n").encode("utf-8"))
                except BrokenPipeError:
                    # Switching Wi-Fi can tear down the App Lab client before it
                    # receives the reply. The requested host-side switch still
                    # succeeded, so keep serving future app starts.
                    pass


if __name__ == "__main__":
    main()
