"""Tests for logging setup and one polling iteration.

run_once performs a single decide-and-act cycle (no sleep, no infinite loop),
so it is unit-testable with a fake spotipy client and a stubbed
ensure_running. The infinite run() loop itself is thin glue verified manually.
"""

import logging
from logging.handlers import RotatingFileHandler

from spotipy.exceptions import SpotifyException

from idle_player import loop
from idle_player.config import Config
from idle_player.player import PremiumRequiredError


def make_config(tmp_path, **overrides):
    base = dict(
        client_id="cid",
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        playlist_uri="spotify:playlist:abc",
        launch_wait_seconds=0,
        log_file=str(tmp_path / "logs" / "app.log"),
        log_max_bytes=2048,
        log_backup_count=3,
    )
    base.update(overrides)
    return Config(**base)


class FakeSpotify:
    def __init__(self, playback=None, devices=None, start_errors=None):
        self._playback = playback
        self._devices = devices or []
        # start_errors: list of exceptions/None applied per start_playback call.
        self._start_errors = list(start_errors or [])
        self.start_calls = []

    def current_playback(self):
        return self._playback

    def devices(self):
        return {"devices": self._devices}

    def start_playback(self, context_uri=None, device_id=None):
        self.start_calls.append({"context_uri": context_uri, "device_id": device_id})
        if self._start_errors:
            err = self._start_errors.pop(0)
            if err is not None:
                raise err

    def shuffle(self, state, device_id=None):
        pass

    def repeat(self, state, device_id=None):
        pass


def stub_ensure_running(monkeypatch):
    calls = []
    monkeypatch.setattr(loop, "ensure_running", lambda wait: calls.append(wait) or True)
    return calls


# --- setup_logging --------------------------------------------------------


def test_setup_logging_configures_rotating_handler(tmp_path):
    config = make_config(tmp_path, log_level="DEBUG")

    logger = loop.setup_logging(config)

    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert handlers, "expected a RotatingFileHandler"
    handler = handlers[0]
    assert handler.maxBytes == 2048
    assert handler.backupCount == 3
    assert logger.level == logging.DEBUG
    # Parent log directory is created.
    assert (tmp_path / "logs").is_dir()
    # A console handler is attached so foreground runs are not silent.
    assert any(
        type(h) is logging.StreamHandler for h in logger.handlers
    ), "expected a console StreamHandler"


# --- run_once -------------------------------------------------------------


def test_run_once_skips_when_already_playing(tmp_path, monkeypatch):
    calls = stub_ensure_running(monkeypatch)
    sp = FakeSpotify(playback={"is_playing": True, "item": {"uri": "x"}})

    result = loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"))

    assert result == "skip"
    assert sp.start_calls == []
    assert calls == []


def test_run_once_starts_when_idle(tmp_path, monkeypatch):
    calls = stub_ensure_running(monkeypatch)
    sp = FakeSpotify(
        playback=None,
        devices=[{"id": "d1", "name": "Laptop", "is_active": True}],
    )

    result = loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"))

    assert result == "started"
    assert len(sp.start_calls) == 1
    assert sp.start_calls[0]["device_id"] == "d1"
    assert calls == [0]  # ensure_running called once with launch_wait_seconds


def test_run_once_uses_rotator_and_advances_once_per_start(tmp_path, monkeypatch):
    from idle_player.player import PlaylistRotator

    stub_ensure_running(monkeypatch)
    rotator = PlaylistRotator(["spotify:playlist:a", "spotify:playlist:b"], "rotate")
    sp = FakeSpotify(playback=None, devices=[{"id": "d1", "name": "L", "is_active": True}])

    loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"), rotator)
    loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"), rotator)

    # Two starts -> rotated through both playlists in order.
    assert [c["context_uri"] for c in sp.start_calls] == [
        "spotify:playlist:a",
        "spotify:playlist:b",
    ]


def test_run_once_404_retry_keeps_same_playlist(tmp_path, monkeypatch):
    from idle_player.player import PlaylistRotator

    stub_ensure_running(monkeypatch)
    err404 = SpotifyException(404, -1, "no device", reason="NO_ACTIVE_DEVICE")
    rotator = PlaylistRotator(["a", "b"], "rotate")
    sp = FakeSpotify(
        playback=None,
        devices=[{"id": "d1", "name": "L", "is_active": True}],
        start_errors=[err404, None],
    )

    loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"), rotator)

    # Both attempts use the same selection (rotation advanced once, not twice).
    assert [c["context_uri"] for c in sp.start_calls] == ["a", "a"]


def test_run_once_relaunches_and_retries_on_404(tmp_path, monkeypatch):
    calls = stub_ensure_running(monkeypatch)
    err404 = SpotifyException(404, -1, "no device", reason="NO_ACTIVE_DEVICE")
    sp = FakeSpotify(
        playback=None,
        devices=[{"id": "d1", "name": "Laptop", "is_active": True}],
        start_errors=[err404, None],  # first attempt 404, retry succeeds
    )

    result = loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"))

    assert result == "started"
    assert len(sp.start_calls) == 2
    assert calls == [0, 0]  # ensure_running before each attempt


def test_run_once_no_device_after_retry(tmp_path, monkeypatch):
    stub_ensure_running(monkeypatch)
    err404 = SpotifyException(404, -1, "no device", reason="NO_ACTIVE_DEVICE")
    sp = FakeSpotify(
        playback=None,
        devices=[],
        start_errors=[err404, err404],
    )

    result = loop.run_once(make_config(tmp_path), sp, logging.getLogger("test"))

    assert result == "no_device"
    assert len(sp.start_calls) == 2


# --- _backoff_delay -------------------------------------------------------


def test_backoff_delay_normal_cadence_when_no_failures(tmp_path):
    config = make_config(tmp_path, poll_interval=30)

    assert loop._backoff_delay(config, 0) == 30


def test_backoff_delay_grows_exponentially(tmp_path):
    config = make_config(tmp_path, poll_interval=30, backoff_factor=2, backoff_max_seconds=10000)

    # First failure waits one normal interval, then doubles each time.
    assert loop._backoff_delay(config, 1) == 30
    assert loop._backoff_delay(config, 2) == 60
    assert loop._backoff_delay(config, 3) == 120
    assert loop._backoff_delay(config, 4) == 240


def test_backoff_delay_caps_at_max(tmp_path):
    config = make_config(tmp_path, poll_interval=30, backoff_factor=2, backoff_max_seconds=200)

    assert loop._backoff_delay(config, 5) == 200  # 30*2^4 = 480, capped to 200
    assert loop._backoff_delay(config, 99) == 200


# --- wait_for_network -----------------------------------------------------


def test_wait_for_network_returns_immediately_when_up(tmp_path, monkeypatch):
    config = make_config(tmp_path, network_wait_attempts=5, network_wait_interval=5)
    slept = []
    monkeypatch.setattr(loop.time, "sleep", lambda s: slept.append(s))

    ok = loop.wait_for_network(config, logging.getLogger("test"), probe=lambda *a: True)

    assert ok is True
    assert slept == []  # no waiting when reachable on first try


def test_wait_for_network_retries_then_succeeds(tmp_path, monkeypatch):
    config = make_config(tmp_path, network_wait_attempts=5, network_wait_interval=5)
    slept = []
    monkeypatch.setattr(loop.time, "sleep", lambda s: slept.append(s))
    results = iter([False, False, True])

    ok = loop.wait_for_network(config, logging.getLogger("test"), probe=lambda *a: next(results))

    assert ok is True
    assert slept == [5, 5]  # slept between the two failed attempts


def test_wait_for_network_gives_up_after_budget(tmp_path, monkeypatch):
    config = make_config(tmp_path, network_wait_attempts=3, network_wait_interval=5)
    slept = []
    monkeypatch.setattr(loop.time, "sleep", lambda s: slept.append(s))

    ok = loop.wait_for_network(config, logging.getLogger("test"), probe=lambda *a: False)

    assert ok is False
    assert slept == [5, 5]  # no sleep after the final attempt


# --- maybe_reload ---------------------------------------------------------


def test_maybe_reload_no_change_is_noop(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    monkeypatch.setattr(loop, "_watch_mtimes", lambda: {".env": 1.0})
    load_called = []

    cfg, sp, rot, mtimes, reloaded = loop.maybe_reload(
        config, "SP", "ROT", {".env": 1.0}, logging.getLogger("test"),
        load=lambda: load_called.append(True),
    )

    assert reloaded is False
    assert cfg is config and sp == "SP" and rot == "ROT"
    assert load_called == []  # unchanged files -> no reload


def test_maybe_reload_applies_new_config(tmp_path, monkeypatch):
    old = make_config(tmp_path, playlist_uri="spotify:playlist:old")
    new = make_config(tmp_path, playlist_uris=["spotify:playlist:a", "spotify:playlist:b"])
    monkeypatch.setattr(loop, "_watch_mtimes", lambda: {".env": 2.0})

    cfg, sp, rot, mtimes, reloaded = loop.maybe_reload(
        old, "SP", "ROT", {".env": 1.0}, logging.getLogger("test"),
        load=lambda: new, build=lambda c: "NEW_SP",
    )

    assert reloaded is True
    assert cfg is new
    assert sp == "SP"  # no auth change -> client reused
    assert rot.next() == "spotify:playlist:a"  # rotator rebuilt from new config
    assert mtimes == {".env": 2.0}


def test_maybe_reload_rebuilds_client_on_auth_change(tmp_path, monkeypatch):
    old = make_config(tmp_path, client_id="old")
    new = make_config(tmp_path, client_id="new")
    monkeypatch.setattr(loop, "_watch_mtimes", lambda: {".env": 2.0})

    cfg, sp, rot, mtimes, reloaded = loop.maybe_reload(
        old, "SP", "ROT", {".env": 1.0}, logging.getLogger("test"),
        load=lambda: new, build=lambda c: "NEW_SP",
    )

    assert reloaded is True
    assert sp == "NEW_SP"  # credentials changed -> client rebuilt


def test_maybe_reload_keeps_previous_on_bad_edit(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    monkeypatch.setattr(loop, "_watch_mtimes", lambda: {".env": 2.0})

    def boom():
        raise ValueError("bad yaml")

    cfg, sp, rot, mtimes, reloaded = loop.maybe_reload(
        config, "SP", "ROT", {".env": 1.0}, logging.getLogger("test"), load=boom,
    )

    assert reloaded is False
    assert cfg is config  # previous config kept; daemon stays up
    assert mtimes == {".env": 2.0}  # but mtime advanced so we don't retry endlessly


# --- run() premium handling -----------------------------------------------


def test_run_stops_on_premium_required_without_sleeping(tmp_path, monkeypatch):
    config = make_config(tmp_path)

    def boom(cfg, sp, logger, rotator=None):
        raise PremiumRequiredError("needs premium")

    slept = []
    monkeypatch.setattr(loop, "run_once", boom)
    monkeypatch.setattr(loop.time, "sleep", lambda s: slept.append(s))

    # Returns (does not loop forever) and never sleeps/retries.
    loop.run(config, object())

    assert slept == []
