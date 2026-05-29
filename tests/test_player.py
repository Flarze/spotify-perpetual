"""Tests for the playback decision logic.

The decision function (player module) is pure. It takes a current_playback()
response shape and config flags, and returns whether to start playback. These
tests mock spotipy responses; they never hit the network.
"""

from idle_player.player import should_start_playback


def test_nothing_playing_no_device_starts():
    # current_playback() returns None when there is no active device / nothing.
    assert should_start_playback(None, paused_counts_as_playing=True) is True


def test_actively_playing_does_nothing():
    playback = {"is_playing": True, "item": {"uri": "spotify:track:x"}}
    assert should_start_playback(playback, paused_counts_as_playing=True) is False


def test_paused_counts_as_playing_does_nothing():
    playback = {"is_playing": False, "item": {"uri": "spotify:track:x"}}
    assert should_start_playback(playback, paused_counts_as_playing=True) is False


def test_paused_not_counting_starts():
    playback = {"is_playing": False, "item": {"uri": "spotify:track:x"}}
    assert should_start_playback(playback, paused_counts_as_playing=False) is True
