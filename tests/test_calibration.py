"""
Unit tests for CalibrationManager (grid generation, vector extraction, train/predict).
Run: python -m pytest tests/test_calibration.py -v
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pytest
import numpy as np
from unittest.mock import MagicMock
from core.calibration import CalibrationManager
import config

SCREEN_W, SCREEN_H = 1920, 1080

@pytest.fixture
def manager():
    return CalibrationManager(SCREEN_W, SCREEN_H)

# --- Grid Generation ---

def test_grid_point_count(manager):
    expected = config.CALIBRATION_GRID_COLS * config.CALIBRATION_GRID_ROWS
    assert len(manager.grid_points) == expected

def test_grid_within_screen_bounds(manager):
    for x, y in manager.grid_points:
        assert 0 <= x <= SCREEN_W, f"x={x} out of bounds"
        assert 0 <= y <= SCREEN_H, f"y={y} out of bounds"

def test_grid_has_margin(manager):
    margin_x = SCREEN_W * 0.05
    margin_y = SCREEN_H * 0.05
    for x, y in manager.grid_points:
        assert x >= margin_x - 1
        assert y >= margin_y - 1
        assert x <= SCREEN_W - margin_x + 1
        assert y <= SCREEN_H - margin_y + 1

# --- Normalized Vector Extraction ---

def _make_mock_landmark(x, y, z=0.0):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    lm.z = z
    return lm

def _make_face_landmarks(left_iris_x, left_iris_y, right_iris_x, right_iris_y):
    """Build a minimal 478-landmark list with realistic iris positions."""
    landmarks = [_make_mock_landmark(0.3 + i * 0.0001, 0.4 + i * 0.0001) for i in range(478)]
    landmarks[468] = _make_mock_landmark(left_iris_x, left_iris_y)
    landmarks[473] = _make_mock_landmark(right_iris_x, right_iris_y)
    return landmarks

def test_vector_length(manager):
    lms = _make_face_landmarks(0.45, 0.48, 0.55, 0.48)
    vec = manager.extract_normalized_vector(lms)
    assert vec is not None
    assert len(vec) == 4

def test_vector_values_normalized_in_range(manager):
    lms = _make_face_landmarks(0.45, 0.48, 0.55, 0.48)
    vec = manager.extract_normalized_vector(lms)
    for v in vec:
        assert 0.0 <= v <= 1.0, f"Normalized value {v} out of [0, 1]"

def test_vector_returns_none_on_zero_bounding_box(manager):
    """All landmarks at the same point → zero bounding box → should return None."""
    landmarks = [_make_mock_landmark(0.5, 0.5) for _ in range(478)]
    vec = manager.extract_normalized_vector(landmarks)
    assert vec is None

# --- Training and Prediction ---

def _make_synthetic_dataset(manager):
    """Inject synthetic data: identity mapping — gaze == screen point."""
    rng = np.random.default_rng(42)
    for pt in manager.grid_points:
        # Simulate slightly jittered iris vectors for this screen point
        base_vec = [pt[0] / SCREEN_W, pt[1] / SCREEN_H,
                    pt[0] / SCREEN_W + 0.02, pt[1] / SCREEN_H]
        vectors = [
            [v + rng.uniform(-0.005, 0.005) for v in base_vec]
            for _ in range(10)
        ]
        manager.add_point_data(pt, vectors)

def test_train_returns_true(manager):
    _make_synthetic_dataset(manager)
    assert manager.train() is True

def test_train_returns_false_with_no_data():
    m = CalibrationManager(SCREEN_W, SCREEN_H)
    assert m.train() is False

def test_predict_roughly_correct(manager):
    """After training on synthetic data, predictions should be within 200px."""
    _make_synthetic_dataset(manager)
    manager.train()
    for pt in manager.grid_points:
        vec = [pt[0] / SCREEN_W, pt[1] / SCREEN_H,
               pt[0] / SCREEN_W + 0.02, pt[1] / SCREEN_H]
        px, py = manager.predict(vec)
        err = np.sqrt((px - pt[0])**2 + (py - pt[1])**2)
        assert err < 200, f"Prediction error {err:.0f}px too large at point {pt}"

def test_add_point_data_skips_empty_vectors(manager):
    before = len(manager.collected_data)
    manager.add_point_data((100, 100), [])
    assert len(manager.collected_data) == before
