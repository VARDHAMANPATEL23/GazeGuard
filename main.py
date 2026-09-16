"""
GazeGuard — Main entry point.
Starts the gaze engine and overlay window.
"""
import sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from core.gaze_engine import GazeEngine
from overlay.overlay_window import OverlayWindow

def main():
    try:
        print("Initializing GazeEngine with heavy smoothing...")
        engine = GazeEngine(smoothing_level="low")
        engine.start()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Run 'python ui/setup_screen.py' and 'python ui/calibration_ui.py' first.")
        sys.exit(1)

    app = Gtk.Application(application_id="com.gazeguard.overlay")

    def on_activate(app):
        win = OverlayWindow(engine, application=app)
        win.present()

    def on_shutdown(app):
        engine.stop()

    app.connect("activate", on_activate)
    app.connect("shutdown", on_shutdown)
    app.run(sys.argv)

if __name__ == "__main__":
    main()

