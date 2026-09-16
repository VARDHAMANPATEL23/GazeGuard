import os
from pathlib import Path

# Project root and user config paths
BASE_DIR = Path(__file__).parent.absolute()
APP_NAME = "gazeguard"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
PROFILES_DIR = CONFIG_DIR / "profiles"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# File paths
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CAMERA_FILE = CONFIG_DIR / "camera.json"
HOTKEYS_FILE = CONFIG_DIR / "hotkeys.json"
DEFAULT_PROFILE_FILE = PROFILES_DIR / "default.json"

# --- Calibration Settings ---
CALIBRATION_GRID_COLS = 5
CALIBRATION_GRID_ROWS = 5  # was 4 — extra row improves vertical regression quality
CALIBRATION_COLS = CALIBRATION_GRID_COLS
CALIBRATION_ROWS = CALIBRATION_GRID_ROWS
CALIBRATION_POINTS = CALIBRATION_GRID_COLS * CALIBRATION_GRID_ROWS
IRIS_Y_SCALE_FACTOR = (
    1.4  # amplifies vertical component of iris vector before regression
)

# --- Overlay Settings ---
DEFAULT_BLUR_INTENSITY = "medium"  # low, medium, high
DEFAULT_FOCUS_SHAPE = "circle"  # circle, rectangle, strip
DEFAULT_ZONE_MODE = "small_sharp"  # small_sharp, large_soft
DEFAULT_FOCUS_SIZE = 120  # px radius or height

# --- Boss Mode Settings ---
BOSS_MODE_ENABLED = True
BOSS_MODE_GRACE_SECONDS = 3
BOSS_MODE_NOTIFY = True
BOSS_MODE_RESUME_FADE_MS = 500

# --- Reading Mode Settings ---
READING_MODE_WINDOW_FRAMES = 60
READING_MODE_MIN_DETECTIONS = 3
READING_MODE_STRIP_HEIGHT_DEFAULT = 120

# --- Hotkeys Defaults ---
DEFAULT_HOTKEYS = {
    "toggle_gazeguard": "ctrl+shift+g",
    "emergency_unblur": "ctrl+shift+space",
    "pause_10m": "ctrl+shift+p",
    "toggle_reading_mode": "ctrl+shift+r",
    "toggle_boss_mode": "ctrl+shift+b",
}
