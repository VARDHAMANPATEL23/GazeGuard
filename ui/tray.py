#!/usr/bin/env python3
"""
GazeGuard — System Tray Application.
Uses AyatanaAppIndicator3 and GTK 3 to integrate into the GNOME top bar.
Communicates with the GazeGuard overlay daemon via IPC.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3

sys.path.append(str(Path(__file__).parent.parent))
import config
from core.ipc import is_service_running, send_ipc_command

APPINDICATOR_ID = "gazeguard-tray"


class GazeGuardTray:
    def __init__(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APPINDICATOR_ID,
            "security-high",
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()
        self._build_menu()
        self.indicator.set_menu(self.menu)

        # Check status every 2 seconds
        GLib.timeout_add_seconds(2, self._periodic_check)

    def _build_menu(self):
        # 1. Status header (disabled/insensitive)
        self.status_item = Gtk.MenuItem(label="GazeGuard: Checking...")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # 2. Toggle Tracking (Enable/Disable)
        self.toggle_item = Gtk.MenuItem(label="Disable Tracking")
        self.toggle_item.connect("activate", self._on_toggle_tracking)
        self.menu.append(self.toggle_item)

        # 3. Pause Submenu
        pause_menu_item = Gtk.MenuItem(label="Pause")
        pause_submenu = Gtk.Menu()

        item_p10 = Gtk.MenuItem(label="Pause for 10 minutes")
        item_p10.connect("activate", lambda w: self._on_pause(600))
        pause_submenu.append(item_p10)

        item_p30 = Gtk.MenuItem(label="Pause for 30 minutes")
        item_p30.connect("activate", lambda w: self._on_pause(1800))
        pause_submenu.append(item_p30)

        item_p_indef = Gtk.MenuItem(label="Pause until resumed")
        item_p_indef.connect("activate", lambda w: self._on_pause(0))
        pause_submenu.append(item_p_indef)

        pause_submenu.append(Gtk.SeparatorMenuItem())

        self.resume_item = Gtk.MenuItem(label="Resume Tracking")
        self.resume_item.connect("activate", self._on_resume)
        pause_submenu.append(self.resume_item)

        pause_menu_item.set_submenu(pause_submenu)
        self.menu.append(pause_menu_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # 4. Calibration & Setup Submenu
        cal_item = Gtk.MenuItem(label="Calibration")
        cal_submenu = Gtk.Menu()

        item_cont = Gtk.MenuItem(label="Continuous Calibration (Recommended)")
        item_cont.connect(
            "activate", lambda w: self._launch_script("ui/continuous_calibration_ui.py")
        )
        cal_submenu.append(item_cont)

        item_grid = Gtk.MenuItem(label="Grid Calibration")
        item_grid.connect(
            "activate", lambda w: self._launch_script("ui/calibration_ui.py")
        )
        cal_submenu.append(item_grid)

        cal_submenu.append(Gtk.SeparatorMenuItem())

        item_cam = Gtk.MenuItem(label="Camera Physical Setup...")
        item_cam.connect(
            "activate", lambda w: self._launch_script("ui/setup_screen.py")
        )
        cal_submenu.append(item_cam)

        cal_item.set_submenu(cal_submenu)
        self.menu.append(cal_item)

        # 5. Settings
        settings_item = Gtk.MenuItem(label="Settings...")
        settings_item.connect(
            "activate", lambda w: self._launch_script("ui/settings_window.py")
        )
        self.menu.append(settings_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # 6. Quit
        quit_item = Gtk.MenuItem(label="Quit GazeGuard")
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self._update_status()

    def _periodic_check(self):
        self._update_status()
        return True

    def _set_icon_name(self, name):
        try:
            self.indicator.set_icon_full(name, name)
        except Exception:
            try:
                self.indicator.set_icon(name)
            except Exception:
                pass

    def _update_status(self):
        resp = send_ipc_command("STATUS")
        if resp is None:
            self.status_item.set_label("GazeGuard: Inactive")
            self.toggle_item.set_label("Start GazeGuard")
            self._set_icon_name("security-low")
        else:
            parts = resp.split(":")
            state = parts[0]
            if state == "PAUSED":
                self.status_item.set_label("GazeGuard: Paused")
                self.toggle_item.set_label("Resume Tracking")
                self._set_icon_name("security-medium")
            elif state == "DISABLED":
                self.status_item.set_label("GazeGuard: Disabled")
                self.toggle_item.set_label("Enable Tracking")
                self._set_icon_name("security-low")
            else:
                self.status_item.set_label("GazeGuard: Active (Guarding)")
                self.toggle_item.set_label("Disable Tracking")
                self._set_icon_name("security-high")

    def _on_toggle_tracking(self, widget):
        if not is_service_running():
            self._launch_script("main.py")
        else:
            send_ipc_command("TOGGLE")
        self._update_status()

    def _on_pause(self, seconds):
        if is_service_running():
            send_ipc_command(f"PAUSE:{seconds}")
        self._update_status()

    def _on_resume(self, widget):
        if is_service_running():
            send_ipc_command("RESUME")
        self._update_status()

    def _launch_script(self, rel_path):
        script_path = str(config.BASE_DIR / rel_path)
        python_bin = sys.executable
        subprocess.Popen([python_bin, script_path])

    def _on_quit(self, widget):
        if is_service_running():
            send_ipc_command("QUIT")
        Gtk.main_quit()


def main():
    tray = GazeGuardTray()
    Gtk.main()


if __name__ == "__main__":
    main()
