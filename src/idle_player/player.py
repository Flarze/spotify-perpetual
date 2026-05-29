"""Playback state checks and start logic.

Decision logic is kept separate from API calls so it is unit-testable without
hitting Spotify (see tests/test_player.py).

Key decision: given a current_playback() response, should we start playback?
Edge case: paused-but-has-track vs. truly idle. Whether a paused session
counts as "listening" is a config flag (paused_counts_as_playing), not a
buried assumption.
"""

from __future__ import annotations

from typing import Optional

from spotipy.exceptions import SpotifyException


def should_start_playback(
    playback: Optional[dict], paused_counts_as_playing: bool
) -> bool:
    """Decide whether to (re)start the configured playlist.

    Args:
        playback: the `current_playback()` response shape, or None when there
            is no active device / nothing is playing.
        paused_counts_as_playing: if True, a paused-but-loaded session counts as
            "listening" and we leave it alone.

    Returns:
        True if we should start playback, False to leave it be.
    """
    # No active device / nothing playing -> start (triggers launch fallback).
    if playback is None:
        return True

    if playback.get("is_playing"):
        return False

    # Active device but nothing loaded -> truly idle, always (re)start.
    if playback.get("item") is None:
        return True

    # Paused with a loaded track: honor the config flag.
    return not paused_counts_as_playing


def get_playback(sp) -> Optional[dict]:
    """Return the current_playback() response, or None when nothing is active."""
    return sp.current_playback()


def pick_device(sp, preferred_name: str = "") -> Optional[str]:
    """Choose a Connect device id, or None if there is nothing to play on.

    Selection order:
        1. a device whose name matches ``preferred_name`` (case-insensitive),
           if a preferred name was given. No match returns None so the caller
           does not silently play on the wrong speaker.
        2. otherwise the active device, if any.
        3. otherwise the first device.
    """
    devices = sp.devices().get("devices", [])
    if not devices:
        return None

    if preferred_name:
        target = preferred_name.strip().lower()
        for device in devices:
            if device.get("name", "").strip().lower() == target:
                return device.get("id")
        return None

    for device in devices:
        if device.get("is_active"):
            return device.get("id")

    return devices[0].get("id")


def start_playlist(sp, playlist_uri: str, device_id: Optional[str] = None) -> bool:
    """Start the playlist; return whether playback was started.

    Returns True on success. A "no active device" 404 returns False instead of
    raising: that is the trigger to launch Spotify and retry, not a crash. Any
    other error propagates.
    """
    try:
        sp.start_playback(context_uri=playlist_uri, device_id=device_id)
        return True
    except SpotifyException as exc:
        if exc.http_status == 404:
            return False
        raise
