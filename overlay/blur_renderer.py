import numpy as np
import cv2
from pathlib import Path
import subprocess
import os

# Blur kernel sizes for each intensity level
BLUR_KERNELS = {
    "low":    21,
    "medium": 41,
    "high":   71,
}

def capture_screenshot(output_path="/tmp/gz_overlay_bg.png"):
    """
    Capture screen using GNOME Shell's built-in D-Bus screenshot API.
    This is exactly what the Print Screen key calls internally.
    """
    try:
        subprocess.run([
            "gdbus", "call",
            "--session",
            "--dest", "org.gnome.Shell.Screenshot",
            "--object-path", "/org/gnome/Shell/Screenshot",
            "--method", "org.gnome.Shell.Screenshot.Screenshot",
            "true",    # include cursor
            "true",    # flash
            output_path
        ], check=True, timeout=4, capture_output=True)

        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        print(f"Screenshot failed: {e}")

    return None

def blur_image(image_path, intensity="medium"):
    """Load an image and return a Gaussian-blurred numpy array (RGB)."""
    img = cv2.imread(image_path)
    if img is None:
        return None

    k = BLUR_KERNELS.get(intensity, BLUR_KERNELS["medium"])
    blurred = cv2.GaussianBlur(img, (k, k), 0)
    return cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB)

def numpy_to_cairo_surface(rgb_array):
    """Convert an RGB numpy array to raw BGRA bytes for a Cairo ImageSurface."""
    import cairo
    h, w = rgb_array.shape[:2]
    bgra = np.zeros((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = rgb_array[:, :, 2]  # B
    bgra[:, :, 1] = rgb_array[:, :, 1]  # G
    bgra[:, :, 2] = rgb_array[:, :, 0]  # R
    bgra[:, :, 3] = 255                  # A

    surface = cairo.ImageSurface.create_for_data(
        bgra, cairo.FORMAT_ARGB32, w, h
    )
    return surface
