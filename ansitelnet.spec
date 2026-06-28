# -*- mode: python ; coding: utf-8 -*-
import sys

_excludes = [
    'tkinter', '_tkinter',
    'asyncio',
    'unittest', 'doctest', 'pdb', 'pydoc',
    'email', 'mailbox', 'imaplib', 'smtplib', 'poplib', 'ftplib', 'nntplib',
    'sqlite3', '_sqlite3',
    'ssl', '_ssl', '_hashlib',
    'http.server', 'xmlrpc',
    'distutils', 'lib2to3',
    'multiprocessing',
    'curses.textpad',
    'test', 'tests',
    'pip', 'setuptools', 'pkg_resources',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['windows_curses'] if sys.platform == 'win32' else [],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ansitelnet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=sys.platform != 'win32',
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
