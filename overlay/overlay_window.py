import math
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
import cairo
from gi.repository import Gdk, GLib, Gtk

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.settings_manager import load_settings

ALPHA_MAP = {
    "low": 0.35,
    "medium": 0.55,
    "high": 0.75,
}


class OverlayWindow(Gtk.ApplicationWindow):
    """
    Translucent privacy overlay window.
    Draws an undecorated, maximized window with GTK CSS translucent background
    and an illuminated white sphere gaze tracker following eye movements.
    """

    def __init__(self, gaze_engine, screenshot_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = gaze_engine
        self.enabled = True
        self.paused_until = 0.0  # timestamp or -1 for indefinite

        self._css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Raw gaze target (from pipeline)
        self._target_x = 960.0
        self._target_y = 540.0

        # Visual position (interpolated towards target each tick)
        self._disp_x = 960.0
        self._disp_y = 540.0

        # Load settings and apply CSS
        self.reload_settings()

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

        alpha = ALPHA_MAP.get(self.blur_intensity, 0.55)
        css = f"""
        window, window.background, .background {{
            background-color: rgba(10, 10, 20, {alpha});
            background: rgba(10, 10, 20, {alpha});
            border: none;
            box-shadow: none;
        }}
        """
        self._css_provider.load_from_data(css.encode("utf-8"))

        if hasattr(self.engine, "reload_settings"):
            self.engine.reload_settings()

    def _setup_window(self):
        self.set_title("GazeGuard")
        self.set_decorated(False)
        self.maximize()

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
        if not self.enabled or self.is_paused():
            return

        gx = self._disp_x
        gy = self._disp_y

        # Camera disconnect safe mode
        if not self.engine.is_camera_connected():
            cr.set_source_rgba(0.04, 0.04, 0.08, 0.95)
            cr.paint()

            cr.set_source_rgba(0.85, 0.45, 0.05, 0.95)
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

        # Boss Mode absence defense
        if self.engine.is_boss_blur():
            fade_alpha = self.engine.get_boss_fade_alpha()
            # Darken screen during absence
            cr.set_source_rgba(0.04, 0.04, 0.08, 0.90 * fade_alpha)
            cr.paint()

            cr.set_source_rgba(0.1, 0.1, 0.16, 0.95 * fade_alpha)
            cr.rectangle(0, 0, width, 50)
            cr.fill()

            cr.set_source_rgba(0.9, 0.9, 1.0, fade_alpha)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(18)
            msg = "GazeGuard: Boss Mode Active — Screen secured (Absence detected)"
            ext = cr.text_extents(msg)
            cr.move_to((width - ext.width) / 2, 32)
            cr.show_text(msg)
            return

        # Multi-face security alert
        is_mf = self.multi_face_security and self.engine.is_multi_face()
        if is_mf:
            cr.set_source_rgba(0.04, 0.04, 0.08, 0.90)
            cr.paint()

            cr.set_source_rgba(0.9, 0.1, 0.1, 0.92)
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

        # Foveated illuminated white sphere gaze tracker
        size = self.focus_size

        if self.focus_shape == "circle":
            rad = size / 2.0
            pattern = cairo.RadialGradient(
                gx - rad * 0.15, gy - rad * 0.15, rad * 0.05, gx, gy, rad
            )
            pattern.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 1.0)
            pattern.add_color_stop_rgba(0.7, 0.95, 0.96, 1.0, 0.92)
            pattern.add_color_stop_rgba(1.0, 0.85, 0.88, 0.98, 0.70)
            cr.set_source(pattern)
            cr.arc(gx, gy, rad, 0, 2 * math.pi)
            cr.fill()
        else:  # Rectangle
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
            cr.rectangle(gx - size / 2, gy - size / 2, size, size)
            cr.fill()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.drawing.queue_draw()

    def do_close_request(self):
        GLib.source_remove(self._draw_id)
        return False
