"""Tests for the pure parts of Spotify process detect + launch.

Name matching and per-OS launch command selection are pure functions, tested
here. The psutil/subprocess wiring (is_running, launch, ensure_running) is thin
glue verified manually on the target OS.
"""

import pytest

from idle_player.spotify_process import _launch_command, _matches_spotify


@pytest.mark.parametrize(
    "name",
    ["Spotify", "spotify", "SPOTIFY", "Spotify.exe", "spotify.exe"],
)
def test_matches_spotify_true(name):
    assert _matches_spotify(name) is True


@pytest.mark.parametrize(
    "name",
    ["spotifyd", "chrome", "Spotify Helper", "spotify-tui", "", None],
)
def test_matches_spotify_false(name):
    assert _matches_spotify(name) is False


def test_launch_command_macos():
    assert _launch_command("darwin") == ["open", "-a", "Spotify"]


def test_launch_command_linux():
    assert _launch_command("linux") == ["xdg-open", "spotify:"]


def test_launch_command_windows_uses_startfile():
    # None signals the caller to use os.startfile("spotify:").
    assert _launch_command("win32") is None
