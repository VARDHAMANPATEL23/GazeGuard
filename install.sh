#!/usr/bin/env bash
# GazeGuard Installation Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "      GazeGuard — Linux Installer         "
echo "=========================================="

# 1. Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install python3 first."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Detected Python: $PY_VER"

# 2. Check System Packages
echo "Checking system package prerequisites..."
PACKAGES_TO_CHECK=(
    "python3-gi"
    "gir1.2-gtk-4.0"
    "gir1.2-gtk-3.0"
    "gir1.2-ayatanaappindicator3-0.1"
    "libgirepository1.0-dev"
)

MISSING_PKGS=()
for pkg in "${PACKAGES_TO_CHECK[@]}"; do
    if ! dpkg -s "$pkg" &> /dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "Notice: Missing system packages: ${MISSING_PKGS[*]}"
    echo "Attempting to install system dependencies via apt (may prompt for sudo)..."
    sudo apt update && sudo apt install -y "${MISSING_PKGS[@]}"
fi

# 3. Create or update virtual environment with system site packages (for PyGObject)
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment with system site packages..."
    python3 -m venv --system-site-packages venv
else
    echo "Virtual environment already exists."
fi

# 4. Install Python dependencies
echo "Installing/Updating Python dependencies..."
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# 5. Verify MediaPipe Face Landmarker model asset
MODEL_FILE="$SCRIPT_DIR/face_landmarker.task"
if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading MediaPipe Face Landmarker model asset..."
    curl -Lo "$MODEL_FILE" "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
fi
echo "Face Landmarker model verified."

# 6. Install desktop launcher
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
DESKTOP_FILE="$DESKTOP_DIR/gazeguard.desktop"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=GazeGuard
GenericName=Privacy Screen Overlay
Comment=Foveated eye-tracking screen shield for shoulder-surfing defense
Exec=/bin/bash -c "cd '$SCRIPT_DIR' && venv/bin/python main.py"
Icon=security-high
Terminal=false
Categories=Utility;Security;Accessibility;
Keywords=privacy;gaze;eye-tracking;security;foveated;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
echo "Desktop shortcut installed to: $DESKTOP_FILE"

echo "=========================================="
echo " Installation Complete!                   "
echo " To start GazeGuard:                      "
echo "   ./venv/bin/python main.py              "
echo " Or launch GazeGuard from your GNOME app menu."
echo "=========================================="
