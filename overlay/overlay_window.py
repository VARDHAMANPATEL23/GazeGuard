import sys
import math
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

sys.path.append(str(Path(__file__).parent.parent))
import config

BOX_SIZE  = 60
MARGIN    = BOX_SIZE // 2   # keep box fully on screen

class OverlayWindow(Gtk.ApplicationWindow):
    """
    Fullscreen overlay window.
    Draws a white box that follows gaze with smooth eased movement.
    """

    def __init__(self, gaze_engine, screenshot_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = gaze_engine
        self.enabled = True

        # Raw gaze target (from pipeline)
        self._target_x = 960.0
        self._target_y = 540.0

        # Visual position (interpolated towards target each tick)
        self._disp_x = 960.0
        self._disp_y = 540.0

        self._setup_window()
        self._draw_id = GLib.timeout_add(16, self._tick)  # ~60fps

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

    def _tick(self):
        if not self.enabled:
            return True

        pt = self.engine.get_gaze_point()
        if pt:
            w = self.drawing.get_width()
            h = self.drawing.get_height()

            # Clamp target so box never goes off screen
            tx = max(MARGIN, min(pt[0], w - MARGIN))
            ty = max(MARGIN, min(pt[1], h - MARGIN))
            self._target_x = tx
            self._target_y = ty

        # --- Smooth accelerated easing ---
        # Lerp factor scales with distance: faster when far, decelerates on arrival
        dx = self._target_x - self._disp_x
        dy = self._target_y - self._disp_y
        dist = math.hypot(dx, dy)

        if dist > 0.5:
            # Base speed 0.12, adds 0.003 per pixel of distance, caps at 0.5
            factor = min(0.12 + dist * 0.003, 0.5)
            self._disp_x += dx * factor
            self._disp_y += dy * factor

        self.drawing.queue_draw()
        return True

    def on_draw(self, area, cr, width, height):
        if not self.enabled:
            return

        gx = self._disp_x
        gy = self._disp_y

        # Solid black background
        cr.set_source_rgba(0, 0, 0, 1.0)
        cr.paint()

        # Box color: red if multi-face detected
        if self.engine.is_multi_face():
            cr.set_source_rgba(1.0, 0.1, 0.1, 1.0)
        else:
            cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)

        cr.rectangle(gx - BOX_SIZE/2, gy - BOX_SIZE/2, BOX_SIZE, BOX_SIZE)
        cr.fill()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.drawing.queue_draw()

    def do_close_request(self):
        GLib.source_remove(self._draw_id)
        return False
