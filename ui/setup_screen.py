import os
import sys
import json
import glob
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import cairo

# Ensure we can import config
sys.path.append(str(Path(__file__).parent.parent))
import config

CSS = b"""
window {
    background-color: #1a1b26;
    color: #c0caf5;
}
.header {
    font-size: 26px;
    font-weight: 900;
    color: #7aa2f7;
    text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}
.subheader {
    font-size: 14px;
    color: #9ece6a;
}
.confirm-btn {
    background: linear-gradient(to right, #7aa2f7, #bb9af7);
    color: #1a1b26;
    font-weight: 900;
    font-size: 16px;
    border-radius: 8px;
    padding: 10px 24px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.5);
    border: none;
}
.confirm-btn:hover {
    background: linear-gradient(to right, #8ab2f7, #cbabf7);
}
.reset-btn {
    background: #24283b;
    color: #c0caf5;
    font-weight: 900;
    font-size: 16px;
    border-radius: 8px;
    padding: 10px 24px;
    border: 2px solid #7aa2f7;
}
.reset-btn:hover {
    background: #2f334d;
}
.camera-widget {
    background: linear-gradient(135deg, #f7768e, #ff9e64);
    color: #1a1b26;
    font-weight: bold;
    border-radius: 6px;
    border: 2px solid #ffffff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.6);
}
"""

class SetupScreen(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("GazeGuard - Camera Setup")
        self.set_default_size(900, 700)
        
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        self.screen_w, self.screen_h = 1920, 1080
        if monitors.get_n_items() > 0:
            monitor = monitors.get_item(0)
            geom = monitor.get_geometry()
            self.screen_w = geom.width
            self.screen_h = geom.height
            
        self.aspect_ratio = self.screen_w / self.screen_h
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_start(40)
        vbox.set_margin_end(40)
        vbox.set_margin_top(30)
        vbox.set_margin_bottom(30)
        self.set_child(vbox)
        
        header = Gtk.Label(label="Camera Setup")
        header.add_css_class("header")
        subheader = Gtk.Label(label=f"Drag the camera widget to match its physical location on your monitor ({self.screen_w}x{self.screen_h}).")
        subheader.add_css_class("subheader")
        vbox.append(header)
        vbox.append(subheader)
        
        cam_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cam_box.set_halign(Gtk.Align.CENTER)
        cam_label = Gtk.Label(label="Select Camera Device:")
        
        self.devices = self.get_real_cameras()
        display_names = [d['display'] for d in self.devices]
        
        self.cam_dropdown = Gtk.DropDown.new_from_strings(display_names)
        
        cam_box.append(cam_label)
        cam_box.append(self.cam_dropdown)
        vbox.append(cam_box)
        
        frame = Gtk.Frame()
        frame.set_vexpand(True)
        frame.set_hexpand(True)
        frame.remove_css_class("frame")
        vbox.append(frame)
        
        self.overlay = Gtk.Overlay()
        frame.set_child(self.overlay)
        
        self.screen_rect = Gtk.DrawingArea()
        self.screen_rect.set_draw_func(self.on_draw_screen)
        self.overlay.set_child(self.screen_rect)
        
        self.cam_widget = Gtk.Button(label="Webcam")
        self.cam_widget.add_css_class("camera-widget")
        self.cam_widget.set_size_request(120, 40)
        self.cam_widget.set_halign(Gtk.Align.START)
        self.cam_widget.set_valign(Gtk.Align.START)
        
        self.cam_x = 350.0
        self.cam_y = 10.0
        self.cam_widget.set_margin_start(int(self.cam_x))
        self.cam_widget.set_margin_top(int(self.cam_y))
        self.overlay.add_overlay(self.cam_widget)
        
        self.drag = Gtk.GestureDrag.new()
        self.drag.connect("drag-begin", self.on_drag_begin)
        self.drag.connect("drag-update", self.on_drag_update)
        self.cam_widget.add_controller(self.drag)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        btn_box.set_halign(Gtk.Align.CENTER)
        
        self.reset_btn = Gtk.Button(label="Auto-Center (Laptop Default)")
        self.reset_btn.add_css_class("reset-btn")
        self.reset_btn.set_size_request(240, 45)
        self.reset_btn.connect("clicked", self.on_reset)
        btn_box.append(self.reset_btn)
        
        self.confirm_btn = Gtk.Button(label="Confirm & Save")
        self.confirm_btn.add_css_class("confirm-btn")
        self.confirm_btn.set_size_request(200, 45)
        self.confirm_btn.connect("clicked", self.on_confirm)
        btn_box.append(self.confirm_btn)
        
        vbox.append(btn_box)

    def get_real_cameras(self):
        cameras = []
        seen_names = set()
        for path in sorted(glob.glob('/sys/class/video4linux/video*')):
            dev_node = "/dev/" + os.path.basename(path)
            try:
                with open(os.path.join(path, 'name'), 'r') as f:
                    name = f.read().strip()
                if "Metadata" in name or "Processing" in name:
                    continue
                if name not in seen_names:
                    seen_names.add(name)
                    cameras.append({"node": dev_node, "display": f"{name} ({dev_node})"})
            except Exception:
                if "/dev/video" not in seen_names:
                    cameras.append({"node": dev_node, "display": dev_node})
                    seen_names.add("/dev/video")
        if not cameras:
            cameras.append({"node": "/dev/video0", "display": "No cameras found (Default: /dev/video0)"})
        return cameras

    def on_draw_screen(self, area, cr, width, height):
        padding = 40
        available_w = width - (padding * 2)
        available_h = height - (padding * 2)
        
        if available_w / available_h > self.aspect_ratio:
            draw_h = available_h
            draw_w = draw_h * self.aspect_ratio
        else:
            draw_w = available_w
            draw_h = draw_w / self.aspect_ratio
            
        start_x = (width - draw_w) / 2
        start_y = (height - draw_h) / 2
        
        cr.set_source_rgba(0, 0, 0, 0.4)
        cr.rectangle(start_x + 5, start_y + 10, draw_w, draw_h)
        cr.fill()
        
        cr.set_source_rgb(0.08, 0.08, 0.1)
        cr.set_line_width(12)
        cr.rectangle(start_x, start_y, draw_w, draw_h)
        cr.stroke_preserve()
        
        pattern = cairo.LinearGradient(start_x, start_y, start_x + draw_w, start_y + draw_h)
        pattern.add_color_stop_rgb(0.0, 0.16, 0.16, 0.24)
        pattern.add_color_stop_rgb(1.0, 0.05, 0.05, 0.1)
        cr.set_source(pattern)
        cr.fill()
        
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.rectangle(start_x, start_y, draw_w, 20)
        cr.fill()
        
        win_w, win_h = draw_w * 0.5, draw_h * 0.6
        win_x, win_y = start_x + (draw_w - win_w)/2, start_y + (draw_h - win_h)/2
        
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.rectangle(win_x + 4, win_y + 4, win_w, win_h)
        cr.fill()
        cr.set_source_rgb(0.12, 0.12, 0.15)
        cr.rectangle(win_x, win_y, win_w, win_h)
        cr.fill()
        cr.set_source_rgb(0.2, 0.2, 0.25)
        cr.rectangle(win_x, win_y, win_w, 24)
        cr.fill()
        
        cr.set_source_rgb(0.4, 0.5, 0.8)
        cr.rectangle(win_x + 15, win_y + 40, win_w * 0.6, 6)
        cr.fill()
        cr.set_source_rgb(0.3, 0.7, 0.4)
        cr.rectangle(win_x + 15, win_y + 55, win_w * 0.4, 6)
        cr.fill()
        cr.set_source_rgb(0.8, 0.4, 0.4)
        cr.rectangle(win_x + 15, win_y + 70, win_w * 0.7, 6)
        cr.fill()
            
        cr.set_source_rgb(0.15, 0.15, 0.18)
        stand_w = draw_w * 0.15
        cr.rectangle(width/2 - (stand_w/2), start_y + draw_h + 6, stand_w, padding - 6)
        cr.fill()
        cr.rectangle(width/2 - (stand_w), start_y + draw_h + padding - 6, stand_w * 2, 6)
        cr.fill()
        
        self.canvas_x = start_x
        self.canvas_y = start_y
        self.canvas_w = draw_w
        self.canvas_h = draw_h

    def on_reset(self, btn):
        if hasattr(self, 'canvas_w') and self.canvas_w > 0:
            target_x = self.canvas_x + (self.canvas_w / 2) - (self.cam_widget.get_width() / 2)
            target_y = self.canvas_y - (self.cam_widget.get_height() / 2)
            
            max_x = self.overlay.get_width() - self.cam_widget.get_width()
            max_y = self.overlay.get_height() - self.cam_widget.get_height()
            
            self.cam_x = max(0, min(target_x, max_x if max_x > 0 else 900))
            self.cam_y = max(0, min(target_y, max_y if max_y > 0 else 700))
            
            self.cam_widget.set_margin_start(int(self.cam_x))
            self.cam_widget.set_margin_top(int(self.cam_y))

    def on_drag_begin(self, gesture, start_x, start_y):
        self.start_cam_x = self.cam_x
        self.start_cam_y = self.cam_y

    def on_drag_update(self, gesture, offset_x, offset_y):
        self.cam_x = self.start_cam_x + offset_x
        self.cam_y = self.start_cam_y + offset_y
        
        max_x = self.overlay.get_width() - self.cam_widget.get_width()
        max_y = self.overlay.get_height() - self.cam_widget.get_height()
        
        self.cam_x = max(0, min(self.cam_x, max_x if max_x > 0 else 900))
        self.cam_y = max(0, min(self.cam_y, max_y if max_y > 0 else 700))
        
        self.cam_widget.set_margin_start(int(self.cam_x))
        self.cam_widget.set_margin_top(int(self.cam_y))

    def on_confirm(self, btn):
        center_x = self.cam_x + (self.cam_widget.get_width() / 2)
        center_y = self.cam_y + (self.cam_widget.get_height() / 2)
        
        if hasattr(self, 'canvas_w') and self.canvas_w > 0:
            norm_x = (center_x - self.canvas_x) / self.canvas_w
            norm_y = (center_y - self.canvas_y) / self.canvas_h
        else:
            norm_x, norm_y = 0.5, 0.0
            
        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))
        
        selected_idx = self.cam_dropdown.get_selected()
        if selected_idx != Gtk.INVALID_LIST_POSITION and selected_idx < len(self.devices):
            cam_device = self.devices[selected_idx]['node']
        else:
            cam_device = "/dev/video0"
        
        data = {
            "device": cam_device,
            "position": {"x": norm_x, "y": norm_y},
            "resolution": {"w": self.screen_w, "h": self.screen_h}
        }
        
        config.CAMERA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.CAMERA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
            
        print(f"Saved camera config: {data}")
        self.close()

def main():
    app = Gtk.Application(application_id='com.gazeguard.setup')
    def on_activate(app):
        win = SetupScreen(application=app)
        win.present()
    app.connect('activate', on_activate)
    app.run(sys.argv)

if __name__ == '__main__':
    main()
