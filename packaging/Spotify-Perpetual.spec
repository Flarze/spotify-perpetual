# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for a windowed, branded Spotify Perpetual app.
# Build from the repo root:
#     pyinstaller packaging/Spotify-Perpetual.spec --noconfirm
#
# Produces a ONE-DIR build: dist/Spotify Perpetual/Spotify Perpetual.exe plus
# its dependencies. One-dir (not one-file) is deliberate: it has no runtime
# self-extraction step, so it starts faster and avoids the antivirus
# false-positives and "failed to open archive" extraction errors that plague
# unsigned one-file PyInstaller exes. The Inno Setup installer bundles the whole
# folder, so users still just run one Setup.exe.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# SMTC (mode=hybrid) uses the winrt-* bindings, imported lazily by name in
# status.py, so PyInstaller cannot discover them on its own. Collect the whole
# winrt namespace (native .pyd modules + metadata) when it is installed; skip
# cleanly for an api-only build where it is absent.
smtc_datas, smtc_binaries, smtc_hidden = [], [], []
try:
    smtc_datas, smtc_binaries, smtc_hidden = collect_all('winrt')
except Exception:
    pass

a = Analysis(
    ['entry.py'],
    pathex=['../src'],
    binaries=smtc_binaries,
    datas=smtc_datas,
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
        # SMTC binding (mode=hybrid); harmless if winrt is not installed.
        'winrt.windows.media.control',
    ] + smtc_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter must NOT be excluded: the first-run setup form and login dialog
    # (gui_setup.py) are tkinter. PyInstaller's tkinter hook bundles the Tcl/Tk
    # runtime automatically once it is no longer excluded.
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,               # one-dir: binaries go in COLLECT below
    name='Spotify Perpetual',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX packing is a major antivirus false-positive trigger on unsigned
    # PyInstaller exes (Defender flags it as a virus). Leave it off.
    upx=False,
    console=False,                       # windowed: no console window
    disable_windowed_traceback=False,
    version='version_info.txt',  # branded file properties (beside this spec)
    icon=None,                           # set to 'packaging/icon.ico' if you add one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='Spotify Perpetual',            # -> dist/Spotify Perpetual/
)
