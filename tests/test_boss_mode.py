"""Unit tests for Phase 7 — Boss Mode (Absence Detection & State Machine)."""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from core.boss_mode import BossModeController, BossModeState


def test_initial_state_is_active():
    bm = BossModeController(enabled=True, grace_seconds=3, notify=False)
    assert bm.get_state() == BossModeState.ACTIVE
    assert bm.is_boss_blur() is False
    assert bm.get_fade_alpha() == 0.0


def test_transition_to_grace_period_after_three_frames():
    bm = BossModeController(enabled=True, grace_seconds=3, notify=False)

    # 1st and 2nd frame absence should stay ACTIVE
    assert bm.update(0, current_time=100.0) == BossModeState.ACTIVE
    assert bm.update(0, current_time=100.033) == BossModeState.ACTIVE

    # 3rd frame absence triggers GRACE_PERIOD
    assert bm.update(0, current_time=100.066) == BossModeState.GRACE_PERIOD
    assert bm.is_boss_blur() is False


def test_face_return_cancels_grace_period():
    bm = BossModeController(enabled=True, grace_seconds=3, notify=False)
    bm.update(0, current_time=100.0)
    bm.update(0, current_time=100.033)
    bm.update(0, current_time=100.066)
    assert bm.get_state() == BossModeState.GRACE_PERIOD

    # Face returns at 101.0s (before 3s grace expires)
    assert bm.update(1, current_time=101.0) == BossModeState.ACTIVE
    assert bm.is_boss_blur() is False


def test_grace_period_expiration_triggers_boss_blur():
    bm = BossModeController(enabled=True, grace_seconds=3, notify=False)
    bm.update(0, current_time=100.0)
    bm.update(0, current_time=100.033)
    bm.update(0, current_time=100.066)
    assert bm.get_state() == BossModeState.GRACE_PERIOD

    # 2 seconds later — still in grace period
    assert bm.update(0, current_time=102.0) == BossModeState.GRACE_PERIOD
    assert bm.is_boss_blur() is False

    # 3.1 seconds later — grace expired, transitions to BOSS_BLUR
    assert bm.update(0, current_time=103.1) == BossModeState.BOSS_BLUR
    assert bm.is_boss_blur() is True
    assert bm.get_fade_alpha() == 1.0


def test_zero_second_grace_period_triggers_immediately():
    bm = BossModeController(enabled=True, grace_seconds=0, notify=False)
    bm.update(0, current_time=100.0)
    bm.update(0, current_time=100.033)
    # On 3rd absent frame with grace=0, should jump straight to BOSS_BLUR
    assert bm.update(0, current_time=100.066) == BossModeState.BOSS_BLUR
    assert bm.is_boss_blur() is True


def test_resuming_fade_transition_when_face_returns():
    bm = BossModeController(
        enabled=True, grace_seconds=0, notify=False, resume_fade_ms=500
    )
    bm.update(0, current_time=100.0)
    bm.update(0, current_time=100.033)
    bm.update(0, current_time=100.066)
    assert bm.get_state() == BossModeState.BOSS_BLUR

    # User face reappears at t = 105.0s
    assert bm.update(1, current_time=105.0) == BossModeState.RESUMING
    assert bm.is_boss_blur() is True  # still obscuring while fading
    assert 0.0 < bm.get_fade_alpha(current_time=105.25) < 1.0  # halfway faded

    # After 500ms (t = 105.51s), state should be ACTIVE
    assert bm.update(1, current_time=105.51) == BossModeState.ACTIVE
    assert bm.is_boss_blur() is False
    assert bm.get_fade_alpha() == 0.0


def test_disabled_boss_mode_ignores_absence():
    bm = BossModeController(enabled=False, grace_seconds=0, notify=False)
    for _ in range(10):
        assert bm.update(0, current_time=100.0) == BossModeState.ACTIVE
    assert bm.is_boss_blur() is False
