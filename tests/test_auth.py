"""Tests for auth client construction.

build_client wires a spotipy.Spotify with a SpotifyOAuth auth manager. Building
the client triggers no network/browser (that happens on first token fetch), so
we can assert the auth manager is configured with the right scopes and cache
path without hitting Spotify.
"""

import spotipy

from idle_player.auth import SCOPES, build_client
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
