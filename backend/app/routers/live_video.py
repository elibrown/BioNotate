
from collections import deque
from time import monotonic

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter()

MAX_FRAME_BYTES = 4 * 1024 * 1024  # 4 MB


@router.websocket("/ws/video/{astronaut_id}")
async def video_stream(
    websocket: WebSocket,
    astronaut_id: str,
):
    await websocket.accept()

    print(f"Video stream connected: {astronaut_id}")

    frame_count = 0
    frame_buffer = deque(maxlen=90)

    try:
        while True:
            # Receive PNG-encoded frame
            frame_bytes = await websocket.receive_bytes()

            if len(frame_bytes) > MAX_FRAME_BYTES:
                await websocket.send_json({
                    "type": "error",
                    "message": "Frame exceeds size limit",
                })
                continue

            # Decode the frame
            buffer = np.frombuffer(
                frame_bytes, dtype=np.uint8
            )

            bgr_frame = cv2.imdecode(
                buffer, cv2.IMREAD_COLOR
            )

            if bgr_frame is None:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid image frame",
                })
                continue

            # Convert to RGB for the prediction models
            rgb_frame = cv2.cvtColor(
                bgr_frame, cv2.COLOR_BGR2RGB
            )

            timestamp = monotonic()

            # Save frame in the rolling buffer
            frame_buffer.append((timestamp, rgb_frame))
            frame_count += 1

            if frame_count % 30 == 0:
                duration = (
                    frame_buffer[-1][0]
                    - frame_buffer[0][0]
                )

                await websocket.send_json({
                    "type": "status",
                    "astronaut_id": astronaut_id,
                    "frames_received": frame_count,
                    "frames_buffered": len(frame_buffer),
                    "buffer_duration_seconds": round(
                        duration, 2
                    ),
                    "frame_shape": list(rgb_frame.shape),
                })

    except WebSocketDisconnect:
        print(f"Stream disconnected: {astronaut_id}")
