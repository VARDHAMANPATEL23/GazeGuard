"""
Settings UI for GazeGuard.
Full GTK4 user-facing control surface with tabs for Camera, Focus, Blur, Modes, Profile, and Hotkeys.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.settings_manager import DEFAULT_SETTINGS, load_settings, save_settings
from utils.camera import get_real_cameras

CSS = b"""
window {
    background-color: #1a1b26;
    color: #c0caf5;
    font-family: system-ui, -apple-system, sans-serif;
}
notebook {
    background-color: #1a1b26;
}
notebook > header {
    background-color: #16161e;
    border-bottom: 2px solid #24283b;
    padding: 4px;
}
notebook > header > tabs > tab {
    padding: 10px 18px;
    font-weight: bold;
    font-size: 14px;
    color: #7982a9;
    border-radius: 6px 6px 0 0;
}
notebook > header > tabs > tab:checked {
    color: #7aa2f7;
    background-color: #1f2335;
    border-bottom: 2px solid #7aa2f7;
}
.tab-content {
    padding: 24px;
    background-color: #1a1b26;
}
.section-title {
    font-size: 18px;
    font-weight: bold;
    color: #7aa2f7;
    margin-bottom: 6px;
}
.section-desc {
    font-size: 13px;
    color: #a9b1d6;
    margin-bottom: 16px;
}
.card {
    background-color: #24283b;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 14px;
    border: 1px solid #2f334d;
}
.control-label {
    font-size: 14px;
    font-weight: 600;
    color: #c0caf5;
}
.hint-label {
    font-size: 12px;
    color: #565f89;
}
.btn-primary {
    background: linear-gradient(to right, #7aa2f7, #bb9af7);
    color: #1a1b26;
    font-weight: bold;
    font-size: 14px;
    border-radius: 6px;
    padding: 8px 18px;
    border: none;
}
.btn-primary:hover {
    background: linear-gradient(to right, #8ab2f7, #cbabf7);
}
.btn-secondary {
    background-color: #2f334d;
    color: #c0caf5;
    font-weight: bold;
    font-size: 14px;
    border-radius: 6px;
    padding: 8px 18px;
    border: 1px solid #414868;
}
.btn-secondary:hover {
    background-color: #414868;
}
.btn-danger {
    background-color: #f7768e;
    color: #1a1b26;
    font-weight: bold;
    font-size: 14px;
    border-radius: 6px;
    padding: 8px 18px;
    border: none;
}
.btn-danger:hover {
    background-color: #ff8b9e;
}
.badge-hotkey {
    background-color: #16161e;
    color: #7dcfff;
    border: 1px solid #3b4261;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: monospace;
    font-weight: bold;
}
.status-msg {
    color: #9ece6a;
    font-weight: bold;
    font-size: 13px;
}
"""


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("GazeGuard — Settings")
        self.set_default_size(780, 640)

        # Apply CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.settings = load_settings()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(main_box)

        # Notebook (Tabs)
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        main_box.append(self.notebook)

        # Build tabs
        self._build_camera_tab()
        self._build_focus_tab()
        self._build_blur_tab()
        self._build_modes_tab()
        self._build_profile_tab()
        self._build_hotkeys_tab()

        # Bottom action bar
        self._build_bottom_bar(main_box)

    # ── Camera Tab ────────────────────────────────────────────────────────────
    def _build_camera_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Camera & Positioning")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Configure your webcam device and position relative to your monitor."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        # Device card
        dev_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        dev_card.add_css_class("card")

        dev_lbl = Gtk.Label(label="Webcam Capture Device:")
        dev_lbl.add_css_class("control-label")
        dev_lbl.set_halign(Gtk.Align.START)
        dev_card.append(dev_lbl)

        self.cameras = get_real_cameras()
        cam_names = [c["display"] for c in self.cameras]
        self.cam_dropdown = Gtk.DropDown.new_from_strings(cam_names)

        # Select currently saved device
        current_dev = self.settings.get("camera", {}).get("device", "/dev/video0")
        for i, c in enumerate(self.cameras):
            if c["node"] == current_dev:
                self.cam_dropdown.set_selected(i)
                break
        dev_card.append(self.cam_dropdown)
        page.append(dev_card)

        # Calibration & Position Actions Card
        pos_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        pos_card.add_css_class("card")

        pos_title = Gtk.Label(label="Calibration & Physical Alignment:")
        pos_title.add_css_class("control-label")
        pos_title.set_halign(Gtk.Align.START)
        pos_card.append(pos_title)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        setup_btn = Gtk.Button(label="Open Camera Setup Screen")
        setup_btn.add_css_class("btn-secondary")
        setup_btn.connect(
            "clicked", lambda b: self._launch_script("ui/setup_screen.py")
        )
        btn_box.append(setup_btn)

        cont_cal_btn = Gtk.Button(label="Continuous Calibration (Recommended)")
        cont_cal_btn.add_css_class("btn-primary")
        cont_cal_btn.connect(
            "clicked", lambda b: self._launch_script("ui/continuous_calibration_ui.py")
        )
        btn_box.append(cont_cal_btn)

        grid_cal_btn = Gtk.Button(label="Grid Calibration")
        grid_cal_btn.add_css_class("btn-secondary")
        grid_cal_btn.connect(
            "clicked", lambda b: self._launch_script("ui/calibration_ui.py")
        )
        btn_box.append(grid_cal_btn)

        pos_card.append(btn_box)
        page.append(pos_card)

        self.notebook.append_page(page, Gtk.Label(label="Camera"))

    # ── Focus Tab ─────────────────────────────────────────────────────────────
    def _build_focus_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Foveated Focus Region")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Control the shape and radius of the unblurred clear window following your gaze."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card")

        # Focus shape
        shape_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        shape_lbl = Gtk.Label(label="Focus Shape:")
        shape_lbl.add_css_class("control-label")
        shape_box.append(shape_lbl)

        self.shape_dropdown = Gtk.DropDown.new_from_strings(["Circle", "Rectangle"])
        current_shape = self.settings.get("focus", {}).get("shape", "circle")
        self.shape_dropdown.set_selected(0 if current_shape == "circle" else 1)
        shape_box.append(self.shape_dropdown)
        card.append(shape_box)

        # Zone mode
        zone_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        zone_lbl = Gtk.Label(label="Zone Mode:")
        zone_lbl.add_css_class("control-label")
        zone_box.append(zone_lbl)

        self.zone_dropdown = Gtk.DropDown.new_from_strings(
            ["Small Sharp (Foveal 1-2° focus)", "Large Soft (Macular ~5° soft falloff)"]
        )
        current_zone = self.settings.get("focus", {}).get("zone_mode", "small_sharp")
        self.zone_dropdown.set_selected(0 if current_zone == "small_sharp" else 1)
        zone_box.append(self.zone_dropdown)
        card.append(zone_box)

        # Focus size slider
        size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        current_size = self.settings.get("focus", {}).get("size", 120)

        self.size_val_lbl = Gtk.Label(
            label=f"Focus Radius / Height: {int(current_size)} px"
        )
        self.size_val_lbl.add_css_class("control-label")
        self.size_val_lbl.set_halign(Gtk.Align.START)
        size_box.append(self.size_val_lbl)

        self.size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 60, 300, 10
        )
        self.size_scale.set_value(float(current_size))
        self.size_scale.set_hexpand(True)
        self.size_scale.connect("value-changed", self._on_size_changed)
        size_box.append(self.size_scale)
        card.append(size_box)

        page.append(card)
        self.notebook.append_page(page, Gtk.Label(label="Focus"))

    def _on_size_changed(self, scale):
        val = int(scale.get_value())
        self.size_val_lbl.set_label(f"Focus Radius / Height: {val} px")

    # ── Blur Tab ──────────────────────────────────────────────────────────────
    def _build_blur_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Blur & Motion Smoothing")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Adjust background obscurity and Kalman gaze smoothing filter presets."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card")

        # Blur intensity
        blur_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        blur_lbl = Gtk.Label(label="Blur Intensity:")
        blur_lbl.add_css_class("control-label")
        blur_box.append(blur_lbl)

        self.blur_dropdown = Gtk.DropDown.new_from_strings(
            [
                "Low (21px kernel — subtle privacy)",
                "Medium (41px kernel — recommended balance)",
                "High (71px kernel — maximum security)",
            ]
        )
        current_blur = self.settings.get("blur", {}).get("intensity", "medium")
        blur_idx = {"low": 0, "medium": 1, "high": 2}.get(current_blur, 1)
        self.blur_dropdown.set_selected(blur_idx)
        blur_box.append(self.blur_dropdown)
        card.append(blur_box)

        # Smoothing level
        smooth_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        smooth_lbl = Gtk.Label(label="Smoothing Filter:")
        smooth_lbl.add_css_class("control-label")
        smooth_box.append(smooth_lbl)

        self.smooth_dropdown = Gtk.DropDown.new_from_strings(
            [
                "Low (Fastest response, slight saccadic jitter)",
                "Medium (Balanced responsiveness and stability)",
                "High (Ultra-smooth fixation, slight tracking latency)",
            ]
        )
        current_smooth = self.settings.get("blur", {}).get("smoothing", "medium")
        smooth_idx = {"low": 0, "medium": 1, "high": 2}.get(current_smooth, 1)
        self.smooth_dropdown.set_selected(smooth_idx)
        smooth_box.append(self.smooth_dropdown)
        card.append(smooth_box)

        page.append(card)
        self.notebook.append_page(page, Gtk.Label(label="Blur & Filter"))

    # ── Security & Modes Tab ──────────────────────────────────────────────────
    def _build_modes_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Privacy Modes & Security")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Configure automated security triggers for bystanders, absence, and reading."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        # Multi-face
        mf_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        mf_card.add_css_class("card")
        mf_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        mf_lbl = Gtk.Label(label="Multi-Face Security (Shoulder-Surfing Protection)")
        mf_lbl.add_css_class("control-label")
        mf_lbl.set_halign(Gtk.Align.START)
        mf_desc = Gtk.Label(
            label="Immediately applies full screen blur when more than one face is visible."
        )
        mf_desc.add_css_class("hint-label")
        mf_desc.set_halign(Gtk.Align.START)
        mf_info.append(mf_lbl)
        mf_info.append(mf_desc)
        mf_info.set_hexpand(True)
        mf_card.append(mf_info)

        self.mf_switch = Gtk.Switch()
        self.mf_switch.set_active(
            self.settings.get("security", {}).get("multi_face", True)
        )
        self.mf_switch.set_valign(Gtk.Align.CENTER)
        mf_card.append(self.mf_switch)
        page.append(mf_card)

        # Boss Mode
        boss_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        boss_card.add_css_class("card")
        boss_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        boss_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        boss_lbl = Gtk.Label(label="Boss Mode (Absence Protection)")
        boss_lbl.add_css_class("control-label")
        boss_lbl.set_halign(Gtk.Align.START)
        boss_desc = Gtk.Label(
            label="Fully obscures display when your face leaves the camera frame."
        )
        boss_desc.add_css_class("hint-label")
        boss_desc.set_halign(Gtk.Align.START)
        boss_info.append(boss_lbl)
        boss_info.append(boss_desc)
        boss_info.set_hexpand(True)
        boss_head.append(boss_info)

        self.boss_switch = Gtk.Switch()
        self.boss_switch.set_active(
            self.settings.get("boss_mode", {}).get("enabled", True)
        )
        self.boss_switch.set_valign(Gtk.Align.CENTER)
        boss_head.append(self.boss_switch)
        boss_card.append(boss_head)

        grace_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        grace_lbl = Gtk.Label(label="Grace Period:")
        grace_lbl.add_css_class("control-label")
        grace_box.append(grace_lbl)

        self.grace_dropdown = Gtk.DropDown.new_from_strings(
            ["0 seconds (instant)", "3 seconds (default)", "5 seconds"]
        )
        grace_sec = self.settings.get("boss_mode", {}).get("grace_seconds", 3)
        grace_idx = {0: 0, 3: 1, 5: 2}.get(grace_sec, 1)
        self.grace_dropdown.set_selected(grace_idx)
        grace_box.append(self.grace_dropdown)
        boss_card.append(grace_box)
        page.append(boss_card)

        # Reading Mode
        rm_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        rm_card.add_css_class("card")
        rm_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rm_lbl = Gtk.Label(label="Reading Mode (Horizontal Sweep Auto-Detection)")
        rm_lbl.add_css_class("control-label")
        rm_lbl.set_halign(Gtk.Align.START)
        rm_desc = Gtk.Label(
            label="Transforms circular focus into a wide horizontal line reading strip."
        )
        rm_desc.add_css_class("hint-label")
        rm_desc.set_halign(Gtk.Align.START)
        rm_info.append(rm_lbl)
        rm_info.append(rm_desc)
        rm_info.set_hexpand(True)
        rm_card.append(rm_info)

        self.rm_switch = Gtk.Switch()
        self.rm_switch.set_active(
            self.settings.get("reading_mode", {}).get("enabled", False)
        )
        self.rm_switch.set_valign(Gtk.Align.CENTER)
        rm_card.append(self.rm_switch)
        page.append(rm_card)

        self.notebook.append_page(page, Gtk.Label(label="Modes & Security"))

    # ── Profile Tab ───────────────────────────────────────────────────────────
    def _build_profile_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Calibration Profile")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Information and management for your active calibration profile."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")

        self.profile_info_lbl = Gtk.Label()
        self.profile_info_lbl.set_halign(Gtk.Align.START)
        self._refresh_profile_info()
        card.append(self.profile_info_lbl)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        del_btn = Gtk.Button(label="Delete Profile")
        del_btn.add_css_class("btn-danger")
        del_btn.connect("clicked", self._on_delete_profile)
        btn_row.append(del_btn)

        recal_btn = Gtk.Button(label="Recalibrate (Continuous)")
        recal_btn.add_css_class("btn-primary")
        recal_btn.connect(
            "clicked", lambda b: self._launch_script("ui/continuous_calibration_ui.py")
        )
        btn_row.append(recal_btn)

        card.append(btn_row)
        page.append(card)

        self.notebook.append_page(page, Gtk.Label(label="Profile"))

    def _refresh_profile_info(self):
        prof_path = config.DEFAULT_PROFILE_FILE
        if prof_path.exists():
            try:
                with open(prof_path, "r") as f:
                    p = json.load(f)
                res = p.get("screen_resolution", [1920, 1080])
                created = p.get("created", "Unknown")[:19].replace("T", " ")
                cam = p.get("camera_position", {})
                cx, cy = cam.get("x", 0.5), cam.get("y", 0.0)
                text = (
                    f"Status: Active Profile Loaded\n"
                    f"Path: {prof_path}\n"
                    f"Resolution: {res[0]}x{res[1]}\n"
                    f"Camera Alignment: X={cx:.2f}, Y={cy:.2f}\n"
                    f"Created: {created}\n"
                    f"Version: {p.get('version', 3)}"
                )
            except Exception as e:
                text = f"Error reading profile: {e}"
        else:
            text = "Status: No profile found. Run calibration to generate one."
        self.profile_info_lbl.set_label(text)

    def _on_delete_profile(self, btn):
        prof_path = config.DEFAULT_PROFILE_FILE
        if prof_path.exists():
            try:
                prof_path.unlink()
                self._refresh_profile_info()
                self.status_lbl.set_label("Profile deleted. Calibration required.")
            except Exception as e:
                self.status_lbl.set_label(f"Error deleting profile: {e}")

    # ── Hotkeys Tab ───────────────────────────────────────────────────────────
    def _build_hotkeys_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("tab-content")

        title = Gtk.Label(label="Global Keyboard Shortcuts")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        page.append(title)

        desc = Gtk.Label(
            label="Control GazeGuard from anywhere on your desktop via global hotkeys."
        )
        desc.add_css_class("section-desc")
        desc.set_halign(Gtk.Align.START)
        page.append(desc)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")

        hotkeys = self.settings.get("hotkeys", config.DEFAULT_HOTKEYS)
        labels = [
            (
                "Toggle GazeGuard Overlay",
                hotkeys.get("toggle_gazeguard", "ctrl+shift+g"),
            ),
            (
                "Emergency Immediate Unblur",
                hotkeys.get("emergency_unblur", "ctrl+shift+space"),
            ),
            ("Pause Gaze Tracking (10 min)", hotkeys.get("pause_10m", "ctrl+shift+p")),
            (
                "Toggle Reading Strip Mode",
                hotkeys.get("toggle_reading_mode", "ctrl+shift+r"),
            ),
            (
                "Toggle Boss Mode Absence Guard",
                hotkeys.get("toggle_boss_mode", "ctrl+shift+b"),
            ),
        ]

        for name, key in labels:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            lbl = Gtk.Label(label=name)
            lbl.add_css_class("control-label")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)
            row.append(lbl)

            badge = Gtk.Label(label=key.upper())
            badge.add_css_class("badge-hotkey")
            row.append(badge)

            card.append(row)

        page.append(card)
        self.notebook.append_page(page, Gtk.Label(label="Hotkeys"))

    # ── Bottom Action Bar ─────────────────────────────────────────────────────
    def _build_bottom_bar(self, main_box):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.set_margin_start(24)
        bar.set_margin_end(24)
        bar.set_margin_top(12)
        bar.set_margin_bottom(16)

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.add_css_class("status-msg")
        self.status_lbl.set_hexpand(True)
        self.status_lbl.set_halign(Gtk.Align.START)
        bar.append(self.status_lbl)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.add_css_class("btn-secondary")
        reset_btn.connect("clicked", self._on_reset_defaults)
        bar.append(reset_btn)

        save_btn = Gtk.Button(label="Save Changes")
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._on_save_clicked)
        bar.append(save_btn)

        main_box.append(bar)

    def _on_save_clicked(self, btn):
        # Camera
        cam_idx = self.cam_dropdown.get_selected()
        if 0 <= cam_idx < len(self.cameras):
            self.settings["camera"]["device"] = self.cameras[cam_idx]["node"]

        # Focus
        self.settings["focus"]["shape"] = (
            "circle" if self.shape_dropdown.get_selected() == 0 else "rectangle"
        )
        self.settings["focus"]["zone_mode"] = (
            "small_sharp" if self.zone_dropdown.get_selected() == 0 else "large_soft"
        )
        self.settings["focus"]["size"] = int(self.size_scale.get_value())

        # Blur
        b_idx = self.blur_dropdown.get_selected()
        self.settings["blur"]["intensity"] = ["low", "medium", "high"][b_idx]
        s_idx = self.smooth_dropdown.get_selected()
        self.settings["blur"]["smoothing"] = ["low", "medium", "high"][s_idx]

        # Security & Modes
        self.settings["security"]["multi_face"] = self.mf_switch.get_active()
        self.settings["boss_mode"]["enabled"] = self.boss_switch.get_active()
        g_idx = self.grace_dropdown.get_selected()
        self.settings["boss_mode"]["grace_seconds"] = [0, 3, 5][g_idx]
        self.settings["reading_mode"]["enabled"] = self.rm_switch.get_active()

        # Save & Notify
        if save_settings(self.settings, notify_overlay=True):
            self.status_lbl.set_label("Settings saved & live overlay updated!")
            self._refresh_profile_info()
            GLib.timeout_add_seconds(3, lambda: self.status_lbl.set_label("") or False)
        else:
            self.status_lbl.set_label("Failed to save settings.")

    def _on_reset_defaults(self, btn):
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        save_settings(self.settings, notify_overlay=True)
        self.status_lbl.set_label("Reset to default settings.")
        # Reload values into controls
        self.cam_dropdown.set_selected(0)
        self.shape_dropdown.set_selected(0)
        self.zone_dropdown.set_selected(0)
        self.size_scale.set_value(120)
        self.blur_dropdown.set_selected(1)
        self.smooth_dropdown.set_selected(1)
        self.mf_switch.set_active(True)
        self.boss_switch.set_active(True)
        self.grace_dropdown.set_selected(1)
        self.rm_switch.set_active(False)

    def _launch_script(self, rel_path):
        script_path = str(config.BASE_DIR / rel_path)
        python_bin = sys.executable
        subprocess.Popen([python_bin, script_path])


def main():
    app = Gtk.Application(application_id="com.gazeguard.settings")
    app.connect("activate", lambda a: SettingsWindow(application=a).present())
    app.run(sys.argv)


if __name__ == "__main__":
    main()
