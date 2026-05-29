"""Cross-platform Spotify process detection and launch.

Detection uses psutil to avoid OS-specific output parsing. Launch branches per
OS and relies on the OS to resolve Spotify's location (don't assume install
path):
    Windows : start spotify  (or the spotify: URI)
    macOS   : open -a Spotify
    Linux   : spotify URI / spotify command

After launching, wait a few seconds for Spotify to register as a Connect
device before retrying playback. A "no active device" 404 is the trigger for
this launch fallback, not a crash.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import List, Optional

import psutil


def _matches_spotify(name: Optional[str]) -> bool:
    """True if a process name is the Spotify desktop app (not a helper/clone).

    Matches case-insensitively on the stem so ``Spotify`` and ``Spotify.exe``
    both match, while ``spotifyd``, ``spotify-tui`` and ``Spotify Helper`` do
    not.
    """
    if not name:
        return False
    stem = name.rsplit(".", 1)[0] if name.lower().endswith(".exe") else name
    return stem.strip().lower() == "spotify"


def _launch_command(platform: str) -> Optional[List[str]]:
    """Per-OS command to launch Spotify, or None on Windows.

    None signals the caller to use ``os.startfile("spotify:")``. We rely on the
    OS to resolve Spotify's location rather than hardcoding an install path.
    """
    if platform == "darwin":
        return ["open", "-a", "Spotify"]
    if platform.startswith("linux"):
        return ["xdg-open", "spotify:"]
    return None  # win32


def is_running() -> bool:
    """True if a Spotify desktop process is currently running."""
    for proc in psutil.process_iter(["name"]):
        try:
            if _matches_spotify(proc.info.get("name")):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def launch() -> None:
    """Launch Spotify via the OS, without assuming its install path."""
    command = _launch_command(sys.platform)
    if command is None:  # win32
        os.startfile("spotify:")  # type: ignore[attr-defined]
        return
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_running(wait_seconds: int) -> bool:
    """Ensure Spotify is running; launch and wait if not.

    Returns True if Spotify was already running. If it was launched, sleeps
    ``wait_seconds`` so it can register as a Connect device, then returns False.
    """
    if is_running():
        return True
    launch()
    time.sleep(wait_seconds)
    return False
