import json
import queue
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.boss_mode import BossModeController
from core.calibration import CalibrationManager
from core.gaze_pipeline import GazePipeline
from core.smoother import GazeSmoother


class GazeEngine:
    """
    Gaze Engine: consumes (raw_gaze, face_count) from GazePipeline,
    applies Kalman smoothing, manages Boss Mode absence security,
    and exposes get_gaze_point() for the overlay.
    """

    def __init__(self, smoothing_level="medium"):
        self._smooth_gaze = None  # (x, y) — latest smooth coordinate
        self._face_count = 0  # latest face count (-1 = camera disconnected)
        self._multi_face = False  # True when more than 1 face detected
        self._camera_connected = True
        self._lock = threading.Lock()

        self.smoother = GazeSmoother(smoothing_level)
        self.boss_mode = BossModeController()

        # Load calibration profile
        self.cal_manager = self._load_calibration()

        # Load camera device from config
        device_node = "/dev/video0"
        if config.CAMERA_FILE.exists():
            try:
                with open(config.CAMERA_FILE, "r") as f:
                    device_node = json.load(f).get("device", "/dev/video0")
            except Exception:
                pass

        screen_w, screen_h = self._get_screen_resolution()
        self.pipeline = GazePipeline(self.cal_manager, device_node)

        self._running = False
        self._consumer_thread = None

    def _load_calibration(self):
        if not config.DEFAULT_PROFILE_FILE.exists():
            raise FileNotFoundError(
                f"No calibration profile found at {config.DEFAULT_PROFILE_FILE}. "
                "Run ui/calibration_ui.py first."
            )

        # Screen resolution from profile
        with open(config.DEFAULT_PROFILE_FILE, "r") as f:
            data = json.load(f)
        w, h = data["screen_resolution"]

        manager = CalibrationManager(w, h)
        manager.load_profile()
        return manager

    def _get_screen_resolution(self):
        if config.DEFAULT_PROFILE_FILE.exists():
            try:
                with open(config.DEFAULT_PROFILE_FILE, "r") as f:
                    data = json.load(f)
                return tuple(data["screen_resolution"])
            except Exception:
                pass
        return (1920, 1080)

    def reload_settings(self):
        """Reload runtime settings for smoothing and boss mode."""
        self.boss_mode.reload_settings()

    def start(self):
        self.pipeline.start()
        self._running = True
        self._consumer_thread = threading.Thread(
            target=self._consume_loop, daemon=True, name="GazeEngineConsumer"
        )
        self._consumer_thread.start()

    def _consume_loop(self):
        while self._running:
            try:
                raw_gaze, face_count = self.pipeline.output_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            with self._lock:
                self._face_count = face_count
                if face_count == -1:
                    # Camera disconnected safe mode
                    self._camera_connected = False
                    self._smooth_gaze = None
                    self._multi_face = False
                    continue

                self._camera_connected = True
                self._multi_face = face_count > 1

                # Update boss mode state machine with current face count
                self.boss_mode.update(face_count)

                if raw_gaze is not None and not self.boss_mode.is_boss_blur():
                    sx, sy = self.smoother.update(raw_gaze[0], raw_gaze[1])
                    self._smooth_gaze = (int(sx), int(sy))
                else:
                    self._smooth_gaze = None

    def get_gaze_point(self):
        """Returns (x, y) smoothed screen coordinate or None if no face or in boss blur."""
        with self._lock:
            return self._smooth_gaze

    def is_camera_connected(self):
        """Returns True if the camera feed is healthy."""
        with self._lock:
            return self._camera_connected

    def is_multi_face(self):
        """Returns True when more than 1 face is detected."""
        with self._lock:
            return self._multi_face

    def is_boss_blur(self):
        """Returns True when boss mode absence blur is triggered."""
        return self.boss_mode.is_boss_blur()

    def get_boss_state(self):
        return self.boss_mode.get_state()

    def get_boss_fade_alpha(self):
        return self.boss_mode.get_fade_alpha()

    def face_count(self):
        with self._lock:
            return self._face_count

    def stop(self):
        self._running = False
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=2.0)
        self.pipeline.stop()
