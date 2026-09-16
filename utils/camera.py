"""Shared camera utilities for GazeGuard."""
import os
import cv2


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
    saved   = os.dup(2)
    os.dup2(devnull, 2)
    try:
        cap.release()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)
