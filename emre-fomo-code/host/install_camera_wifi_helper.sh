#!/bin/sh
set -eu

APP_DIR="/home/arduino/ArduinoApps/emre-fomo-code"
SOURCE_HELPER="$APP_DIR/host/camera_wifi_helper.py"
INSTALL_DIR="/home/arduino/.local/lib/miniauto"
HELPER="$INSTALL_DIR/camera_wifi_helper.py"
PID_FILE="$APP_DIR/.camera_wifi_helper.pid"
LOG_FILE="$APP_DIR/.camera_wifi_helper.log"
MARKER="# miniauto-camera-wifi-helper"

mkdir -p "$INSTALL_DIR"
cp "$SOURCE_HELPER" "$HELPER"
chmod +x "$HELPER"

if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE")"
    if [ -n "$OLD_PID" ] && [ -r "/proc/$OLD_PID/cmdline" ] && \
       tr '\0' ' ' < "/proc/$OLD_PID/cmdline" | grep -qF "$HELPER"; then
        kill "$OLD_PID"
    fi
fi

CRON_TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -vF "$MARKER" > "$CRON_TMP" || true
echo "@reboot /usr/bin/python3 $HELPER >> $LOG_FILE 2>&1 $MARKER" >> "$CRON_TMP"
crontab "$CRON_TMP"
rm -f "$CRON_TMP"

nohup /usr/bin/python3 "$HELPER" >> "$LOG_FILE" 2>&1 &
echo "camera Wi-Fi helper installed and started"
