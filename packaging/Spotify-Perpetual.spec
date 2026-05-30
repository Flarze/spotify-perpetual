# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for a single-file, windowed, branded Spotify Perpetual.exe.
# Build from the repo root:
#     pyinstaller packaging/Spotify-Perpetual.spec --noconfirm
#
# Produces dist/Spotify Perpetual.exe (no console; double-click runs the tray).

block_cipher = None

a = Analysis(
    ['entry.py'],
    pathex=['../src'],
    binaries=[],
    datas=[],
    # PyInstaller misses these without help: the pystray Windows backend and the
    # third-party libs imported lazily / by name.
    hiddenimports=[
        'pystray._win32',
        'PIL.Image',
        'PIL.ImageDraw',
        'spotipy',
        'dotenv',
        'yaml',
        'psutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Spotify Perpetual',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,                       # windowed: no console window
    disable_windowed_traceback=False,
    version='version_info.txt',  # branded file properties (beside this spec)
    icon=None,                           # set to 'packaging/icon.ico' if you add one
)
