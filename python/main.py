import os
import time

from arduino.app_utils import App

# ---------------------------------------
# MiniAuto Robot
# ---------------------------------------
# Import the MiniAuto robot "driver"
from robot_client import MiniAutoRobot

# Golbal variables for the MiniAuto control
ROBOT_SPEED_SLOW = int(100)
ROBOT_SPEED_MED = int(os.getenv("ROBOCUP_SPEED", "150"))
ROBOT_SPEED_FAST = int(255)
PULSE_MS = int(os.getenv("ROBOCUP_PULSE_MS", "700"))
PAUSE_SEC = float(os.getenv("ROBOCUP_PAUSE_SEC", "0.25"))

robot = MiniAutoRobot()

# ---------------------------------------
# ESP-CAM video feed
# ---------------------------------------
# URL for displaying live stream of the ESP-CAM (Important: the UNO Q has to be setup to connect to the ESP-CAM wifi access point)
STREAM_URL = "http://192.168.5.1:81/stream" 

# ---------------------------------------
# Streamlit WebUI
# ---------------------------------------
# Import Streamlit library
from arduino.app_bricks.streamlit_ui import st

# Write title on top
st.write("Interact with your MiniAuto bot using this web interface.")

# Split the UI in 2 main columns
col1, col2 = st.columns([2, 3])

# In the left column we will display control buttons and robot status info
with col1:
    st.subheader("Controls")

    # we will split the col1 culumn into 3 subcolumns to display control buttons next to each other like a joystick
    # Top row
    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c2:
        if st.button("↑ Forward", use_container_width=True):
            robot.drive("forward", ROBOT_SPEED_SLOW, 5000)

    # Second row
    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        if st.button("← Left", use_container_width=True):
            robot.drive("left", ROBOT_SPEED_SLOW, 5000)
    with r2c2:
        if st.button("■ Stop", use_container_width=True):
            robot.stop()
    with r2c3:
        if st.button("Right →", use_container_width=True):
            robot.drive("right", ROBOT_SPEED_SLOW, 5000)

    # Third row
    r3c1, r3c2, r3c3 = st.columns(3)
    with r3c2:
        if st.button("↓ Backward", use_container_width=True):
            robot.drive("backward", ROBOT_SPEED_SLOW, 5000)

    # Bottom row
    r4c1, r4c2, r4c3 = st.columns(3)
    with r4c1:
        if st.button("⟲ Rotate L", use_container_width=True):
            robot.drive("rotate_left", ROBOT_SPEED_MED, 5000)
    with r4c2:
        if st.button("🔊 Buzz", use_container_width=True):
            robot.buzz()
    with r4c3:
        if st.button("Rotate R ⟳", use_container_width=True):
            robot.drive("rotate_right", ROBOT_SPEED_MED, 5000)
            
    # Below the controls we will display the rogot health indicators and sensors readings
    st.divider()       
    st.write("Robot Health:")
    st.write(robot.health())
    st.write("Sensors read:")
    st.write(robot.read_sensors())

# In the right column of the UI we will display the live stream from the ESP-CAM and some camera status info
with col2:

    st.subheader("Live stream")
    # Using the iframe method to simply display the video from its streaming URL
    st.iframe(STREAM_URL)

    st.subheader("Camera Status")
    st.write(f"**Stream URL:** `{STREAM_URL}`")

# Force periodic refresh so the displayed image updates continuously
time.sleep(0.05)
st.rerun()

# Start the app
App.run()