"""
GazeGuard — Main entry point.
Starts the gaze engine, overlay window, IPC server, and system tray.
Includes graceful startup: automatically triggers calibration if profile is missing.
"""

import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import config
from core.gaze_engine import GazeEngine
from core.ipc import IPCServer, is_service_running
from core.settings_manager import load_settings
from overlay.overlay_window import OverlayWindow


def main():
    settings = load_settings()

    # Graceful startup: Verify calibration profile exists, or launch calibration wizard
    if not config.DEFAULT_PROFILE_FILE.exists():
        print(
            "No calibration profile found. Launching Continuous Calibration Wizard..."
        )
        cal_script = str(config.BASE_DIR / "ui" / "continuous_calibration_ui.py")
        try:
            proc = subprocess.Popen([sys.executable, cal_script])
            proc.wait()
        except Exception as e:
            print(f"Error launching calibration wizard: {e}")

        if not config.DEFAULT_PROFILE_FILE.exists():
            print("Calibration wizard closed without saving a profile. Exiting.")
            sys.exit(0)
        print("Profile generated successfully! Resuming GazeGuard startup...")

    # Initialize GazeEngine
    smoothing = settings.get("blur", {}).get("smoothing", "medium")
    print(f"Initializing GazeEngine with smoothing='{smoothing}'...")
    try:
        engine = GazeEngine(smoothing_level=smoothing)
        engine.start()
    except Exception as e:
        print(f"ERROR starting GazeEngine: {e}")
        sys.exit(1)

    app = Gtk.Application(application_id="com.gazeguard.overlay")

    overlay_win = None
    tray_proc = None

    def ipc_command_handler(cmd):
        nonlocal overlay_win
        parts = cmd.split(":")
        action = parts[0].upper()

        if action == "PING":
            return "PONG"

        elif action == "STATUS":
            if not overlay_win or not overlay_win.enabled:
                return "DISABLED"
            if overlay_win.is_paused():
                return "PAUSED"
            return "ACTIVE"

        elif action == "TOGGLE":
            if overlay_win:
                GLib.idle_add(overlay_win.toggle)
            return "OK"

        elif action == "ENABLE":
            if overlay_win:
                GLib.idle_add(lambda: overlay_win.set_enabled(True))
            return "OK"

        elif action == "DISABLE":
            if overlay_win:
                GLib.idle_add(lambda: overlay_win.set_enabled(False))
            return "OK"

        elif action == "PAUSE":
            secs = int(parts[1]) if len(parts) > 1 else 0
            if overlay_win:
                GLib.idle_add(lambda: overlay_win.pause(secs))
            return "OK"

        elif action == "RESUME":
            if overlay_win:
                GLib.idle_add(overlay_win.resume)
            return "OK"

        elif action == "RELOAD_SETTINGS":
            if overlay_win:
                GLib.idle_add(overlay_win.reload_settings)
            return "OK"

        elif action == "QUIT":
            GLib.idle_add(app.quit)
            return "OK"

        return "UNKNOWN_CMD"

    # Start IPC Server
    ipc_server = IPCServer(command_handler=ipc_command_handler)
    if not ipc_server.start():
        print("Another GazeGuard instance is already running.")
        engine.stop()
        sys.exit(0)

    # Spawn tray in background if not already active
    try:
        tray_script = str(config.BASE_DIR / "ui" / "tray.py")
        tray_proc = subprocess.Popen([sys.executable, tray_script])
    except Exception as e:
        print(f"Note: Could not start system tray: {e}")

    def on_activate(application):
        nonlocal overlay_win
        overlay_win = OverlayWindow(engine, application=application)
        overlay_win.present()

    def on_shutdown(application):
        nonlocal tray_proc
        print("Shutting down GazeGuard...")
        engine.stop()
        ipc_server.stop()
        if tray_proc and tray_proc.poll() is None:
            tray_proc.terminate()

    app.connect("activate", on_activate)
    app.connect("shutdown", on_shutdown)

    try:
        app.run(sys.argv)
    finally:
        ipc_server.stop()
        engine.stop()


if __name__ == "__main__":
    main()
