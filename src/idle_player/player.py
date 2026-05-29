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

    # Paused with a loaded track: honor the config flag.
    return not paused_counts_as_playing
