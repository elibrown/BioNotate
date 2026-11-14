
import time

import cv2
from websockets.sync.client import connect


SERVER_URL = "ws://127.0.0.1:8000/ws/video/test-astronaut"

# Open the default webcam on Windows
camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not camera.isOpened():
    raise RuntimeError("Could not open webcam")

try:
    with connect(SERVER_URL) as websocket:
        print("Connected to backend!")

        for i in range(30):
            # Read a frame from the webcam
            success, frame = camera.read()

            if not success:
                raise RuntimeError("Failed to read camera frame")

            # Encode the frame as PNG
            encoded, buffer = cv2.imencode(".png", frame)

            if not encoded:
                raise RuntimeError("Failed to encode frame")

            # Send binary data over WebSocket
            websocket.send(buffer.tobytes())

            print(f"Sent frame {i + 1}/30")

            time.sleep(0.1)

        # The server sends a status every 30 frames
        response = websocket.recv(timeout=10)
        print("Server response:", response)

finally:
    camera.release()
    print("Camera released")
