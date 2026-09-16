import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

sys.path.append(str(Path(__file__).parent.parent))
import config
from utils.camera import open_camera, release_camera


def _send_notification(title, message):
    """Send desktop notification via notify-send if available."""
    try:
        subprocess.Popen(
            ["notify-send", "-u", "critical", "-a", "GazeGuard", title, message]
        )
    except Exception:
        pass


class GazePipeline:
    """
    Camera Thread: reads frames, runs MediaPipe, extracts iris vectors,
    and pushes (raw_gaze, face_count) to a queue at ~30fps.
    Includes disconnect resilience with automatic 5-second reconnect retries.
    """

    def __init__(self, calibration_manager, device_node="/dev/video0"):
        self.manager = calibration_manager
        self.device_node = device_node
        self.output_queue = queue.Queue(maxsize=5)  # cap to avoid stale frames
        self.camera_connected = True
        self._running = False
        self._thread = None
        self.cap = None

    def start(self):
        model_path = str(config.BASE_DIR / "face_landmarker.task")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=2,  # detect up to 2 faces for multi-face security
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

        self.cap = open_camera(self.device_node)
        if not self.cap.isOpened():
            self.camera_connected = False
            print(
                f"Warning: Camera {self.device_node} not available at startup. Will retry..."
            )
        else:
            self.camera_connected = True

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.name = "GazePipelineThread"
        self._thread.start()

    def _loop(self):
        consecutive_failures = 0

        while self._running:
            # Handle disconnected camera state
            if not self.camera_connected or self.cap is None or not self.cap.isOpened():
                self._handle_reconnect()
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    print(
                        f"Camera read failed {consecutive_failures} times. Disconnecting..."
                    )
                    self._handle_disconnect()
                else:
                    time.sleep(0.03)
                continue

            consecutive_failures = 0

            # Optimize resolution for low CPU footprint (scale down if > 640w)
            h, w = frame.shape[:2]
            if w > 640:
                scale = 640.0 / w
                frame = cv2.resize(
                    frame, (640, int(h * scale)), interpolation=cv2.INTER_AREA
                )

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.detector.detect(mp_img)

            face_count = len(result.face_landmarks)

            if face_count >= 1:
                vec = self.manager.extract_normalized_vector(result.face_landmarks[0])
                if vec:
                    raw_gaze = self.manager.predict(vec)
                    self._push_output(raw_gaze, face_count)
                else:
                    self._push_output(None, face_count)
            else:
                # No face detected — signal absence for Boss Mode
                self._push_output(None, 0)

    def _push_output(self, raw_gaze, face_count):
        try:
            self.output_queue.put_nowait((raw_gaze, face_count))
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.output_queue.put_nowait((raw_gaze, face_count))
            except queue.Full:
                pass

    def _handle_disconnect(self):
        self.camera_connected = False
        if self.cap:
            release_camera(self.cap)
            self.cap = None

        _send_notification(
            "GazeGuard: Camera Disconnected",
            "Camera feed lost. Screen secured. Retrying every 5 seconds...",
        )
        self._push_output(None, -1)  # face_count = -1 signals camera error

    def _handle_reconnect(self):
        """Periodically retry opening camera every 5 seconds."""
        time.sleep(5.0)
        if not self._running:
            return

        print(f"Attempting to reconnect camera {self.device_node}...")
        try:
            new_cap = open_camera(self.device_node)
            if new_cap.isOpened():
                # Verify read
                ret, _ = new_cap.read()
                if ret:
                    self.cap = new_cap
                    self.camera_connected = True
                    print(f"Camera {self.device_node} reconnected successfully!")
                    _send_notification(
                        "GazeGuard: Camera Reconnected",
                        "Camera feed restored. Resuming gaze tracking.",
                    )
                    return
            release_camera(new_cap)
        except Exception as e:
            print(f"Reconnect error: {e}")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if hasattr(self, "cap") and self.cap:
            release_camera(self.cap)
        if hasattr(self, "detector"):
            self.detector.close()
