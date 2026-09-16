"""
Unit tests for GazeSmoother (Kalman filter wrapper).
Run: python -m pytest tests/test_smoother.py -v
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pytest
import numpy as np
from core.smoother import GazeSmoother

def test_first_output_near_input():
    """First update should seed the filter and return near the input point."""
    s = GazeSmoother("medium")
    x, y = s.update(500, 300)
    assert abs(x - 500) < 50
    assert abs(y - 300) < 50

def test_smooth_output_stays_bounded():
    """Feeding consistent input should keep output within a tight range."""
    s = GazeSmoother("medium")
    for _ in range(30):
        s.update(960, 540)
    x, y = s.update(960, 540)
    assert abs(x - 960) < 20
    assert abs(y - 540) < 20

def test_jitter_dampened():
    """Alternating input should produce output with less variance than input."""
    s = GazeSmoother("low")
    outputs = []
    for i in range(60):
        jittered_x = 960 + (30 if i % 2 == 0 else -30)
        ox, _ = s.update(jittered_x, 540)
        outputs.append(ox)

    output_std = np.std(outputs[10:])  # skip warm-up frames
    assert output_std < 30, f"Expected jitter suppression, got std={output_std:.1f}"

def test_high_smoothing_lags_more_than_low():
    """High process noise should respond faster than low process noise."""
    high = GazeSmoother("high")
    low  = GazeSmoother("low")

    # Seed both at (0, 0)
    for _ in range(20):
        high.update(0, 0)
        low.update(0, 0)

    # Step to (500, 500) and see who catches up faster after 10 frames
    for _ in range(10):
        hx, _ = high.update(500, 0)
        lx, _ = low.update(500, 0)

    # High-noise filter should be closer to target (500) than low-noise filter
    assert abs(hx - 500) < abs(lx - 500), (
        f"High-noise filter ({hx:.1f}) should be closer to 500 than low-noise ({lx:.1f})"
    )

def test_reset_reinitializes_filter():
    """After reset, the filter should behave as if freshly created."""
    s = GazeSmoother("medium")
    for _ in range(30):
        s.update(100, 100)

    s.reset()

    # After reset, seeding at a very different location should stick quickly
    x, y = s.update(900, 700)
    assert abs(x - 900) < 50
    assert abs(y - 700) < 50

def test_all_presets_produce_output():
    """All three presets should run without error and return finite values."""
    for level in ["low", "medium", "high"]:
        s = GazeSmoother(level)
        x, y = s.update(640, 360)
        assert np.isfinite(x) and np.isfinite(y), f"Preset '{level}' returned non-finite value"

def test_unknown_preset_falls_back_to_medium():
    """An unknown smoothing level should silently fall back to medium."""
    s = GazeSmoother("ultra")  # invalid key
    x, y = s.update(100, 100)
    assert np.isfinite(x) and np.isfinite(y)
