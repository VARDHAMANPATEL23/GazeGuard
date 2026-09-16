"""Unit tests for Phase 6 — Performance, Resilience, and Profile Loading."""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import config
from core.calibration import CalibrationManager


def test_profile_load_time_under_two_seconds():
    """Verify that loading the calibration profile takes well under 2.0 seconds."""
    if not config.DEFAULT_PROFILE_FILE.exists():
        # Create a dummy profile to test load time
        mgr = CalibrationManager(1920, 1080)
        mgr.train()
        mgr.save_profile(config.DEFAULT_PROFILE_FILE)

    start = time.perf_counter()
    mgr = CalibrationManager(1920, 1080)
    mgr.load_profile(config.DEFAULT_PROFILE_FILE)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"Profile loading took {elapsed:.3f}s (expected < 2.0s)"


def test_camera_disconnect_state_handling():
    """Verify that GazeEngine properly reflects camera disconnect state."""
    from core.gaze_engine import GazeEngine

    engine = GazeEngine(smoothing_level="medium")
    assert engine.is_camera_connected() is True

    # Start consumer thread only
    engine._running = True
    import threading

    engine._consumer_thread = threading.Thread(target=engine._consume_loop, daemon=True)
    engine._consumer_thread.start()

    try:
        # Simulate camera disconnect event via consumer queue
        engine.pipeline.output_queue.put((None, -1))
        time.sleep(0.2)

        assert engine.is_camera_connected() is False
        assert engine.get_gaze_point() is None
    finally:
        engine._running = False
        if engine._consumer_thread.is_alive():
            engine._consumer_thread.join(timeout=1.0)
