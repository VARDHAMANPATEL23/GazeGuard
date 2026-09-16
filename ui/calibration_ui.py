import os
import sys
import json
import threading
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.calibration import CalibrationManager
from utils.camera import open_camera, release_camera

CSS = b"""
window { background-color: #0d0d12; }
.instruction {
    font-size: 28px;
    color: #ffffff;
    font-weight: bold;
    text-shadow: 0 4px 8px rgba(0,0,0,0.9);
}
"""

class CalibrationWizard(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("GazeGuard - Calibration")
        self.fullscreen()

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        display = Gdk.Display.get_default()
        monitor = display.get_monitors().get_item(0)
        geom = monitor.get_geometry()
        self.screen_w = geom.width
        self.screen_h = geom.height

        self.manager = CalibrationManager(self.screen_w, self.screen_h)
        self.current_idx = 0

        # Animation state (driven by 16ms timer, independent of camera)
        self.space_held = False
        self.fill_progress = 0.0   # 0.0 to 1.0
        self.point_complete = False # waiting for space release before next dot

        # Capture state (driven by 33ms camera thread)
        self.collected_vectors = []
        self.last_vector = None    # updated by camera thread safely
        self._lock = threading.Lock()

        # Overlay
        self.overlay = Gtk.Overlay()
        self.set_child(self.overlay)

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_draw_func(self.on_draw)
        self.overlay.set_child(self.drawing_area)

        self.label = Gtk.Label(label="Look at the RED DOT and HOLD SPACE")
        self.label.add_css_class("instruction")
        self.label.set_halign(Gtk.Align.CENTER)
        self.label.set_valign(Gtk.Align.END)
        self.label.set_margin_bottom(50)
        self.overlay.add_overlay(self.label)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        key_ctrl.connect("key-released", self.on_key_released)
        self.add_controller(key_ctrl)

        self.init_camera()

        # Two separate loops:
        # 1. Animation loop — 16ms (~60fps), purely redraws the ring
        self.anim_id = GLib.timeout_add(16, self.animation_tick)
        # 2. Camera loop — 33ms (~30fps), runs in a background thread
        self.cam_thread = threading.Thread(target=self.camera_loop, daemon=True)
        self.cam_thread.start()

    def init_camera(self):
        device_node = "/dev/video0"
        if config.CAMERA_FILE.exists():
            try:
                with open(config.CAMERA_FILE, 'r') as f:
                    device_node = json.load(f).get("device", "/dev/video0")
            except Exception:
                pass

        print(f"Opening camera: {device_node}")
        self.cap = cv2.VideoCapture(device_node)
        if not self.cap.isOpened():
            print(f"Cannot open camera: {device_node}")
            sys.exit(1)

        model_path = str(config.BASE_DIR / 'face_landmarker.task')
        if not os.path.exists(model_path):
            print("Missing face_landmarker.task!")
            sys.exit(1)

        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path),
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        self._running = True

    def camera_loop(self):
        """Runs in a background thread. Reads frames and updates last_vector."""
        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.detector.detect(mp_img)
            if result.face_landmarks:
                vec = self.manager.extract_normalized_vector(result.face_landmarks[0])
                with self._lock:
                    self.last_vector = vec

    def animation_tick(self):
        """Runs on the GTK main thread at ~60fps. Handles all animation and capture logic."""
        if self.current_idx >= len(self.manager.grid_points):
            return True

        if self.space_held and not self.point_complete:
            # 1/150 per frame at ~60fps → fills in ~2.5 seconds
            self.fill_progress = min(1.0, self.fill_progress + (1.0 / 150.0))

            # Only sample iris data in the stable 40-90% window
            if 0.4 <= self.fill_progress <= 0.9:
                with self._lock:
                    vec = self.last_vector
                if vec:
                    self.collected_vectors.append(vec)

            if self.fill_progress >= 1.0:
                self._complete_point()

        self.drawing_area.queue_draw()
        return True

    def _complete_point(self):
        """Commit this point's data only if vectors were actually collected."""
        self.point_complete = True
        self.space_held = False

        if self.collected_vectors:
            point = self.manager.grid_points[self.current_idx]
            self.manager.add_point_data(point, self.collected_vectors)
            print(f"Captured point {self.current_idx + 1}/{len(self.manager.grid_points)}")
        else:
            # No face detected during capture window — reset this point silently
            print(f"No iris data for point {self.current_idx + 1} — will retry.")
            self.point_complete = False
            self.fill_progress = 0.0
            self.label.set_label("No face detected. Look at the dot and HOLD SPACE again.")
            self.collected_vectors = []
            return

        self.collected_vectors = []
        self.current_idx += 1
        self.label.set_label("Release SPACE, then look at the next dot.")

        if self.current_idx >= len(self.manager.grid_points):
            GLib.idle_add(self.finish_calibration)

    def on_draw(self, area, cr, width, height):
        # Draw grid lines
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.set_line_width(1.5)
        cols = config.CALIBRATION_GRID_COLS
        rows = config.CALIBRATION_GRID_ROWS
        pts = self.manager.grid_points

        if len(pts) == cols * rows:
            for r in range(rows):
                s, e = pts[r * cols], pts[r * cols + cols - 1]
                cr.move_to(s[0], s[1])
                cr.line_to(e[0], e[1])
                cr.stroke()
            for c in range(cols):
                s, e = pts[c], pts[(rows - 1) * cols + c]
                cr.move_to(s[0], s[1])
                cr.line_to(e[0], e[1])
                cr.stroke()

        if self.current_idx >= len(pts):
            cr.set_source_rgb(0.2, 0.8, 0.2)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(60)
            text = "Calibration Complete!"
            ext = cr.text_extents(text)
            cr.move_to((width - ext.width) / 2, height / 2)
            cr.show_text(text)
            return

        tx, ty = pts[self.current_idx]

        # Central dot
        cr.set_source_rgb(1.0, 0.2, 0.2)
        cr.arc(tx, ty, 12, 0, 2 * np.pi)
        cr.fill()

        # Static outer ring
        cr.set_source_rgba(1.0, 0.2, 0.2, 0.25)
        cr.set_line_width(2)
        cr.arc(tx, ty, 36, 0, 2 * np.pi)
        cr.stroke()

        # Animated green fill ring
        if self.fill_progress > 0:
            cr.set_source_rgb(0.2, 1.0, 0.4)
            cr.set_line_width(7)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            start = -np.pi / 2
            end = start + 2 * np.pi * self.fill_progress
            cr.arc(tx, ty, 36, start, end)
            cr.stroke()

    def on_key_pressed(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_space:
            if not self.point_complete and not self.space_held:
                if self.current_idx < len(self.manager.grid_points):
                    self.space_held = True
                    self.fill_progress = 0.0
                    self.collected_vectors = []
                    self.label.set_label("Hold SPACE — keep looking at the dot...")
            return True
        elif keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def on_key_released(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_space:
            if self.point_complete:
                # User released after completion — ready for next dot
                self.point_complete = False
                self.fill_progress = 0.0
                if self.current_idx < len(self.manager.grid_points):
                    self.label.set_label("Look at the RED DOT and HOLD SPACE")
            else:
                # Cancelled — reset the ring
                self.space_held = False
                self.fill_progress = 0.0
                self.collected_vectors = []
                self.label.set_label("Look at the RED DOT and HOLD SPACE")
                self.drawing_area.queue_draw()
            return True
        return False

    def finish_calibration(self):
        self.label.set_label("Training model... Please wait.")
        if self.manager.train():
            self.manager.save_profile()
            print("Profile saved.")
        self.label.set_label("Done! Window will close shortly.")
        GLib.timeout_add_seconds(3, self.close)

    def do_close_request(self):
        # Stop the camera thread first, then release resources safely
        self._running = False
        if hasattr(self, 'cam_thread') and self.cam_thread.is_alive():
            self.cam_thread.join(timeout=2.0)
        if hasattr(self, 'anim_id'):
            GLib.source_remove(self.anim_id)
        if hasattr(self, 'cap'):
            release_camera(self.cap)
        if hasattr(self, 'detector'):
            self.detector.close()
        return False

def main():
    app = Gtk.Application(application_id='com.gazeguard.calib')
    app.connect('activate', lambda a: CalibrationWizard(application=a).present())
    app.run(sys.argv)

if __name__ == '__main__':
    main()
