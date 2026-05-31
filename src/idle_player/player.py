"""Playback state checks and start logic.

Decision logic is kept separate from API calls so it is unit-testable without
hitting Spotify (see tests/test_player.py).

Key decision: given a current_playback() response, should we start playback?
Edge case: paused-but-has-track vs. truly idle. Whether a paused session
counts as "listening" is a config flag (paused_counts_as_playing), not a
buried assumption.
"""

from __future__ import annotations

import random
import time
from typing import List, Optional, Sequence

from spotipy.exceptions import SpotifyException


class PlaylistRotator:
    """Pick which playlist to start, given a list and a selection strategy.

    ``rotate`` cycles through the list in order, advancing each time a playlist
    is actually started. ``random`` picks one at random each time. A single
    playlist degenerates to always returning it.
    """

    def __init__(self, playlists: Sequence[str], strategy: str = "rotate"):
        if not playlists:
            raise ValueError("PlaylistRotator needs at least one playlist")
        self._playlists: List[str] = list(playlists)
        self._strategy = strategy
        self._index = 0

    def next(self) -> str:
        """Return the next playlist URI, advancing rotation state."""
        if self._strategy == "random":
            return random.choice(self._playlists)
        uri = self._playlists[self._index % len(self._playlists)]
        self._index += 1
        return uri


class PremiumRequiredError(Exception):
    """Raised when Spotify rejects a playback command for lack of Premium.

    Remote playback control is a Premium-only feature; a free account gets a
    403 that will never succeed on retry, so the loop treats this as fatal and
    surfaces a clear message rather than hammering every poll.
    """


def _is_premium_required(exc: SpotifyException) -> bool:
    """True if a 403 looks like the Premium-required playback restriction."""
    text = " ".join(str(x) for x in (exc.reason, exc.msg) if x).lower()
    return "premium" in text


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


def track_label(playback: Optional[dict]) -> Optional[str]:
    """Return "Song — Artist" for the current item, or None if unavailable."""
    item = (playback or {}).get("item") or {}
    name = item.get("name")
    if not name:
        return None
    artists = item.get("artists") or []
    who = ", ".join(a.get("name", "") for a in artists if a.get("name"))
    return f"{name} — {who}" if who else name


def is_paused_with_track(playback: Optional[dict]) -> bool:
    """True if a track is loaded but paused (vs. truly idle / no device)."""
    return (
        playback is not None
        and not playback.get("is_playing")
        and playback.get("item") is not None
    )


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


def start_playlist(
    sp,
    playlist_uri: str,
    device_id: Optional[str] = None,
    shuffle: bool = False,
    repeat: str = "off",
    volume: Optional[int] = None,
    fade_in_seconds: int = 0,
) -> bool:
    """Start the playlist; return whether playback was started.

    Returns True on success. A "no active device" 404 returns False instead of
    raising: that is the trigger to launch Spotify and retry, not a crash. A
    Premium-required 403 raises PremiumRequiredError so the caller can stop with
    a clear message. Any other error propagates.

    After playback starts, applies the ``shuffle`` and ``repeat`` modes. These
    are best-effort: a failure to set them does not undo the started playback.
    """
    try:
        sp.start_playback(context_uri=playlist_uri, device_id=device_id)
    except SpotifyException as exc:
        if exc.http_status == 404:
            return False
        if exc.http_status == 403 and _is_premium_required(exc):
            raise PremiumRequiredError(
                "Spotify playback control requires Premium; this account cannot "
                "be controlled remotely. Free accounts are not supported."
            ) from exc
        raise

    _apply_modes(sp, device_id, shuffle, repeat)
    _apply_volume(sp, device_id, volume, fade_in_seconds)
    return True


def resume_playback(
    sp,
    device_id: Optional[str] = None,
    volume: Optional[int] = None,
    fade_in_seconds: int = 0,
) -> bool:
    """Resume the current (paused) track without changing the context.

    Uses transfer_playback (not start_playback) so a session paused on another
    device — e.g. a phone — is moved to ``device_id`` and resumed there. Calling
    start_playback with a device_id that does not already own the session gets a
    403 "Restriction violated"; transfer_playback with force_play=True is the
    supported way to hand the active session to another Connect device.

    Returns True on success. A "no active device" 404 returns False so the
    caller can fall back to starting a playlist. A Premium-required 403 raises
    PremiumRequiredError. Any other error propagates. Volume/fade are applied
    after a successful resume (best-effort).
    """
    try:
        sp.transfer_playback(device_id, force_play=True)
    except SpotifyException as exc:
        if exc.http_status == 404:
            return False
        if exc.http_status == 403 and _is_premium_required(exc):
            raise PremiumRequiredError(
                "Spotify playback control requires Premium; this account cannot "
                "be controlled remotely. Free accounts are not supported."
            ) from exc
        raise

    _apply_volume(sp, device_id, volume, fade_in_seconds)
    return True


def _apply_modes(sp, device_id, shuffle: bool, repeat: str) -> None:
    """Set shuffle and repeat after playback starts. Best-effort: never raises."""
    try:
        sp.shuffle(shuffle, device_id=device_id)
        sp.repeat(repeat, device_id=device_id)
    except SpotifyException:
        # Playback already started; these toggles are non-critical extras.
        pass


def _apply_volume(
    sp,
    device_id,
    volume: Optional[int],
    fade_in_seconds: int,
    sleep=time.sleep,
) -> None:
    """Set volume (optionally fading in) after playback starts. Best-effort.

    Does nothing when there is no target volume and no fade. With a fade the
    volume ramps from 0 up to the target (``volume``, or 100 if only a fade is
    configured) over ``fade_in_seconds``. Never raises: volume control is a
    non-critical extra and requires Premium + an active device.
    """
    if volume is None and fade_in_seconds <= 0:
        return
    target = 100 if volume is None else volume
    try:
        if fade_in_seconds > 0:
            steps = max(1, min(fade_in_seconds, 20))
            sp.volume(0, device_id=device_id)
            for i in range(1, steps + 1):
                sp.volume(round(target * i / steps), device_id=device_id)
                if i < steps:
                    sleep(fade_in_seconds / steps)
        else:
            sp.volume(target, device_id=device_id)
    except SpotifyException:
        pass
