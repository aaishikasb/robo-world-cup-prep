# Robot Soccer Hackathon — conversation and debugging handoff

Updated: 2026-09-17. Intended next assistant: GPT Terra, medium reasoning.

This is a detailed conversation summary and operational handoff, not a verbatim transcript. Read it before continuing. The user wants fixes made **one at a time, with physical validation between changes**.

## Workspace and user objective

- Workspace: `C:\Users\qc_de\Developer\robo-world-cup-prep\emre-fomo-code`.
- Actual Git root is the parent: `C:\Users\qc_de\Developer\robo-world-cup-prep`.
- Windows host, PowerShell, America/Los_Angeles timezone.
- Robots: Hiwonder miniAuto chassis, four 60 mm mecanum wheels, UNO Q, expansion board, ESP32-S3 camera.
- Wheel reference inspected: `docs/assets/miniauto-getting-ready/assembly/04.png`.
- Camera product supplied by user: https://www.hiwonder.com/products/esp32-s3.
- Each UNO Q has an App Lab connection to a host PC and a Wi-Fi connection to its own camera. **Camera video is wireless; camera BOOT button events are wired I2C, address 0x79.** The user confirmed the I2C wiring works across the robots.
- Field: red/blue tape, goals with nets, soccer ball. First hackathon required attendees to deploy a supplied Edge Impulse FOMO model trained on already-captured data. That was too ambitious.
- Next hackathon should provide working hardware/perception so attendees focus on ball/goal/side search, offense/defense, and movement strategies including diagonals.
- User wants parts of camera/client locked down while allowing custom movement. Suggested boundary: organizer owns transport, model lifecycle, calibration and MCU fail-safes; attendees own strategy and bounded movement/mixing.

## Latest user report and immediate interpretation

Latest user message: “put this conversation into an md file that is accessible to a new chat with gpt terra medium, also the wheels couldn't turn on again after automatic four second stop”.

**The most recent drive test was deliberately ONE-SHOT.** It sent one four-second drive command, called `stop()` in `finally`, then exited. Its temporary Docker container was removed. No Python driving routine remains running from that test. Therefore pressing BOOT again can re-enable the firmware but cannot issue another drive command. This is a strong explanation for the reported inability to restart; it is not proof of a new motor fault.

Important distinction:

- MCU `updateDriveTimer()` calls `stopMotors()`, which does not disable the program.
- Bridge `stop()` calls `rpcStop()`, which calls `setProgramEnabled(false)` as well as stopping motors.
- The test observed no stop-button event during its pulse, then cleanup called Bridge `stop()`. Final sensors confirmed `program_enabled=false`.

Next: explain the one-shot behavior to the user and run a deliberately repeatable, bounded test (or explicitly rerun the one-shot), with a fresh BOOT start per trial. Validate stop during actual motion and restarting a second trial. Do not diagnose restart failure from the old test as firmware failure without this check.

## User preferences and authorization

- User asked to proceed through fixes sequentially and validate each.
- User explicitly requested sketch upload via ADB.
- Before upload, user confirmed expansion-board power was off.
- Subsequently user said “plugged in expansion board, wheels up”.
- User then explicitly requested “test with driving now”. Low-speed bounded forward test was executed under that authorization.
- No need to repeatedly ask for already-provided authorization in the same physical setup. If starting a later session and the setup may have changed, establish current physical state before moving hardware.
- Applicable skill: `.agents/skills/uno-q-miniauto/SKILL.md`. It requires confirmed safe physical setup before flashing/moving and staged validation. Read it and its architecture reference before edits.
- No subagents were used. Do not infer that this handoff requests creating a new chat; it requests a file usable from one.

## Code changes completed (only first fix)

Modified `sketch/sketch.ino`:

1. Removed `lastButtonActionAt` and the extra one-second short-press cooldown. Camera firmware already debounces and acknowledges each event by clearing it on I2C read; the UNO cooldown previously discarded acknowledged presses.
2. Converted `beginProgramEnableCountdown()` from blocking `delay(600)` twice to a nonblocking state machine.
3. Added `programEnableStartedAt`, `programEnableYellow`, and `updateProgramEnableCountdown()`.
4. A short press while `programEnablePending` cancels startup through `setProgramEnabled(false)`.
5. Idle blue flashing is suppressed during the countdown.
6. Main loop checks the button before advancing the countdown.

Modified `README.md` start/stop section with I2C-vs-Wi-Fi clarification, cancellation behavior, short-press-on-release semantics, and a physical test checklist.

No camera firmware, Python source, dependency configuration, or model changes were made. No commits were made.

Current Git status:

```text
 M .gitignore                         # PRE-EXISTING USER CHANGE
 M README.md                          # our button documentation
 D references/architecture.md         # PRE-EXISTING USER CHANGE
 M sketch/sketch.ino                   # our button fix
```

Preserve pre-existing user changes. `HANDOFF.md` is newly added by this handoff request.

## Validation already performed

- Four Python source files passed parsing/byte compilation.
- `git diff --check` passed.
- Baseline and strict contract checker both fail on the **pre-existing** missing `Arduino_RouterBridge` declaration in `sketch/sketch.yaml`; not caused by the button changes. The sketch profile also has blank `fqbn`.
- The updated sketch **compiled successfully on the UNO Q** with installed core `arduino:zephyr 0.90.0` and `Arduino_RouterBridge 0.4.3`.
- Compilation reported 120124 bytes program storage (15%) and 46154 bytes globals (17%).
- Uploaded successfully through ADB using the board's `arduino-cli upload`/remoteocd.
- User physically reported: “red yellow green -> stays on green, hit again goes to blue, hit again red yellow hit again goes to blue, stays cancelled”. This validates observed startup, disable/idle-blue behavior and cancellation during startup. It does not establish separately measured stop latency or stop while moving.
- Blue after stop is idle flashing, not necessarily a team switch.

## Health timeout investigation

User's original failure:

```text
File /app/python/main.py, line 166
    print(f"health   : {robot.health()}")
File /app/python/robot_client.py, line 80
    raw = Bridge.call("health")
TimeoutError: Request 'health' timed out after 10s
```

User observes this after expansion power stays on and idle. Their known recovery sequence:

1. Unplug host USB-C.
2. Turn expansion board off.
3. Reconnect USB-C.
4. Turn expansion board on.

The deployed Python line numbers differ from the local checkout; likely another app version. **Do not overwrite board Python with local Python assuming they match.**

Observed during this session:

1. First flash was performed with expansion power OFF.
2. Router stayed active, but subsequent read-only `health` still timed out after expansion power was turned ON.
3. Re-uploading the **same compiled binary**, with expansion power ON, reset the MCU.
4. After that, both `health` and `read_sensors` succeeded without unplugging USB or restarting Linux.
5. `stop()` succeeded and sensors confirmed disabled state.

This implicates MCU/peripheral startup state but does NOT prove an I2C root cause. Do not call it fixed yet.

Installed RouterBridge source was inspected on the board:

- `/home/arduino/Arduino/libraries/Arduino_RouterBridge/src/bridge.h`
- `/home/arduino/Arduino/libraries/Arduino_RouterBridge/src/monitor.h`
- `provide_safe` handlers are processed through `__loopHook()` / `safeUpdate()`. A blocked setup or main loop can therefore prevent a `health` response even though `rpcHealth()` itself does not perform I2C.
- `Monitor.begin()` can initialize Bridge before the explicit `Bridge.begin()` later in sketch setup. Earlier speculation that all Bridge initialization happens after I2C was incomplete; distinguish library initialization from registration of our RPC providers.
- Sketch setup calls Monitor.begin, Wire.begin, setupPins, ultrasonic LED I2C, then explicit Bridge.begin/registerBridgeMethods.
- Main loop includes serial monitor polling and repeated I2C access.

Router logs showed invalid MessagePack/closed-connection errors around flashing. Bridge.begin in the installed library writes a startup string to flush broken RPCs; therefore these log messages alone do not prove ongoing malfunction. Later calls succeeded.

Observed sensors after recovery: line_ok=true; ultrasonic initially -1 then valid 875 mm and ~2114 mm; battery estimate ~17800 mV. Battery value is unvalidated calibration, not a verified physical voltage. Final hold_toggle=false.

## Most recent driving test: exact behavior and result

Temporary host script:
`C:\Users\qc_de\AppData\Local\Temp\robot_drive_stop_probe.py`

Board script:
`/tmp/codex-button-fix.FAbzuA/robot_drive_stop_probe.py`

Script used direct Bridge calls as a standalone diagnostic (not the production strategy/client); future production code should reuse MiniAutoRobot.

Behavior:

1. Wait up to 60 seconds for physical BOOT to set program_enabled=true, polling every 50 ms.
2. Issue `Bridge.call('drive', 'forward', 80, 4000, timeout=2)` once.
3. Poll program_enabled for up to 4.3 seconds, looking for button disable.
4. In `finally`, call `Bridge.call('stop', timeout=3)` and print sensors.
5. Exit and remove temporary container.

Actual output:

```text
READY: press/release BOOT to start. Then press/release again during motion.
START detected: forward speed=80, hardware auto-stop=4000 ms
No button stop observed during pulse; hardware timer should have stopped motors. Physical confirmation needed.
Cleanup stop: True
Final sensors: ... program_enabled: False, hold_toggle: False
```

The prior assistant asked whether wheels turned and whether BOOT was pressed/released before they stopped. User instead requested this handoff and reported wheels would not turn on again after automatic stop. **Physical stop-during-motion validation remains incomplete.** No motion command has been issued since the one-shot test ended.

## ADB and build/upload details (known working)

ADB executable on host (not on PATH):

```text
C:\Users\qc_de\AppData\Local\Arduino15\packages\arduino\tools\adb\32.0.0\adb.exe
```

Connected board at time of testing:

- ADB serial: `1177864026`
- Hostname/product: `miniAutoQ23`
- Host Arduino discovery: COM3, UNO Q.
- ADB shell user: `arduino`.
- Board CLI: `/usr/bin/arduino-cli`, version 1.5.1.
- App CLI: `/usr/bin/arduino-app-cli`.
- Router socket: `/var/run/arduino-router.sock`.
- Router service: `arduino-router`, active.

Recheck device identity before future hardware actions. Example PowerShell:

```powershell
$adbPath = 'C:/Users/qc_de/AppData/Local/Arduino15/packages/arduino/tools/adb/32.0.0/adb.exe'
& $adbPath devices -l
& $adbPath -s 1177864026 shell 'arduino-cli core list'
```

The updated sketch was pushed by itself (without the incomplete sketch.yaml) to:
`/tmp/codex-button-fix.FAbzuA/sketch/sketch.ino`

Successful compile command inside ADB shell:

```sh
arduino-cli compile --fqbn arduino:zephyr:unoq --output-dir /tmp/codex-button-fix.FAbzuA/build /tmp/codex-button-fix.FAbzuA/sketch
```

Successful upload command inside ADB shell:

```sh
arduino-cli upload --fqbn arduino:zephyr:unoq --input-dir /tmp/codex-button-fix.FAbzuA/build /tmp/codex-button-fix.FAbzuA/sketch
```

No explicit port was needed: remoteocd supports local flashing on the UNO's Linux side. Upload completed with exit 0. Temporary files may disappear on reboot.

**Do not use `/usr/local/bin/arduino-flash` or `/opt/openocd/bin/arduino-flash.sh`:** inspected old scripts hardcode `0x80F0000`; current core flash config uses `0x08100000`. Use the installed CLI's matching upload recipe.

`sudo -n true` and `systemctl stop arduino-router` were denied authentication. No credentials were guessed. The supported `arduino-cli upload` still worked without these manual service operations.

## Safe read-only Bridge probing without starting App Lab

No App Lab app containers were running when tested. Several stopped containers existed. A locally cached base image contains the Bridge Python module:
`ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`.

Host board Python does not have `arduino` or `msgpack` installed. Use a temporary container with **overridden entrypoint**; its normal entrypoint tries to create an app virtualenv and fails without app mounts.

Known working command in the board shell:

```sh
docker run --rm --network none --entrypoint python \
  -v /var/run/arduino-router.sock:/var/run/arduino-router.sock \
  ghcr.io/arduino/app-bricks/python-apps-base:0.12.0 \
  -u -c 'from arduino.app_utils import Bridge; print(Bridge.call("health", timeout=5)); print(Bridge.call("read_sensors", timeout=5))'
```

For multiline diagnostic scripts, push a temporary file to the board and mount it read-only into the same image, then run `python -u /probe.py`. Do not start an unknown existing app, which could reflash old firmware or start its own strategy.

## App Lab source caveat

We flashed the MCU from a temporary copy. **We did not update the sketch within an existing App Lab app.** Starting one of those apps could recompile/reflash its old sketch.

Observed user apps:

- `user:assets` — “HSV Startup”, failed state.
- `user:python-20260828-180520` — “Qualcomm/AI-LA Robot Soccer Cup”, stopped.
- Other stopped/failed arcade and capture apps.

`/home/arduino/ArduinoApps/assets/python` contains main.py, robot_client.py, wall_detector.py, spin_test.py, requirements.txt and an EIM model; its layout differs from this repository (no separate camera.py listed). Identify the intended app before synchronizing; preserve board-only changes and make a backup.

## Remaining review findings and proposed sequence

These were identified in the initial review, but **not fixed yet**, except the button cooldown/countdown:

1. Complete physical button-stop/restart validation with an appropriate test harness.
2. Diagnose startup/idle health timeout using the reproducible power-state evidence; do not merely swallow timeouts or endlessly retry.
3. Separate motion stop from program disable. Current `robot.stop()` disables firmware and breaks later operations in starter `main.py` (servo after stop raises ProgramStopped). Revisit run_program semantics together.
4. Enforce program-enabled and finite command expiry on MCU motion entry points. Current rpcDrive/rpcDriveRaw do not check enabled state; Python-only checking has a race. Duration zero means indefinite motion.
5. Remove/isolate blocking diagnostics and make deadline handling dependable. Current servo, buzzer, serial motor scans block; main-loop timer is not an independent watchdog.
6. Make Python motion validation/timing consistent. drive ignores rejected RPC result and sleeps for unbounded caller duration despite MCU clamping to five seconds; drive_raw returns immediately. Malformed sensor JSON raises rather than returning {} as docs claim.
7. Fix inference lifecycle: camera.py constructs ImageImpulseRunner but never calls init(); official SDK requires it. main.py never invokes inference. Errors are collapsed to empty detections. Pin explicit model path, required labels and readiness.
8. Fix stale camera data: no frame timestamp/sequence, old image survives disconnect indefinitely, unbounded malformed-MJPEG accumulation. Publish fresh coherent observations and stop on stale perception.
9. Fix preview schema/state: UI uses score but inference returns value; soccer_ball vs soccerball label mismatch; raw frame preview overwrites detection results; FPS counts requests; CHASING does not reflect actual strategy state.
10. Fix reproducible distribution: current .gitignore excludes camera/docs/.agents and these directories were untracked; blank board identifier/missing Bridge dependency in sketch.yaml; README camera path/password mismatch. Preserve user's .gitignore edits when addressing this explicitly.
11. Provide stable bounded movement API with diagonals. Firmware already has velocityController(angle, velocity, rot, drift) and diagonal legacy serial commands. Confirm per-robot wheel ordering/polarity: old comments say only one motor reliably reverses; that statement is not physically verified in this session.
12. Treat tape color as visible wall color, not proof of field-half position. Add tape ROI, ambiguity margin and temporal persistence. Current equal red/blue coverage picks RED.
13. FOMO outputs are centroid/grid based; do not infer true object dimensions/distance from returned box width/height. Supply normalized centers and correct model/image coordinate mapping.
14. Provision models/dependencies before event. Make participant strategy a small entry point with recorded-observation tests and modest baseline. Explicit no-target vs failed-perception distinction.
15. Fleet setup: unique camera SSIDs/pairing, intentional Wi-Fi channels (softAP default is channel 1), one direct stream consumer per camera, host preview through UNO, tested host management link for untethered matches.

Relevant primary sources checked:

- SDK initialization: https://github.com/edgeimpulse/linux-sdk-python/blob/master/edge_impulse_linux/image.py
- FOMO centroid behavior: https://www.edgeimpulse.com/blog/announcing-fomo-faster-objects-more-objects/
- ESP32 AP defaults: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html
- Supported uploader: https://github.com/arduino/remoteocd
- Router protocol: https://github.com/arduino/arduino-router

## Suggested first response in the new chat

Explain that the diagnostic exited and disabled the program after its single pulse, so BOOT alone cannot restart its motion. Check current board identity/physical setup, then prepare a bounded repeatable test using a fresh start press for each trial. Observe actual stop-button state transitions and ask the user whether wheels physically stop. Keep the original one-fix-at-a-time plan; do not silently implement the whole backlog.
