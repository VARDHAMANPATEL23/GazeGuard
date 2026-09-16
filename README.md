# GazeGuard 👁️🛡️

> **Foveated Eye-Tracking Screen Privacy Shield for Linux**  
> _See only what matters. Everything else stays private._

---

## Overview

**GazeGuard** is an open-source, privacy-preserving desktop application for Linux that defends against shoulder surfing and visual eavesdropping. Using standard webcams and lightweight computer vision, GazeGuard tracks where you are looking in real time and applies **foveated rendering**:

- **Foveal Zone (1–2°)**: Crystal-clear, unblurred view centered precisely at your gaze fixation point.
- **Parafoveal Zone (~5°)**: Gentle, smooth gradient falloff matching human peripheral acuity.
- **Peripheral Zone (60–180°)**: Obscured by privacy blur, preventing onlookers from reading your screen.

---

## Core Features

- 🎯 **Continuous Sweep Calibration**: Collects >1,000 gaze samples along natural eye movement paths with quadratic Ridge polynomial regression.
- 📐 **Independent Vertical Axis Scaling**: Normalizes iris motion within eye bounding boxes with vertical amplification (`IRIS_Y_SCALE_FACTOR = 1.4`) to ensure full top-to-bottom screen coverage.
- 👥 **Multi-Face Defense**: Automatically triggers full-screen blur when a secondary face enters the webcam frame.
- ⚡ **Kalman Motion Filtering**: Adaptive smoothing balances low-latency saccades with rock-solid fixation stability.
- 🎛️ **Full GTK4 Control Surface**: 6-tab Settings window for camera selection, foveated focus shape/size, blur intensity, modes, profile management, and global hotkeys.
- 🛡️ **System Tray Integration**: GNOME top bar indicator (`AyatanaAppIndicator3`) with live status, tracking pause/resume, quick recalibration, and instant toggle.
- 🔄 **Fault-Tolerant Camera Pipeline**: Detects camera disconnects, enters immediate security safe mode, and retries reconnection automatically every 5 seconds.
- 🚀 **Graceful Startup**: Automatically prompts and guides new users through calibration on first launch.

---

## System Requirements

- **OS**: Linux (Ubuntu 22.04 / 24.04 / 26.04 recommended, GNOME desktop)
- **CPU**: Intel Core i5 6th Gen or equivalent AMD (optimized to < 20% sustained CPU at 30fps)
- **Webcam**: Standard USB or integrated 720p/1080p webcam (V4L2)
- **Libraries**: GTK 4.0, Cairo, Python 3.10+

---

## Quick Installation

Run the automated installer:

```bash
git clone https://github.com/VARDHAMANPATEL23/GazeGuard.git
cd GazeGuard
chmod +x install.sh
./install.sh
```

The installer verifies system packages (`gir1.2-gtk-4.0`, `gir1.2-ayatanaappindicator3-0.1`), sets up the Python virtual environment with system bindings, checks the bundled MediaPipe Face Landmarker model, and installs the `gazeguard.desktop` application shortcut.

---

## Getting Started

### 1. Camera Physical Alignment (First Run)

Align the software with your webcam's physical position:

```bash
venv/bin/python ui/setup_screen.py
```

### 2. Gaze Calibration

Follow the animated guide box along perimeter and diagonal sweeps:

```bash
venv/bin/python ui/continuous_calibration_ui.py
```

### 3. Launch GazeGuard

Launch the complete privacy overlay and system tray:

```bash
venv/bin/python main.py
```

### 4. Settings & Customization

Configure focus shape, size, blur intensity, and security triggers:

```bash
venv/bin/python ui/settings_window.py
```

---

## Global Hotkeys

| Hotkey                 | Action                            |
| ---------------------- | --------------------------------- |
| `Ctrl + Shift + G`     | Toggle GazeGuard overlay on / off |
| `Ctrl + Shift + Space` | Emergency immediate unblur        |
| `Ctrl + Shift + P`     | Pause tracking for 10 minutes     |
| `Ctrl + Shift + R`     | Toggle Reading Strip Mode         |
| `Ctrl + Shift + B`     | Toggle Boss Mode absence guard    |

---

## Project Architecture

```
gazeguard/
├── main.py                     # Entry point — starts IPC daemon, overlay, and tray
├── config.py                   # Centralized configuration and constants
├── core/
│   ├── gaze_engine.py          # Consumer orchestrator & Kalman smoother
│   ├── gaze_pipeline.py        # 30fps camera thread with MediaPipe & auto-reconnect
│   ├── calibration.py          # Ridge polynomial gaze mapping & normalizer
│   ├── smoother.py             # Kalman filter motion smoothing
│   ├── settings_manager.py     # Persistent settings in ~/.config/gazeguard/
│   └── ipc.py                  # Unix domain socket IPC daemon
├── overlay/
│   ├── overlay_window.py       # Fullscreen GTK4 privacy overlay & focus cutout
│   └── blur_renderer.py        # Cairo/OpenCV Gaussian blur pipeline
├── ui/
│   ├── continuous_calibration_ui.py  # Primary continuous sweep calibration
│   ├── calibration_ui.py             # Discrete 25-point grid calibration
│   ├── setup_screen.py               # Physical camera placement wizard
│   ├── settings_window.py            # GTK4 6-tab settings control panel
│   └── tray.py                       # GNOME top bar indicator
└── tests/                      # Automated unit test suite
```

---

## Running Unit Tests

To run the complete automated test suite:

```bash
venv/bin/python -m pytest tests/ -v
```

All 23 tests cover calibration geometry, vertical tracking bounds, motion smoothing presets, settings persistence, IPC messaging, profile loading performance, and camera disconnect resilience.

---

## License

MIT License. See `LICENSE` for details.
