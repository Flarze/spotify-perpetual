"""Tests for status sources and the SMTC listener.

The WinRT calls (_read_smtc / _smtc_subscribe) are isolated and not exercised
here — the dev box is WSL and cannot read the Windows host's SMTC. What is
tested is the pure mapping (map_smtc / label_for), the source wrappers, and the
listener's start/stop plumbing, all with injected fakes.
"""

import pytest

from idle_player.status import (
    ApiStatusSource,
    SmtcListener,
    SmtcSnapshot,
    SmtcStatusSource,
    _read_with_retry,
    label_for,
    map_smtc,
)


# --- map_smtc -------------------------------------------------------------


def test_map_smtc_none_is_idle():
    assert map_smtc(None) is None


def test_map_smtc_playing():
    snap = SmtcSnapshot("playing", "Song", "Artist")
    assert map_smtc(snap) == {
        "is_playing": True,
        "item": {"name": "Song", "artists": [{"name": "Artist"}]},
    }


def test_map_smtc_paused_with_track():
    snap = SmtcSnapshot("paused", "Song", "Artist")
    pb = map_smtc(snap)
    assert pb["is_playing"] is False
    assert pb["item"]["name"] == "Song"


def test_map_smtc_stopped_is_active_but_empty():
    # Stopped/closed: app is up but nothing loaded -> truly idle (item None).
    assert map_smtc(SmtcSnapshot("stopped")) == {"is_playing": False, "item": None}


def test_map_smtc_paused_without_title_has_no_item():
    assert map_smtc(SmtcSnapshot("paused", "", "")) == {"is_playing": False, "item": None}


def test_map_smtc_track_without_artist():
    pb = map_smtc(SmtcSnapshot("playing", "Song", ""))
    assert pb["item"] == {"name": "Song", "artists": []}


# --- label_for ------------------------------------------------------------


def test_label_for_idle():
    assert label_for(None) == "Idle"


def test_label_for_playing():
    assert label_for(SmtcSnapshot("playing", "Song", "Artist")) == "Playing: Song — Artist"


def test_label_for_paused():
    assert label_for(SmtcSnapshot("paused", "Song", "Artist")) == "Paused: Song — Artist"


def test_label_for_stopped_has_no_track():
    assert label_for(SmtcSnapshot("stopped")) == "Paused"


# --- ApiStatusSource / SmtcStatusSource -----------------------------------


def test_api_status_source_delegates_to_client():
    class FakeSp:
        def current_playback(self):
            return {"is_playing": True}

    assert ApiStatusSource(FakeSp()).get_playback() == {"is_playing": True}


def test_smtc_status_source_maps_injected_reader():
    src = SmtcStatusSource(reader=lambda: SmtcSnapshot("playing", "S", "A"))
    assert src.get_playback()["is_playing"] is True


def test_smtc_status_source_read_failure_propagates():
    # A WinRT read failure must not be swallowed as "idle" (which would restart
    # playback); it propagates so the loop's error handling backs off.
    def boom():
        raise RuntimeError("winrt blew up")

    with pytest.raises(RuntimeError):
        SmtcStatusSource(reader=boom).get_playback()


# --- _read_with_retry (transient COM rejection handling) ------------------


def _oserror(winerror):
    exc = OSError("com rejected")
    exc.winerror = winerror
    return exc


def test_read_with_retry_returns_first_success():
    sleeps = []
    snap = SmtcSnapshot("playing", "S", "A")
    assert _read_with_retry(lambda: snap, 3, 0.3, sleeps.append) is snap
    assert sleeps == []  # no retry needed


def test_read_with_retry_recovers_after_transient_com_reject():
    # WinError -2147418110 = RPC_E_CALL_CANCELED ("canceled by the message
    # filter"), the error seen in the logs. Second attempt succeeds.
    calls = []
    sleeps = []

    def read():
        calls.append(1)
        if len(calls) == 1:
            raise _oserror(-2147418110)
        return SmtcSnapshot("paused", "S", "A")

    result = _read_with_retry(read, 3, 0.3, sleeps.append)
    assert result.status == "paused"
    assert len(calls) == 2
    assert sleeps == [0.3]  # backed off once between attempts


def test_read_with_retry_exhausts_attempts_then_raises():
    sleeps = []

    def read():
        raise _oserror(-2147418110)

    with pytest.raises(OSError):
        _read_with_retry(read, 3, 0.3, sleeps.append)
    assert sleeps == [0.3, 0.3]  # slept between the 3 attempts, not after last


def test_read_with_retry_does_not_retry_other_oserror():
    sleeps = []

    def read():
        raise _oserror(-1)  # not a transient COM rejection

    with pytest.raises(OSError):
        _read_with_retry(read, 3, 0.3, sleeps.append)
    assert sleeps == []  # propagated immediately, no retry


# --- SmtcListener ---------------------------------------------------------


def test_listener_noop_when_smtc_unavailable():
    calls = []
    listener = SmtcListener(
        subscribe=lambda on_change: calls.append("subscribed"),
        available=lambda: False,
    )
    assert listener.start(lambda label: None) is False
    assert calls == []


def test_listener_starts_and_stops():
    stopped = []
    subscribed = []

    def fake_subscribe(on_change):
        subscribed.append(on_change)
        return lambda: stopped.append(True)

    listener = SmtcListener(subscribe=fake_subscribe, available=lambda: True)

    assert listener.start(lambda label: None) is True
    assert len(subscribed) == 1
    # Second start is a no-op (already running).
    assert listener.start(lambda label: None) is False
    assert len(subscribed) == 1

    listener.stop()
    assert stopped == [True]
    # Stop is idempotent.
    listener.stop()
    assert stopped == [True]


def test_listener_passes_callback_through_to_subscribe():
    received = {}

    def fake_subscribe(on_change):
        received["cb"] = on_change
        on_change("playing: X — Y")
        return lambda: None

    seen = []
    SmtcListener(subscribe=fake_subscribe, available=lambda: True).start(seen.append)

    assert seen == ["playing: X — Y"]


def test_listener_passes_poll_seconds_to_default_subscribe(monkeypatch):
    import idle_player.status as status

    seen = {}

    def fake_smtc_subscribe(on_change, poll_seconds):
        seen["poll_seconds"] = poll_seconds
        return lambda: None

    monkeypatch.setattr(status, "_smtc_subscribe", fake_smtc_subscribe)
    SmtcListener(available=lambda: True, poll_seconds=2.5).start(lambda label: None)

    assert seen["poll_seconds"] == 2.5
