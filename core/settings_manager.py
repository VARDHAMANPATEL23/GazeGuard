"""
Settings Manager for GazeGuard.
Handles persistent configuration in ~/.config/gazeguard/settings.json.
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.ipc import send_ipc_command

DEFAULT_SETTINGS = {
    "camera": {"device": "/dev/video0"},
    "focus": {
        "shape": config.DEFAULT_FOCUS_SHAPE,
        "zone_mode": config.DEFAULT_ZONE_MODE,
        "size": config.DEFAULT_FOCUS_SIZE,
    },
    "blur": {"intensity": config.DEFAULT_BLUR_INTENSITY, "smoothing": "medium"},
    "security": {"multi_face": True},
    "boss_mode": {
        "enabled": config.BOSS_MODE_ENABLED,
        "grace_seconds": config.BOSS_MODE_GRACE_SECONDS,
        "notify": config.BOSS_MODE_NOTIFY,
    },
    "reading_mode": {
        "enabled": False,
        "strip_height": config.READING_MODE_STRIP_HEIGHT_DEFAULT,
    },
    "hotkeys": config.DEFAULT_HOTKEYS.copy(),
}


def _deep_merge(source, destination):
    """Deeply merges source dictionary into destination dictionary."""
    for key, value in source.items():
        if (
            isinstance(value, dict)
            and key in destination
            and isinstance(destination[key], dict)
        ):
            _deep_merge(value, destination[key])
        elif key not in destination:
            destination[key] = value
    return destination


def load_settings(filepath=config.SETTINGS_FILE):
    """
    Load settings from JSON file. If file does not exist or has missing keys,
    fills in defaults and persists the file.
    """
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if filepath.exists():
        try:
            with open(filepath, "r") as f:
                user_data = json.load(f)
            if isinstance(user_data, dict):
                _deep_merge(settings, user_data)
                settings = user_data
        except Exception:
            pass

    # Ensure settings file exists
    save_settings(settings, filepath=filepath, notify_overlay=False)
    return settings


def save_settings(settings_dict, filepath=config.SETTINGS_FILE, notify_overlay=True):
    """Persist settings to JSON and notify running overlay engine if active."""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(settings_dict, f, indent=4)

        if notify_overlay:
            send_ipc_command("RELOAD_SETTINGS")
        return True
    except Exception as e:
        print(f"Error saving settings to {filepath}: {e}")
        return False


def get_setting(key_path, default=None, filepath=config.SETTINGS_FILE):
    """Retrieve setting value by dot-delimited path, e.g. 'focus.size'."""
    settings = load_settings(filepath)
    keys = key_path.split(".")
    val = settings
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def update_setting(key_path, value, filepath=config.SETTINGS_FILE, notify_overlay=True):
    """Update setting value by dot-delimited path, e.g. 'focus.size'."""
    settings = load_settings(filepath)
    keys = key_path.split(".")
    target = settings
    for k in keys[:-1]:
        if k not in target or not isinstance(target[k], dict):
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value
    return save_settings(settings, filepath=filepath, notify_overlay=notify_overlay)
