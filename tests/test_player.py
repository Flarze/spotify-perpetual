"""Tests for the playback decision logic and the thin playback I/O wrappers.

The decision function (should_start_playback) is pure. The I/O wrappers
(get_playback, pick_device, start_playlist) take a spotipy client; here we pass
a fake client so nothing hits the network.
"""

import pytest
from spotipy.exceptions import SpotifyException

from idle_player.player import (
    get_playback,
    pick_device,
    should_start_playback,
    start_playlist,
)


class FakeSpotify:
    """Minimal stand-in for spotipy.Spotify recording calls."""

    def __init__(self, playback=None, devices=None, start_error=None):
        self._playback = playback
        self._devices = devices or []
        self._start_error = start_error
        self.start_calls = []

    def current_playback(self):
        return self._playback

    def devices(self):
        return {"devices": self._devices}

    def start_playback(self, context_uri=None, device_id=None):
        self.start_calls.append({"context_uri": context_uri, "device_id": device_id})
        if self._start_error is not None:
            raise self._start_error


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


def test_idle_active_device_no_item_starts_regardless_of_flag():
    # Device active but nothing loaded (e.g. playlist finished/stopped).
    # This is truly idle, not a user pause, so we restart even when
    # paused_counts_as_playing is True.
    playback = {"is_playing": False, "item": None}
    assert should_start_playback(playback, paused_counts_as_playing=True) is True
    assert should_start_playback(playback, paused_counts_as_playing=False) is True


# --- get_playback ---------------------------------------------------------


def test_get_playback_passthrough():
    sp = FakeSpotify(playback={"is_playing": True})
    assert get_playback(sp) == {"is_playing": True}


# --- pick_device ----------------------------------------------------------


def test_pick_device_none_when_no_devices():
    sp = FakeSpotify(devices=[])
    assert pick_device(sp, preferred_name="") is None


def test_pick_device_prefers_named_match_case_insensitive():
    sp = FakeSpotify(devices=[
        {"id": "a", "name": "Laptop", "is_active": True},
        {"id": "b", "name": "Living Room", "is_active": False},
    ])
    assert pick_device(sp, preferred_name="living room") == "b"


def test_pick_device_falls_back_to_active_when_no_preferred():
    sp = FakeSpotify(devices=[
        {"id": "a", "name": "Laptop", "is_active": False},
        {"id": "b", "name": "Phone", "is_active": True},
    ])
    assert pick_device(sp, preferred_name="") == "b"


def test_pick_device_falls_back_to_first_when_none_active():
    sp = FakeSpotify(devices=[
        {"id": "a", "name": "Laptop", "is_active": False},
        {"id": "b", "name": "Phone", "is_active": False},
    ])
    assert pick_device(sp, preferred_name="") == "a"


def test_pick_device_none_when_preferred_not_found():
    sp = FakeSpotify(devices=[{"id": "a", "name": "Laptop", "is_active": True}])
    assert pick_device(sp, preferred_name="Kitchen") is None


# --- start_playlist -------------------------------------------------------


def test_start_playlist_success_returns_true():
    sp = FakeSpotify()
    assert start_playlist(sp, "spotify:playlist:x", device_id="a") is True
    assert sp.start_calls == [{"context_uri": "spotify:playlist:x", "device_id": "a"}]


def test_start_playlist_no_active_device_404_returns_false():
    err = SpotifyException(404, -1, "No active device", reason="NO_ACTIVE_DEVICE")
    sp = FakeSpotify(start_error=err)
    assert start_playlist(sp, "spotify:playlist:x") is False


def test_start_playlist_reraises_other_errors():
    err = SpotifyException(403, -1, "Forbidden")
    sp = FakeSpotify(start_error=err)
    with pytest.raises(SpotifyException):
        start_playlist(sp, "spotify:playlist:x")
