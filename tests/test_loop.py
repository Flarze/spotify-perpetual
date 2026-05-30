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
