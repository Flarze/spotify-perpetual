"""Tests for auth client construction.

build_client wires a spotipy.Spotify with a SpotifyOAuth auth manager. Building
the client triggers no network/browser (that happens on first token fetch), so
we can assert the auth manager is configured with the right scopes and cache
path without hitting Spotify.
"""

import spotipy
from spotipy.oauth2 import SpotifyOauthError

from idle_player import auth as auth_mod
from idle_player.auth import (
    SCOPES,
    TOKEN_INVALID,
    TOKEN_MISSING,
    TOKEN_OK,
    build_client,
    run_auth_flow,
    token_health,
)
from idle_player.config import Config


def make_config(**overrides):
    base = dict(
        client_id="cid",
        client_secret="secret",
        redirect_uri="http://localhost:8888/callback",
        playlist_uri="spotify:playlist:abc",
        token_cache_path="/tmp/idle_player_test_cache",
    )
    base.update(overrides)
    return Config(**base)


def test_build_client_returns_spotify_instance():
    client = build_client(make_config())
    assert isinstance(client, spotipy.Spotify)


def test_auth_manager_has_required_scopes():
    client = build_client(make_config())
    scope = client.auth_manager.scope
    assert "user-read-playback-state" in scope
    assert "user-modify-playback-state" in scope


def test_auth_manager_uses_configured_cache_path():
    client = build_client(make_config(token_cache_path="/tmp/custom_cache"))
    assert client.auth_manager.cache_handler.cache_path == "/tmp/custom_cache"


def test_auth_manager_uses_credentials():
    client = build_client(make_config(client_id="myid", redirect_uri="http://127.0.0.1:9999/cb"))
    assert client.auth_manager.client_id == "myid"
    assert client.auth_manager.redirect_uri == "http://127.0.0.1:9999/cb"


def test_open_browser_defaults_true():
    client = build_client(make_config())
    assert client.auth_manager.open_browser is True


def test_open_browser_can_be_disabled():
    client = build_client(make_config(), open_browser=False)
    assert client.auth_manager.open_browser is False


# --- token_health ---------------------------------------------------------


class FakeAuthManager:
    """Stand-in for SpotifyOAuth: cached token + controllable expiry/refresh."""

    def __init__(self, token, expired=False, refresh_error=False):
        self._token = token
        self._expired = expired
        self._refresh_error = refresh_error
        self.refreshed = False

        manager = self

        class _Handler:
            def get_cached_token(self):
                return manager._token

        self.cache_handler = _Handler()

    def is_token_expired(self, token_info):
        return self._expired

    def refresh_access_token(self, refresh_token):
        self.refreshed = True
        if self._refresh_error:
            raise SpotifyOauthError("invalid_grant")


def test_token_health_missing_when_no_cache():
    am = FakeAuthManager(token=None)
    assert token_health(make_config(), auth_manager=am) == TOKEN_MISSING


def test_token_health_ok_when_token_valid():
    am = FakeAuthManager(token={"access_token": "x"}, expired=False)
    assert token_health(make_config(), auth_manager=am) == TOKEN_OK
    assert am.refreshed is False  # no network when not expired


def test_token_health_ok_when_expired_but_refreshable():
    am = FakeAuthManager(
        token={"access_token": "x", "refresh_token": "r"}, expired=True
    )
    assert token_health(make_config(), auth_manager=am) == TOKEN_OK
    assert am.refreshed is True


def test_token_health_invalid_when_expired_no_refresh_token():
    am = FakeAuthManager(token={"access_token": "x"}, expired=True)
    assert token_health(make_config(), auth_manager=am) == TOKEN_INVALID


def test_token_health_invalid_when_refresh_rejected():
    am = FakeAuthManager(
        token={"access_token": "x", "refresh_token": "r"},
        expired=True,
        refresh_error=True,
    )
    assert token_health(make_config(), auth_manager=am) == TOKEN_INVALID


# --- run_auth_flow --------------------------------------------------------


def test_run_auth_flow_clears_cache_and_authorizes(tmp_path, monkeypatch):
    cache = tmp_path / ".cache"
    cache.write_text("stale token")
    config = make_config(token_cache_path=str(cache))

    flow = {}

    class _AM:
        def get_access_token(self, as_dict=True):
            flow["called"] = True
            flow["cache_existed_at_call"] = cache.exists()

    monkeypatch.setattr(
        auth_mod, "build_auth_manager", lambda c, open_browser=True: flow.update(browser=open_browser) or _AM()
    )

    run_auth_flow(config, open_browser=False)

    assert flow["called"] is True
    assert flow["browser"] is False
    # Stale cache removed before the flow runs (forces full re-login).
    assert flow["cache_existed_at_call"] is False
