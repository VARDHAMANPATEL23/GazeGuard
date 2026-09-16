"""
Lightweight IPC module for GazeGuard.
Enables communication between the main overlay engine, the system tray,
and the settings window via a Unix Domain Socket.
"""

import os
import socket
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import config

SOCKET_PATH = str(config.CONFIG_DIR / "gazeguard.sock")


class IPCServer:
    def __init__(self, command_handler, socket_path=SOCKET_PATH):
        self.handler = command_handler
        self.socket_path = socket_path
        self._server_sock = None
        self._thread = None
        self._running = False

    def start(self):
        if os.path.exists(self.socket_path):
            try:
                # Check if stale socket
                test_s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_s.settimeout(0.5)
                test_s.connect(self.socket_path)
                test_s.close()
                # Server is actually already running
                return False
            except (ConnectionRefusedError, socket.timeout, OSError):
                # Stale socket from previous crash, remove it
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.socket_path)
        self._server_sock.listen(5)
        self._running = True

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return True

    def _listen_loop(self):
        while self._running:
            try:
                conn, _ = self._server_sock.accept()
            except OSError:
                break

            threading.Thread(
                target=self._handle_client, args=(conn,), daemon=True
            ).start()

    def _handle_client(self, conn):
        try:
            conn.settimeout(2.0)
            data = conn.recv(1024).decode("utf-8").strip()
            if data:
                resp = self.handler(data)
                if resp is None:
                    resp = "OK"
                conn.sendall(f"{resp}\n".encode("utf-8"))
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass


def send_ipc_command(command, socket_path=SOCKET_PATH, timeout=1.0):
    """
    Send a command string to the running GazeGuard overlay instance.
    Returns response string or None if overlay is not running.
    """
    if not os.path.exists(socket_path):
        return None

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        s.sendall(f"{command.strip()}\n".encode("utf-8"))
        resp = s.recv(1024).decode("utf-8").strip()
        s.close()
        return resp
    except Exception:
        return None


def is_service_running(socket_path=SOCKET_PATH):
    """Returns True if the GazeGuard overlay daemon is running."""
    resp = send_ipc_command("PING", socket_path=socket_path, timeout=0.5)
    return resp == "PONG"
