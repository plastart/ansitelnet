VENV := .buildenv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: linux install clean

# ── Linux-Binary (lokal) ──────────────────────────────────────────────────────

linux: $(VENV)
	$(PY) -m PyInstaller --clean ansitelnet.spec
	@echo "→  dist/ansitelnet"

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pyinstaller

install: linux
	install -Dm755 dist/ansitelnet ~/.local/bin/ansitelnet
	@echo "Installiert: ~/.local/bin/ansitelnet"

# ── Windows-Binary via Wine (lokal) ──────────────────────────────────────────
#
# Voraussetzungen:
#   sudo apt install wine
#   # Windows-Python 3.x installer herunterladen und in Wine installieren:
#   wine python-3.13.x-amd64.exe /quiet InstallAllUsers=0 PrependPath=1
#   wine pip install pyinstaller windows-curses
#
# Danach:
#   make windows

WINE_PY ?= wine python

windows:
	$(WINE_PY) -m PyInstaller --clean ansitelnet.spec
	@echo "→  dist/ansitelnet.exe"

# ── Aufräumen ─────────────────────────────────────────────────────────────────

clean:
	rm -rf build dist \
	    ansitelnet/__pycache__ ansitelnet/ui/__pycache__ \
	    __pycache__
