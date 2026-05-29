"""Playback state checks and start logic.

Decision logic is kept separate from API calls so it is unit-testable without
hitting Spotify (see tests/test_player.py).

Key decision: given a current_playback() response, should we start playback?
Edge case — paused-but-has-track vs. truly idle. Whether a paused session
counts as "listening" is a config flag (paused_counts_as_playing), not a
buried assumption.
"""
