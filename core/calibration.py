import json
import math
import numpy as np
import datetime
import sys
from pathlib import Path
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import RidgeCV

sys.path.append(str(Path(__file__).parent.parent))
import config

# Minimum eye-openness ratio to trust iris data (blink gate)
BLINK_EAR_THRESHOLD = 0.15


class CalibrationManager:
    def __init__(self, screen_width, screen_height):
        self.screen_width  = screen_width
        self.screen_height = screen_height

        self.poly = PolynomialFeatures(degree=2, include_bias=True)
        alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
        self.model_x = RidgeCV(alphas=alphas, cv=5)
        self.model_y = RidgeCV(alphas=alphas, cv=5)

        self.grid_points   = self._generate_grid()
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
    def _generate_grid(self, cols=config.CALIBRATION_GRID_COLS,
                       rows=config.CALIBRATION_GRID_ROWS, margin=0.05):
        """Generates an evenly spaced grid of screen calibration points."""
        points = []
        mx = self.screen_width  * margin
        my = self.screen_height * margin
        uw = self.screen_width  - 2 * mx
        uh = self.screen_height - 2 * my
        xs = uw / (cols - 1) if cols > 1 else 0
        ys = uh / (rows - 1) if rows > 1 else 0
        for r in range(rows):
            for c in range(cols):
                points.append((int(mx + c * xs), int(my + r * ys)))
        return points

    # ------------------------------------------------------------------
    def extract_normalized_vector(self, face_landmarks):
        """
        Returns a 7-element hybrid feature vector:
            [eye_a_x, eye_a_y, eye_b_x, eye_b_y, face_ay, face_by, convergence]

        - eye_*_x: iris X within eye socket (strong, head-pose invariant)
        - eye_*_y: iris Y within eye socket (weak vertical, corrects head tilt)
        - face_ay/by: iris Y relative to full face height (STRONG vertical signal)
        - convergence: normalized distance between both irises (handles varying focus depth)

        This hybrid approach avoids the eyelid-follows-iris problem for Y.
        Returns None when either eye is closed (blink gate).
        """
        # Face bounding box for face-relative normalization
        ys = [lm.y for lm in face_landmarks]
        face_min_y = min(ys)
        face_h     = max(ys) - face_min_y

        xs = [lm.x for lm in face_landmarks]
        face_w     = max(xs) - min(xs)

        if face_h == 0 or face_w == 0:
            return None

        def _socket(iris_idx, inner_idx, outer_idx, top_idx, bot_idx):
            iris  = face_landmarks[iris_idx]
            inner = face_landmarks[inner_idx]
            outer = face_landmarks[outer_idx]
            top   = face_landmarks[top_idx]
            bot   = face_landmarks[bot_idx]

            eye_w = abs(outer.x - inner.x)
            eye_h = abs(bot.y   - top.y)

            # Blink gate
            if eye_h < BLINK_EAR_THRESHOLD * eye_w:
                return None, None, None

            ix       = (iris.x - min(inner.x, outer.x)) / max(eye_w, 1e-6)
            iy       = (iris.y - top.y)                 / max(eye_h, 1e-6)
            face_iy  = (iris.y - face_min_y)            / max(face_h, 1e-6)
            return ix, iy, face_iy

        # Eye A - iris 468, corners 33/133, eyelids 159/145
        ax, ay, face_ay = _socket(468, 33, 133, 159, 145)
        if ax is None:
            return None

        # Eye B - iris 473, corners 263/362, eyelids 386/374
        bx, by, face_by = _socket(473, 263, 362, 386, 374)
        if bx is None:
            return None

        # Convergence: normalized distance between both irises
        iris_a_x = face_landmarks[468].x
        iris_b_x = face_landmarks[473].x
        convergence = abs(iris_a_x - iris_b_x) / max(face_w, 1e-6)

        # face_ay and face_by carry the strong vertical signal
        return [ax, ay, bx, by, face_ay, face_by, convergence]

    # ------------------------------------------------------------------
    def add_point_data(self, screen_point, vectors):
        # Average incoming vectors for this calibration point.
        if not vectors:
            return
        self.collected_data.append({
            'point':  screen_point,
            'vector': np.mean(vectors, axis=0).tolist()
        })

    def add_continuous_sample(self, screen_point, vector):
        # Append one frame directly - used by continuous-path calibration.
        self.collected_data.append({'point': screen_point, 'vector': vector})

    # ------------------------------------------------------------------
    def train(self):
        # Fit RidgeCV models (alpha auto-selected via cross-validation).
        if len(self.collected_data) < 6:
            return False
        X   = [d['vector']   for d in self.collected_data]
        y_x = [d['point'][0] for d in self.collected_data]
        y_y = [d['point'][1] for d in self.collected_data]
        Xp  = self.poly.fit_transform(X)
        self.model_x.fit(Xp, y_x)
        self.model_y.fit(Xp, y_y)
        return True

    # ------------------------------------------------------------------
    def _perspective_correction(self, px, py):
        """
        Correct for perspective foreshortening at high gaze angles.

        Physics: camera sits at (cam_x, cam_y) on screen. When the user
        looks at angle theta from the camera axis, the iris moves by d * tan(theta)
        in screen space.  The regression sees a signal compressed by cos(theta).
        Correction factor = 1/cos(theta) = sqrt(1 + (dist/D)^2), where D is
        the estimated viewing distance (2 x screen diagonal).

        STRENGTH < 1 applies a fractional correction to avoid overshoot.
        """
        STRENGTH = 0.30   # tune 0-1: 0 = no correction, 1 = full 1/cos

        cam_x = self.screen_width  * self._cam_x_norm
        cam_y = self.screen_height * self._cam_y_norm

        dx   = px - cam_x
        dy   = py - cam_y
        dist = math.hypot(dx, dy)

        # Surrogate viewing distance ~= 2x screen diagonal
        D = math.hypot(self.screen_width, self.screen_height) * 2.0

        # Perspective factor (1.0 at camera center, grows toward corners)
        factor = math.sqrt(1.0 + (dist / D) ** 2)
        factor = 1.0 + STRENGTH * (factor - 1.0)  # partial application

        return cam_x + dx * factor, cam_y + dy * factor

    # ------------------------------------------------------------------
    def predict(self, vector):
        # Map a 6-element eye vector to a corrected screen (x, y) coordinate.
        vp = self.poly.transform([vector])
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

        n_in = len(self.collected_data[0]['vector']) if self.collected_data else 6
        n_poly = self.poly.fit_transform(np.zeros((1, n_in))).shape[1]

        data = {
            "version":           3,
            "created":           datetime.datetime.now().isoformat(),
            "screen_resolution": [self.screen_width, self.screen_height],
            "camera_position":   cam_pos,
            "n_input_features":  len(self.collected_data[0]['vector']) if self.collected_data else 6,
            "n_poly_features":   n_poly,
            "model_x_coef":      self.model_x.coef_.tolist(),
            "model_x_intercept": float(self.model_x.intercept_),
            "model_y_coef":      self.model_y.coef_.tolist(),
            "model_y_intercept": float(self.model_y.intercept_),
        }
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
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

        n_in   = data.get("n_input_features", 4)
        n_poly = data.get("n_poly_features",  15)
        self.poly.fit(np.zeros((1, n_in)))

        alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
        self.model_x = RidgeCV(alphas=alphas)
        self.model_y = RidgeCV(alphas=alphas)

        self.model_x.coef_          = np.array(data["model_x_coef"])
        self.model_x.intercept_     = data["model_x_intercept"]
        self.model_x.n_features_in_ = n_poly

        self.model_y.coef_          = np.array(data["model_y_coef"])
        self.model_y.intercept_     = data["model_y_intercept"]
        self.model_y.n_features_in_ = n_poly

        return True
