import math
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
import cairo
from gi.repository import Gdk, GLib, Gtk

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.settings_manager import load_settings


class OverlayWindow(Gtk.ApplicationWindow):
    """
    Fullscreen overlay window.
    Draws foveated focus window following gaze with smooth eased movement.
    Supports dynamic settings reload, pausing, camera disconnect safe mode, and multi-face security.
    """

    def __init__(self, gaze_engine, screenshot_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = gaze_engine
        self.enabled = True
        self.paused_until = 0.0  # timestamp or -1 for indefinite

        # Load settings
        self.reload_settings()

        # Raw gaze target (from pipeline)
        self._target_x = 960.0
        self._target_y = 540.0

        # Visual position (interpolated towards target each tick)
        self._disp_x = 960.0
        self._disp_y = 540.0

        self._setup_window()
        self._draw_id = GLib.timeout_add(16, self._tick)  # ~60fps

    def reload_settings(self):
        """Reload active settings from configuration file."""
        s = load_settings()
        self.focus_shape = s.get("focus", {}).get("shape", "circle")
        self.focus_size = float(s.get("focus", {}).get("size", 120))
        self.zone_mode = s.get("focus", {}).get("zone_mode", "small_sharp")
        self.blur_intensity = s.get("blur", {}).get("intensity", "medium")
        self.multi_face_security = s.get("security", {}).get("multi_face", True)

    def _setup_window(self):
        self.set_title("GazeGuard")
        self.fullscreen()

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        drawing = Gtk.DrawingArea()
        drawing.set_draw_func(self.on_draw)
        drawing.set_hexpand(True)
        drawing.set_vexpand(True)
        self.set_child(drawing)
        self.drawing = drawing

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def is_paused(self):
        if self.paused_until == -1:
            return True
        if self.paused_until > 0:
            if time.time() < self.paused_until:
                return True
            else:
                self.paused_until = 0.0  # pause expired
        return False

    def pause(self, seconds=0):
        if seconds == 0:
            self.paused_until = -1.0  # until manually resumed
        else:
            self.paused_until = time.time() + float(seconds)
        self.drawing.queue_draw()

    def resume(self):
        self.paused_until = 0.0
        self.enabled = True
        self.drawing.queue_draw()

    def toggle(self):
        if self.is_paused() or not self.enabled:
            self.resume()
        else:
            self.enabled = False
        self.drawing.queue_draw()

    def _tick(self):
        if not self.enabled or self.is_paused():
            self.drawing.queue_draw()
            return True

        pt = self.engine.get_gaze_point()
        if pt:
            w = self.drawing.get_width()
            h = self.drawing.get_height()
            margin = self.focus_size / 2

            # Clamp target so focus region stays bounded
            tx = max(margin, min(pt[0], w - margin))
            ty = max(margin, min(pt[1], h - margin))
            self._target_x = tx
            self._target_y = ty

        # Smooth accelerated easing
        dx = self._target_x - self._disp_x
        dy = self._target_y - self._disp_y
        dist = math.hypot(dx, dy)

        if dist > 0.5:
            factor = min(0.12 + dist * 0.003, 0.5)
            self._disp_x += dx * factor
            self._disp_y += dy * factor

        self.drawing.queue_draw()
        return True

    def on_draw(self, area, cr, width, height):
        if not self.enabled:
            return

        if self.is_paused():
            # In paused state, do not obscure screen
            return

        gx = self._disp_x
        gy = self._disp_y

        # Solid privacy shield background
        cr.set_source_rgba(0, 0, 0, 1.0)
        cr.paint()

        # Camera disconnect safe mode
        if not self.engine.is_camera_connected():
            cr.set_source_rgba(0.8, 0.4, 0.0, 0.9)
            cr.rectangle(0, 0, width, 55)
            cr.fill()

            cr.set_source_rgb(1, 1, 1)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(20)
            msg = "GazeGuard: Camera Disconnected — Screen secured (Reconnecting every 5s...)"
            ext = cr.text_extents(msg)
            cr.move_to((width - ext.width) / 2, 35)
            cr.show_text(msg)
            return

        # Multi-face security alert
        is_mf = self.multi_face_security and self.engine.is_multi_face()
        if is_mf:
            # Fully obscure display with prominent security banner
            cr.set_source_rgba(0.9, 0.1, 0.1, 0.9)
            cr.rectangle(0, 0, width, 50)
            cr.fill()

            cr.set_source_rgb(1, 1, 1)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(20)
            msg = "GazeGuard: Multiple faces detected — Screen obscured for security"
            ext = cr.text_extents(msg)
            cr.move_to((width - ext.width) / 2, 32)
            cr.show_text(msg)
            return

        # Foveated clear focus window
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        size = self.focus_size

        if self.focus_shape == "circle":
            cr.arc(gx, gy, size / 2, 0, 2 * math.pi)
            cr.fill()
        else:  # Rectangle
            cr.rectangle(gx - size / 2, gy - size / 2, size, size)
            cr.fill()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.drawing.queue_draw()

    def do_close_request(self):
        GLib.source_remove(self._draw_id)
        return False
