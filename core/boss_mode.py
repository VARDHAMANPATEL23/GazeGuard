"""
GazeGuard — Boss Mode Module (Phase 7).
State machine for user absence detection and automatic full-screen blur protection.

States:
  ACTIVE       — User present, standard foveated gaze tracking active.
  GRACE_PERIOD — Face absent for 3 consecutive frames, counting down grace timer.
  BOSS_BLUR    — Grace timer expired, screen fully obscured.
  RESUMING     — User returned, smooth fade transition back to active gaze tracking.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.settings_manager import load_settings


class BossModeState:
    ACTIVE = "ACTIVE"
    GRACE_PERIOD = "GRACE_PERIOD"
    BOSS_BLUR = "BOSS_BLUR"
    RESUMING = "RESUMING"


class BossModeController:
    def __init__(
        self, enabled=None, grace_seconds=None, notify=None, resume_fade_ms=500
    ):
        self.enabled = True
        self.grace_seconds = 3
        self.notify = True
        self.resume_fade_ms = resume_fade_ms

        self.state = BossModeState.ACTIVE
        self.consecutive_absent = 0
        self.grace_start_time = 0.0
        self.resume_start_time = 0.0
        self._lock = threading.Lock()

        # Load persisted settings if available
        self.reload_settings()

        # If explicitly passed in constructor, override persisted settings
        if enabled is not None:
            self.enabled = enabled
        if grace_seconds is not None:
            self.grace_seconds = grace_seconds
        if notify is not None:
            self.notify = notify

    def reload_settings(self):
        """Reload configuration from ~/.config/gazeguard/settings.json."""
        with self._lock:
            try:
                s = load_settings()
                bm = s.get("boss_mode", {})
                self.enabled = bm.get("enabled", True)
                self.grace_seconds = int(bm.get("grace_seconds", 3))
                self.notify = bm.get("notify", True)
            except Exception:
                pass

    def update(self, face_count, current_time=None):
        """
        Process current frame's face count and advance state machine.
        Returns the updated state string.
        """
        now = current_time if current_time is not None else time.time()

        with self._lock:
            if not self.enabled:
                self.state = BossModeState.ACTIVE
                self.consecutive_absent = 0
                return self.state

            # Camera disconnect is handled separately by the camera pipeline
            if face_count == -1:
                return self.state

            # ── State: ACTIVE ─────────────────────────────────────────────────
            if self.state == BossModeState.ACTIVE:
                if face_count == 0:
                    self.consecutive_absent += 1
                    if self.consecutive_absent >= 3:
                        if self.grace_seconds <= 0:
                            self.state = BossModeState.BOSS_BLUR
                            self._trigger_notification(
                                "Screen secured — No face detected"
                            )
                        else:
                            self.state = BossModeState.GRACE_PERIOD
                            self.grace_start_time = now
                else:
                    self.consecutive_absent = 0

            # ── State: GRACE_PERIOD ───────────────────────────────────────────
            elif self.state == BossModeState.GRACE_PERIOD:
                if face_count >= 1:
                    # Face returned before timer expired — abort
                    self.state = BossModeState.ACTIVE
                    self.consecutive_absent = 0
                else:
                    elapsed = now - self.grace_start_time
                    if elapsed >= self.grace_seconds:
                        self.state = BossModeState.BOSS_BLUR
                        self._trigger_notification("Screen secured — No face detected")

            # ── State: BOSS_BLUR ──────────────────────────────────────────────
            elif self.state == BossModeState.BOSS_BLUR:
                if face_count >= 1:
                    # User returned — begin smooth resumption
                    self.consecutive_absent = 0
                    if self.resume_fade_ms <= 0:
                        self.state = BossModeState.ACTIVE
                    else:
                        self.state = BossModeState.RESUMING
                        self.resume_start_time = now

            # ── State: RESUMING ───────────────────────────────────────────────
            elif self.state == BossModeState.RESUMING:
                if face_count == 0:
                    # User immediately stepped away again
                    self.state = BossModeState.BOSS_BLUR
                else:
                    elapsed_ms = (now - self.resume_start_time) * 1000.0
                    if elapsed_ms >= self.resume_fade_ms:
                        self.state = BossModeState.ACTIVE

            return self.state

    def is_boss_blur(self):
        """Returns True if the screen should be fully obscured by boss mode."""
        with self._lock:
            return self.state in (BossModeState.BOSS_BLUR, BossModeState.RESUMING)

    def get_fade_alpha(self, current_time=None):
        """
        Returns the opacity multiplier of the full blur shield (0.0 to 1.0).
        0.0 = clear focus active, 1.0 = 100% obscured.
        """
        now = current_time if current_time is not None else time.time()
        with self._lock:
            if self.state == BossModeState.BOSS_BLUR:
                return 1.0
            elif self.state == BossModeState.RESUMING:
                elapsed_ms = (now - self.resume_start_time) * 1000.0
                progress = min(
                    1.0, max(0.0, elapsed_ms / max(1.0, self.resume_fade_ms))
                )
                return 1.0 - progress
            return 0.0

    def get_state(self):
        with self._lock:
            return self.state

    def reset(self):
        with self._lock:
            self.state = BossModeState.ACTIVE
            self.consecutive_absent = 0
            self.grace_start_time = 0.0
            self.resume_start_time = 0.0

    def _trigger_notification(self, message):
        if not self.notify:
            return
        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "-u",
                    "normal",
                    "-a",
                    "GazeGuard",
                    "GazeGuard: Boss Mode Triggered",
                    message,
                ]
            )
        except Exception:
            pass
