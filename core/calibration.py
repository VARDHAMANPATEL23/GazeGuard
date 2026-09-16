import datetime
import json
import math
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures

sys.path.append(str(Path(__file__).parent.parent))
import config


class CalibrationManager:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.poly = PolynomialFeatures(degree=2, include_bias=True)
        self.model_x = Ridge(alpha=0.1)
        self.model_y = Ridge(alpha=0.1)

        self.grid_points = self._generate_grid()
        self.collected_data = []

        # Camera position on screen (normalised, loaded from camera.json)
        self._cam_x_norm = 0.5  # top-center by default
        self._cam_y_norm = 0.0
        self._load_cam_pos()

    def _load_cam_pos(self):
        """Read camera screen position from camera.json."""
        if config.CAMERA_FILE.exists():
            try:
                with open(config.CAMERA_FILE) as f:
                    pos = json.load(f).get("position", {})
                self._cam_x_norm = float(pos.get("x", 0.5))
                self._cam_y_norm = float(pos.get("y", 0.0))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _generate_grid(self, cols=None, rows=None, margin=0.05):
        """Generates an evenly spaced grid of screen calibration points."""
        cols = cols or config.CALIBRATION_GRID_COLS
        rows = rows or config.CALIBRATION_GRID_ROWS
        points = []
        mx = self.screen_width * margin
        my = self.screen_height * margin
        uw = self.screen_width - 2 * mx
        uh = self.screen_height - 2 * my
        xs = uw / (cols - 1) if cols > 1 else 0
        ys = uh / (rows - 1) if rows > 1 else 0
        for r in range(rows):
            for c in range(cols):
                points.append((int(mx + c * xs), int(my + r * ys)))
        return points

    # ------------------------------------------------------------------
    def extract_normalized_vector(
        self, face_landmarks, image_width=None, image_height=None
    ):
        """
        Extract a scale-invariant 4D iris vector normalized separately
        for X (by face bounding box width) and Y (by face bounding box height).
        This preserves the true aspect ratio of eye movement.
        """
        landmarks = (
            face_landmarks.landmark
            if hasattr(face_landmarks, "landmark")
            else face_landmarks
        )
        if landmarks is None or len(landmarks) <= 473:
            return None

        # Pixel space or normalized landmark space: ratios are identical
        w = image_width if image_width else 1.0
        h = image_height if image_height else 1.0

        xs = [lm.x * w for lm in landmarks]
        ys = [lm.y * h for lm in landmarks]

        bbox_x_min, bbox_x_max = min(xs), max(xs)
        bbox_y_min, bbox_y_max = min(ys), max(ys)
        bbox_width = bbox_x_max - bbox_x_min
        bbox_height = bbox_y_max - bbox_y_min

        if bbox_width <= 1e-6 or bbox_height <= 1e-6:
            return None

        # Iris landmark indices (MediaPipe FaceLandmarker):
        # Left iris center ≈ index 468, Right iris center ≈ index 473
        left_iris = landmarks[468]
        right_iris = landmarks[473]

        left_x_norm = (left_iris.x * w - bbox_x_min) / bbox_width
        left_y_norm = (left_iris.y * h - bbox_y_min) / bbox_height
        right_x_norm = (right_iris.x * w - bbox_x_min) / bbox_width
        right_y_norm = (right_iris.y * h - bbox_y_min) / bbox_height

        return [left_x_norm, left_y_norm, right_x_norm, right_y_norm]

    # ------------------------------------------------------------------
    def _scale_vector(self, vec):
        """Apply Y-axis amplification to compensate for face aspect ratio compression."""
        lx, ly, rx, ry = vec[:4]
        s = getattr(config, "IRIS_Y_SCALE_FACTOR", 1.4)
        return [lx, ly * s, rx, ry * s]

    # ------------------------------------------------------------------
    def add_point_data(self, screen_point, vectors):
        # Average incoming vectors for this calibration point.
        if not vectors:
            return
        mean_vec = np.mean(vectors, axis=0).tolist()
        self.collected_data.append({"point": screen_point, "vector": mean_vec})

    def add_continuous_sample(self, screen_point, vector):
        # Append one frame directly - used by continuous-path calibration.
        self.collected_data.append({"point": screen_point, "vector": vector})

    @property
    def calibration_data(self):
        """Alias for collected_data."""
        return self.collected_data

    @calibration_data.setter
    def calibration_data(self, data):
        self.collected_data = data

    # ------------------------------------------------------------------
    def train(self):
        # Fit Ridge regression models
        if len(self.collected_data) < 3:
            return False

        X = []
        y_x = []
        y_y = []
        for d in self.collected_data:
            vec = d.get("vector", d.get("landmark_vector"))
            pt = d.get("point", d.get("screen_xy"))
            X.append(self._scale_vector(vec))
            y_x.append(pt[0])
            y_y.append(pt[1])

        Xp = self.poly.fit_transform(X)
        self.model_x.fit(Xp, y_x)
        self.model_y.fit(Xp, y_y)
        return True

    def train_model(self):
        """Alias for train() per test specifications."""
        return self.train()

    # ------------------------------------------------------------------
    def _perspective_correction(self, px, py):
        """
        Correct for perspective foreshortening at high gaze angles.

        Physics: camera sits at (cam_x, cam_y) on screen. When the user
        looks at angle theta from the camera axis, the iris moves by d * tan(theta)
        in screen space. The regression sees a signal compressed by cos(theta).
        Correction factor = 1/cos(theta) = sqrt(1 + (dist/D)^2), where D is
        the estimated viewing distance (2 x screen diagonal).

        STRENGTH < 1 applies a fractional correction to avoid overshoot.
        """
        STRENGTH = 0.30  # tune 0-1: 0 = no correction, 1 = full 1/cos

        cam_x = self.screen_width * self._cam_x_norm
        cam_y = self.screen_height * self._cam_y_norm

        dx = px - cam_x
        dy = py - cam_y
        dist = math.hypot(dx, dy)

        # Surrogate viewing distance ~= 2x screen diagonal
        D = math.hypot(self.screen_width, self.screen_height) * 2.0

        # Perspective factor (1.0 at camera center, grows toward corners)
        factor = math.sqrt(1.0 + (dist / D) ** 2)
        factor = 1.0 + STRENGTH * (factor - 1.0)  # partial application

        return cam_x + dx * factor, cam_y + dy * factor

    # ------------------------------------------------------------------
    def predict(self, vector):
        # Map a 4-element eye vector to a corrected screen (x, y) coordinate.
        scaled_vec = self._scale_vector(vector)
        vp = self.poly.transform([scaled_vec])
        px = self.model_x.predict(vp)[0]
        py = self.model_y.predict(vp)[0]
        px, py = self._perspective_correction(px, py)
        return (int(px), int(py))

    # ------------------------------------------------------------------
    def save_profile(self, filepath=config.DEFAULT_PROFILE_FILE):
        # Serialise the trained model to JSON per spec section 8.
        cam_pos = {"x": 0.5, "y": 0.0}
        if config.CAMERA_FILE.exists():
            try:
                with open(config.CAMERA_FILE) as f:
                    cam_pos = json.load(f).get("position", cam_pos)
            except Exception:
                pass

        first_sample = self.collected_data[0] if self.collected_data else {}
        first_vec = first_sample.get(
            "vector", first_sample.get("landmark_vector", [0, 0, 0, 0])
        )
        n_in = len(first_vec) if first_vec else 4
        n_poly = self.poly.fit_transform(np.zeros((1, n_in))).shape[1]

        data = {
            "version": 3,
            "created": datetime.datetime.now().isoformat(),
            "screen_resolution": [self.screen_width, self.screen_height],
            "camera_position": cam_pos,
            "n_input_features": n_in,
            "n_poly_features": n_poly,
            "model_x_coef": self.model_x.coef_.tolist(),
            "model_x_intercept": float(self.model_x.intercept_),
            "model_y_coef": self.model_y.coef_.tolist(),
            "model_y_intercept": float(self.model_y.intercept_),
        }
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)

    # ------------------------------------------------------------------
    def load_profile(self, filepath=config.DEFAULT_PROFILE_FILE):
        # Restore a trained profile from JSON.
        if not filepath.exists():
            return False
        with open(filepath) as f:
            data = json.load(f)

        self.screen_width, self.screen_height = data["screen_resolution"]

        # Restore camera position for perspective correction
        cam_pos = data.get("camera_position", {"x": 0.5, "y": 0.0})
        self._cam_x_norm = float(cam_pos.get("x", 0.5))
        self._cam_y_norm = float(cam_pos.get("y", 0.0))

        n_in = data.get("n_input_features", 4)
        n_poly = data.get("n_poly_features", 15)
        self.poly.fit(np.zeros((1, n_in)))

        self.model_x = Ridge(alpha=0.1)
        self.model_y = Ridge(alpha=0.1)

        self.model_x.coef_ = np.array(data["model_x_coef"])
        self.model_x.intercept_ = data["model_x_intercept"]
        self.model_x.n_features_in_ = n_poly

        self.model_y.coef_ = np.array(data["model_y_coef"])
        self.model_y.intercept_ = data["model_y_intercept"]
        self.model_y.n_features_in_ = n_poly

        return True
