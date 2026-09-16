"""Unit tests for Settings Manager and IPC."""

import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.ipc import IPCServer, is_service_running, send_ipc_command
from core.settings_manager import (
    DEFAULT_SETTINGS,
    get_setting,
    load_settings,
    save_settings,
    update_setting,
)


def test_settings_load_defaults(tmp_path):
    test_file = tmp_path / "settings.json"
    settings = load_settings(filepath=test_file)
    assert settings["focus"]["size"] == 120
    assert settings["blur"]["intensity"] == "medium"
    assert test_file.exists()


def test_settings_update_and_get(tmp_path):
    test_file = tmp_path / "settings.json"
    load_settings(filepath=test_file)

    update_setting("focus.size", 180, filepath=test_file, notify_overlay=False)
    assert get_setting("focus.size", filepath=test_file) == 180

    update_setting("blur.intensity", "high", filepath=test_file, notify_overlay=False)
    assert get_setting("blur.intensity", filepath=test_file) == "high"


def test_ipc_communication(tmp_path):
    test_sock = str(tmp_path / "test.sock")

    def handler(cmd):
        if cmd == "PING":
            return "PONG"
        elif cmd == "STATUS":
            return "ACTIVE"
        return "UNKNOWN"

    server = IPCServer(command_handler=handler, socket_path=test_sock)
    assert server.start() is True

    try:
        assert is_service_running(socket_path=test_sock) is True
        resp = send_ipc_command("STATUS", socket_path=test_sock)
        assert resp == "ACTIVE"
    finally:
        server.stop()

    assert not os.path.exists(test_sock)
    assert is_service_running(socket_path=test_sock) is False
