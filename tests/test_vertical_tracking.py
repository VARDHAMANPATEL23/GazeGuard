"""
Vertical tracking regression test.
Feeds synthetic iris vectors at top/bottom screen positions and asserts
that predicted Y coordinates differ by > 40% of screen height.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest

from core.calibration import CalibrationManager


def test_vertical_range_adequate():
    """Predicted Y range when iris moves from top to bottom must be > 40% screen height."""
    screen_h = 1080
    cm = CalibrationManager(screen_width=1920, screen_height=screen_h)

    # Simulate top-row iris vector (eyes up — low Y norm value)
    top_vec = [0.5, 0.15, 0.5, 0.15]
    # Simulate bottom-row iris vector (eyes down — high Y norm value)
    bottom_vec = [0.5, 0.85, 0.5, 0.85]

    # Build minimal training data spanning full screen
    cm.calibration_data = [
        {"screen_xy": (960, 108), "landmark_vector": top_vec},
        {"screen_xy": (960, 972), "landmark_vector": bottom_vec},
        # Add midpoints to avoid degenerate model
        {"screen_xy": (960, 540), "landmark_vector": [0.5, 0.50, 0.5, 0.50]},
    ]
    cm.train_model()

    pred_top = cm.predict(top_vec)
    pred_bottom = cm.predict(bottom_vec)

    vertical_range = abs(pred_bottom[1] - pred_top[1])
    assert vertical_range > screen_h * 0.4, (
        f"Vertical range {vertical_range:.0f}px is < 40% of screen height — "
        f"vertical tracking is still broken"
    )
