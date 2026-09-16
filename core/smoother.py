import numpy as np
from filterpy.kalman import KalmanFilter

# Process noise presets — much lower Q = heavier smoothing, less jitter
NOISE_PRESETS = {
    "low":     0.5,  # Very heavy smoothing, slow but ultra-stable
    "medium":  2.0,  # Balanced
    "high":   10.0,  # Responsive but might jitter
}

class GazeSmoother:
    def __init__(self, smoothing_level="medium"):
        q = NOISE_PRESETS.get(smoothing_level, NOISE_PRESETS["medium"])
        self.kf = self._build_filter(q)
        self._initialized = False

    def _build_filter(self, q):
        # State: [x, y, dx, dy]; Measurement: [x, y]
        kf = KalmanFilter(dim_x=4, dim_z=2)

        # State transition: constant velocity model
        dt = 1.0
        kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1,  0],
            [0, 0, 0,  1],
        ], dtype=float)

        # Measurement matrix: observe only position
        kf.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=float)

        # Process noise
        kf.Q = np.eye(4) * q

        # Measurement noise
        # Asymmetric noise: Eyelids cause more vertical noise, so we trust raw Y less
        kf.R = np.array([
            [400,   0],    # X-axis variance
            [  0, 800],    # Y-axis variance (double smoothing on vertical)
        ], dtype=float)

        # Initial covariance
        kf.P = np.eye(4) * 1000.0

        return kf

    def update(self, x, y):
        """Feed a raw gaze point; returns the smoothed (x, y)."""
        if not self._initialized:
            # Seed the filter at the first measurement position
            self.kf.x = np.array([[x], [y], [0.0], [0.0]], dtype=float)
            self._initialized = True
        
        self.kf.predict()
        self.kf.update(np.array([[x], [y]], dtype=float))
        
        sx = float(self.kf.x[0, 0])
        sy = float(self.kf.x[1, 0])
        return (sx, sy)

    def reset(self):
        self._initialized = False
