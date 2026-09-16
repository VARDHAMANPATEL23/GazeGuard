"""Shared camera utilities for GazeGuard."""

import glob
import os

import cv2


def get_real_cameras():
    """Enumerate physical V4L2 video capture devices using sysfs."""
    cameras = []
    seen_names = set()
    for path in sorted(glob.glob("/sys/class/video4linux/video*")):
        dev_node = "/dev/" + os.path.basename(path)
        try:
            with open(os.path.join(path, "name"), "r") as f:
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
        cameras.append(
            {"node": "/dev/video0", "display": "Default Camera (/dev/video0)"}
        )
    return cameras


def open_camera(device="/dev/video0"):
    """Open a V4L2 camera and minimize queued buffers to reduce driver noise."""
    cap = cv2.VideoCapture(device)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def release_camera(cap):
    """
    Release the camera while suppressing the V4L2 ioctl(VIDIOC_QBUF) warning.
    That warning is a kernel driver artefact and carries no actionable info.
    """
    if cap is None:
        return
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(devnull, 2)
    try:
        cap.release()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)
