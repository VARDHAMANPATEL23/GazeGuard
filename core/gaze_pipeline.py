import sys
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import queue
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import config
from utils.camera import open_camera, release_camera

class GazePipeline:
    """
    Camera Thread: reads frames, runs MediaPipe, extracts iris vectors,
    and pushes (raw_gaze, face_count) to a queue at ~30fps.
    """

    def __init__(self, calibration_manager, device_node="/dev/video0"):
        self.manager = calibration_manager
        self.device_node = device_node
        self.output_queue = queue.Queue(maxsize=5)  # cap to avoid stale frames
        self._running = False
        self._thread = None

    def start(self):
        model_path = str(config.BASE_DIR / 'face_landmarker.task')
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=2   # detect up to 2 faces for multi-face security
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        
        self.cap = open_camera(self.device_node)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {self.device_node}")

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.name = "GazePipelineThread"
        self._thread.start()

    def _loop(self):
        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.detector.detect(mp_img)

            face_count = len(result.face_landmarks)

            if face_count >= 1:
                vec = self.manager.extract_normalized_vector(result.face_landmarks[0])
                if vec:
                    raw_gaze = self.manager.predict(vec)
                    try:
                        # Drop old entry if queue is full (non-blocking)
                        self.output_queue.put_nowait((raw_gaze, face_count))
                    except queue.Full:
                        try:
                            self.output_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self.output_queue.put_nowait((raw_gaze, face_count))
            else:
                # No face detected — signal absence for Boss Mode
                try:
                    self.output_queue.put_nowait((None, 0))
                except queue.Full:
                    pass

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if hasattr(self, 'cap'):
            release_camera(self.cap)
        if hasattr(self, 'detector'):
            self.detector.close()
