# HiwonderCamStream — Setup & Flashing Guide

MJPEG streaming firmware for the **Hiwonder ESP32S3-CAM V1.0** (GC2145 sensor).
Replaces the stock `image_transmit.bin` with a unique SSID per robot.


## Downloads

Sketchy looking CH341 cam driver (so it shows up under Other Devices in Device Manager)
https://drive.google.com/drive/folders/1CJBYFEaHWPLZ6eSSgGjHhziZFMqmF-mv

Use this flash tool to erase the cam if something goes wrong
https://drive.google.com/drive/folders/1iDdatjYswiquF1eNqKYVFBq68VrKZV_U

image_transmit.bin (originaly source driver, loaded through flash tool above)
https://drive.google.com/drive/folders/1YOCjBNvqUxpelmbY5Be6dNHE6siZCAke

---

## One-time Arduino IDE Setup

### 1. Install the ESP32 Board Package

1. Open Arduino IDE
2. Go to **Tools → Board → Board Manager**
3. Search for `esp32`
4. Find **"esp32 by Espressif Systems"**
5. Select version **2.0.11** from the dropdown

> ⚠️ Version 2.0.11 is required. Version 3.x has a bug with the GC2145 sensor
> that causes camera init to fail regardless of pixel format setting.

### 2. Board Settings (Tools menu)

Every time you open Arduino IDE, verify these settings:

| Setting | Value |
|---|---|
| Board | `ESP32S3 Dev Module` |
| PSRAM | `OPI PSRAM` |
| Flash Size | `8MB (64Mb)` |
| Partition Scheme | `Huge APP (3MB No OTA/1MB SPIFFS)` |
| USB CDC On Boot | `Disabled` |
| Flash Mode | `DIO` |
| Upload Speed | `921600` |
| Port | whichever COM port the camera appears on |

---

## Flashing Each Robot

### Step 1 — Change the SSID

Open `HiwonderCamStream.ino` and edit line 23:

```cpp
#define CAMERA_SSID  "miniAuto_CAM_01"   // change to _02, _03 ... _30
#define CAMERA_PASS  "Q01pass!"        
```


### Step 2 — Upload

Click the **Upload arrow** in Arduino IDE (or Sketch → Upload).

The output should end with:
```
Hash of data verified.
Hard resetting via RTS pin...
```

### Step 3 — Test

1. Unplug and replug the USB (or power cycle on the robot)
2. On your phone or PC, scan for WiFi
3. Connect to `miniAuto_CAM_XX` — password `hiwonder123`
4. Open a browser and go to `http://192.168.5.1:81`
5. Click **▶ Start Stream**

---

## Stream URL

```
http://192.168.5.1:81/stream
```

This URL is the same on every robot. Since each robot has a unique SSID,
connecting to a specific robot's hotspot routes traffic to that camera only.

In Python:
```python
CAMERA_URL = "http://192.168.5.1:81/stream"
```

---


### Camera Pin Definitions (CAMERA_MODEL_ESP32S3_EYE)

```cpp
#define PWDN_GPIO_NUM   -1
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   15
#define SIOD_GPIO_NUM    4
#define SIOC_GPIO_NUM    5
#define Y2_GPIO_NUM     11
#define Y3_GPIO_NUM      9
#define Y4_GPIO_NUM      8
#define Y5_GPIO_NUM     10
#define Y6_GPIO_NUM     12
#define Y7_GPIO_NUM     18
#define Y8_GPIO_NUM     17
#define Y9_GPIO_NUM     16
#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM   13
#define XCLK_FREQ_HZ    15000000
```

Source: Hiwonder's `camera_setting.h` from the ColorDetection firmware package.

---

## Troubleshooting

**"Camera init failed" on the web page**
- Wrong board package version (must be 2.0.11, not 3.x)
- Re-upload after confirming version in Board Manager

**Can't see the COM port**
- CH340 driver not installed
- Driver location: Hiwonder docs → Appendix → ch34x Driver (Windows)

**Stream is slow or choppy**
- Normal — GC2145 outputs RGB565 which is converted to JPEG in software


