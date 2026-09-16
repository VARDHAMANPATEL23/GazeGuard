#!/usr/bin/env python3
"""
Continuous-path calibration for GazeGuard.

The user follows a moving box along a predetermined path covering all screen
regions. Dense frame-by-frame sampling gives ~1000+ training samples vs. 20
from static grid calibration.

Path (normalised):
  below-camera → top-right → bottom-right → top-left (diagonal) →
  bottom-left → bottom-right → top-right → back to start
"""

import sys
import cv2
import json
import queue
import threading
import numpy as np
import math
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.calibration import CalibrationManager
from utils.camera import open_camera, release_camera

# ── Path definition ──────────────────────────────────────────────────────────
# Normalized (x, y) waypoints. 0,0 = top-left, 1,1 = bottom-right
# Comprehensive coverage path (normalised x, y — 0,0=top-left 1,1=bottom-right)
#
# Phase 1: Full clockwise perimeter — all 4 corners + all 4 edge midpoints
# Phase 2: Both full diagonals through centre
# Phase 3: Return to start
PATH_NORM = [
    # ── Phase 1: Perimeter (clockwise from top-center) ──────────────────
    (0.50, 0.05),   # Start — top-mid (nearest to camera)
    (0.95, 0.05),   # Top-right corner
    (0.95, 0.50),   # Right-mid edge
    (0.95, 0.95),   # Bottom-right corner
    (0.50, 0.95),   # Bottom-mid edge
    (0.05, 0.95),   # Bottom-left corner
    (0.05, 0.50),   # Left-mid edge
    (0.05, 0.05),   # Top-left corner
    (0.50, 0.05),   # Top-mid edge (perimeter complete)

    # ── Phase 2: Diagonals through centre ───────────────────────────────
    (0.50, 0.50),   # Centre
    (0.95, 0.95),   # Diagonal 1: centre → bottom-right
    (0.05, 0.05),   # Diagonal 1: full sweep → top-left
    (0.50, 0.50),   # Centre
    (0.05, 0.95),   # Diagonal 2: centre → bottom-left
    (0.95, 0.05),   # Diagonal 2: full sweep → top-right
    (0.50, 0.50),   # Centre

    # ── Phase 3: Return ─────────────────────────────────────────────────
    (0.50, 0.05),   # Back to start
]

SPEED_PX_SEC      = 160    # px/s between waypoints
WAYPOINT_PAUSE_MS = 2500   # ms the box holds still at each waypoint
BOX_SIZE          = 44
COUNTDOWN         = 3
FPS_MS            = 33



class ContinuousCalibrationWindow(Gtk.ApplicationWindow):

    def __init__(self, screen_w, screen_h, cal_manager, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sw  = screen_w
        self.sh  = screen_h
        self.mgr = cal_manager

        # Convert normalised path → pixel path
        self._path_px   = [(int(x * screen_w), int(y * screen_h)) for x, y in PATH_NORM]
        self._cum_dists = self._build_cum_dists()
        self._total     = self._cum_dists[-1]

        # Segment-based movement state
        self._seg      = 0
        self._seg_t    = 0.0
        self._seg_dur  = self._seg_duration(0)
        self._bx       = float(self._path_px[0][0])
        self._by       = float(self._path_px[0][1])
        self._holding  = False
        self._hold_ms  = 0
        self._paused   = False
        self._cdown    = COUNTDOWN
        self._phase    = "countdown"

        # Camera
        self._vqueue   = queue.Queue(maxsize=4)
        self._cam_live = False

        # Window
        self.set_title("GazeGuard — Continuous Calibration")
        self.fullscreen()
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_key)
        self.add_controller(kc)

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        self._canvas.set_hexpand(True)
        self._canvas.set_vexpand(True)
        self.set_child(self._canvas)

        self._tick_id  = GLib.timeout_add(FPS_MS,  self._tick)
        self._cdown_id = GLib.timeout_add(1000, self._cdown_tick)

    # ── Path math ─────────────────────────────────────────────────────────────

    def _build_cum_dists(self):
        d = [0.0]
        for i in range(1, len(self._path_px)):
            x0, y0 = self._path_px[i - 1]
            x1, y1 = self._path_px[i]
            d.append(d[-1] + math.hypot(x1 - x0, y1 - y0))
        return d

    def _seg_duration(self, idx):
        """Travel time in seconds for one path segment."""
        x0, y0 = self._path_px[idx]
        x1, y1 = self._path_px[idx + 1]
        return math.hypot(x1 - x0, y1 - y0) / SPEED_PX_SEC

    def _progress(self):
        """Overall completion 0.0–1.0 for the progress bar."""
        done_dist = self._cum_dists[self._seg]
        seg_dist  = self._cum_dists[self._seg + 1] - self._cum_dists[self._seg]
        return (done_dist + seg_dist * min(self._seg_t / max(self._seg_dur, 1e-6), 1)) / self._total

    # ── Timers ────────────────────────────────────────────────────────────────

    def _cdown_tick(self):
        if self._phase != "countdown":
            return False
        self._cdown -= 1
        if self._cdown <= 0:
            self._phase = "running"
            self._start_camera()
            return False
        self._canvas.queue_draw()
        return True

    def _tick(self):
        if self._phase == "running" and not self._paused:
            if self._holding:
                # Box is paused at waypoint — still collect (stable position = good data)
                self._hold_ms -= FPS_MS
                if self._hold_ms <= 0:
                    self._holding = False
                    self._seg    += 1
                    if self._seg >= len(self._path_px) - 1:
                        self._phase = "done"
                        self._finish()
                        return False
                    self._seg_t   = 0.0
                    self._seg_dur = self._seg_duration(self._seg)
            else:
                self._seg_t += FPS_MS / 1000.0
                t = min(self._seg_t / max(self._seg_dur, 1e-6), 1.0)
                x0, y0 = self._path_px[self._seg]
                x1, y1 = self._path_px[self._seg + 1]
                self._bx = x0 + t * (x1 - x0)
                self._by = y0 + t * (y1 - y0)

                if self._seg_t >= self._seg_dur:
                    # Snap to exact waypoint and begin hold
                    self._bx      = float(x1)
                    self._by      = float(y1)
                    self._holding = True
                    self._hold_ms = WAYPOINT_PAUSE_MS

            # Collect iris sample (even during waypoint hold)
            try:
                vec = self._vqueue.get_nowait()
                if vec:
                    self.mgr.add_continuous_sample(
                        (int(self._bx), int(self._by)), vec
                    )
            except queue.Empty:
                pass

        self._canvas.queue_draw()
        return True

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self, area, cr, w, h):
        cr.set_source_rgb(0.04, 0.04, 0.06)
        cr.paint()

        if self._phase == "countdown":
            self._draw_countdown(cr, w, h)
        elif self._phase == "running":
            self._draw_path_trace(cr)
            self._draw_box(cr)
            self._draw_hud(cr, w, h)
        elif self._phase == "done":
            self._draw_complete(cr, w, h)

    def _draw_path_trace(self, cr):
        cr.set_source_rgba(1, 1, 1, 0.06)
        cr.set_line_width(1)
        pts = self._path_px
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.stroke()

    def _draw_box(self, cr):
        half = BOX_SIZE / 2
        if self._holding:
            # Pulsing amber ring when holding at waypoint
            cr.set_source_rgba(1.0, 0.75, 0.2, 0.25)
            cr.arc(self._bx, self._by, BOX_SIZE + 14, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.75, 0.2, 1.0)
        else:
            cr.set_source_rgba(1, 1, 1, 0.12)
            cr.arc(self._bx, self._by, BOX_SIZE + 10, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
        cr.rectangle(self._bx - half, self._by - half, BOX_SIZE, BOX_SIZE)
        cr.fill()

    def _draw_countdown(self, cr, w, h):
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_source_rgb(1, 1, 1)
        cr.set_font_size(130)
        num = str(max(self._cdown, 1))
        e = cr.text_extents(num)
        cr.move_to(w / 2 - e.width / 2, h / 2 + e.height / 2)
        cr.show_text(num)

        cr.set_font_size(22)
        cr.set_source_rgba(0.8, 0.8, 0.8, 0.9)
        lines = [
            "Follow the white box with your EYES only.",
            "Keep your head completely still.",
            "Blink normally.",
        ]
        for i, line in enumerate(lines):
            e2 = cr.text_extents(line)
            cr.move_to(w / 2 - e2.width / 2, h * 0.68 + i * 34)
            cr.show_text(line)

    def _draw_hud(self, cr, w, h):
        pct = min(100, int(self._progress() * 100))
        n   = len(self.mgr.collected_data)

        # Progress bar
        cr.set_source_rgba(0.25, 0.25, 0.25, 0.7)
        cr.rectangle(20, h - 12, w - 40, 5)
        cr.fill()
        cr.set_source_rgba(0.3, 0.9, 0.5, 0.9)
        cr.rectangle(20, h - 12, (w - 40) * pct / 100, 5)
        cr.fill()

        cr.select_font_face("Mono", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(14)

        if self._paused:
            # Prominent PAUSED overlay
            cr.set_source_rgba(1.0, 0.55, 0.1, 0.92)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(36)
            msg = "PAUSED — press SPACE to resume"
            e = cr.text_extents(msg)
            cr.move_to(w / 2 - e.width / 2, h / 2)
            cr.show_text(msg)
            cr.select_font_face("Mono", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(14)

        elif self._holding:
            cr.set_source_rgba(1.0, 0.85, 0.3, 0.85)
        else:
            cr.set_source_rgba(0.6, 0.6, 0.6, 0.7)

        cr.move_to(20, h - 20)
        status = "HOLD" if self._holding else "COLLECTING"
        cr.show_text(f"{status}  {pct}%  •  {n} samples  •  SPACE=pause  ESC=cancel")

    def _draw_complete(self, cr, w, h):
        cr.set_source_rgba(0.2, 0.95, 0.4, 1)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(42)
        msg = f"Done! {len(self.mgr.collected_data)} samples collected. Training..."
        e = cr.text_extents(msg)
        cr.move_to(w / 2 - e.width / 2, h / 2)
        cr.show_text(msg)

    # ── Camera ────────────────────────────────────────────────────────────────

    def _start_camera(self):
        self._cam_live = True
        threading.Thread(target=self._cam_loop, daemon=True).start()

    def _cam_loop(self):
        model_path = str(config.BASE_DIR / 'face_landmarker.task')
        opts = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path),
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        detector = vision.FaceLandmarker.create_from_options(opts)

        device = "/dev/video0"
        if config.CAMERA_FILE.exists():
            try:
                with open(config.CAMERA_FILE) as f:
                    device = json.load(f).get("device", device)
            except Exception:
                pass

        cap = open_camera(device)
        while self._cam_live:
            ret, frame = cap.read()
            if not ret:
                continue
            frame  = cv2.flip(frame, 1)
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = detector.detect(mp_img)
            if result.face_landmarks:
                vec = self.mgr.extract_normalized_vector(result.face_landmarks[0])
                if vec:
                    try:
                        self._vqueue.put_nowait(vec)
                    except queue.Full:
                        try:
                            self._vqueue.get_nowait()
                        except queue.Empty:
                            pass
                        self._vqueue.put_nowait(vec)
        release_camera(cap)
        detector.close()

    # ── Finish ────────────────────────────────────────────────────────────────

    def _finish(self):
        self._cam_live = False
        self._canvas.queue_draw()
        n = len(self.mgr.collected_data)
        print(f"Collected {n} samples. Training...")
        if self.mgr.train():
            self.mgr.save_profile()
            print("Profile saved.")
        else:
            print("Not enough valid samples.")
        GLib.timeout_add(2000, lambda: self.get_application().quit() or False)

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_space:
            if self._phase == "running":
                self._paused = not self._paused
            return True
        if keyval == Gdk.KEY_Escape:
            self._cam_live = False
            self.get_application().quit()
            return True
        return False

    def do_close_request(self):
        self._cam_live = False
        if hasattr(self, '_tick_id'):
            GLib.source_remove(self._tick_id)
        return False


def main():
    display = Gdk.Display.get_default()
    monitor = display.get_monitors().get_item(0)
    geom    = monitor.get_geometry()
    W, H    = geom.width, geom.height

    cal = CalibrationManager(W, H)
    app = Gtk.Application(application_id="com.gazeguard.continuous_cal")

    def on_activate(a):
        win = ContinuousCalibrationWindow(W, H, cal, application=a)
        win.present()

    app.connect("activate", on_activate)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
