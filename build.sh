#!/bin/bash
# Lokaler Linux-Build: erzeugt dist/ansitelnet
set -e
cd "$(dirname "$0")"

VENV=".buildenv"

if [ ! -d "$VENV" ]; then
    echo "Erstelle virtualenv..."
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --quiet --upgrade pyinstaller

"$VENV/bin/python" -m PyInstaller --clean ansitelnet.spec

echo ""
echo "Fertig: dist/ansitelnet"
echo "  Installieren: cp dist/ansitelnet ~/.local/bin/ansitelnet"
