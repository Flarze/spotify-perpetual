"""Tests for the config loader.

load_config reads credentials/settings from a .env file and an optional
config.yaml (YAML overrides env). It returns a validated Config dataclass and
raises a clear error when a required field is missing.
"""

import pytest

from idle_player.config import Config, load_config


def write_env(path, **overrides):
    """Write a .env file with sensible defaults, overridable per-test."""
    fields = {
        "SPOTIFY_CLIENT_ID": "cid",
        "SPOTIFY_CLIENT_SECRET": "secret",
        "SPOTIFY_REDIRECT_URI": "http://localhost:8888/callback",
        "PLAYLIST_URI": "spotify:playlist:abc",
        "POLL_INTERVAL": "30",
        "TOKEN_CACHE_PATH": ".cache",
        "PAUSED_COUNTS_AS_PLAYING": "true",
    }
    fields.update(overrides)
    lines = [f"{k}={v}" for k, v in fields.items() if v is not None]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_loads_required_fields_from_env(tmp_path):
    env = write_env(tmp_path / ".env")

    config = load_config(env_path=env)

    assert isinstance(config, Config)
    assert config.client_id == "cid"
    assert config.client_secret == "secret"
    assert config.redirect_uri == "http://localhost:8888/callback"
    assert config.playlist_uri == "spotify:playlist:abc"


def test_parses_typed_fields(tmp_path):
    env = write_env(tmp_path / ".env", POLL_INTERVAL="15", PAUSED_COUNTS_AS_PLAYING="false")

    config = load_config(env_path=env)

    assert config.poll_interval == 15
    assert isinstance(config.poll_interval, int)
    assert config.paused_counts_as_playing is False


def test_defaults_applied_when_optional_missing(tmp_path):
    env = write_env(
        tmp_path / ".env",
        POLL_INTERVAL=None,
        TOKEN_CACHE_PATH=None,
        PAUSED_COUNTS_AS_PLAYING=None,
    )

    config = load_config(env_path=env)

    assert config.poll_interval == 30
    assert config.token_cache_path == ".cache"
    assert config.paused_counts_as_playing is True
    assert config.preferred_device_name == ""
    assert config.launch_wait_seconds == 8
    assert config.log_level == "INFO"


def test_missing_required_field_raises_readable_error(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI="")

    with pytest.raises(ValueError) as exc:
        load_config(env_path=env)

    assert "PLAYLIST_URI" in str(exc.value)


def test_playlist_uri_already_in_uri_form_unchanged(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI="spotify:playlist:37i9dQZF1DX")
    config = load_config(env_path=env)
    assert config.playlist_uri == "spotify:playlist:37i9dQZF1DX"


def test_playlist_url_normalized_to_uri(tmp_path):
    env = write_env(
        tmp_path / ".env",
        PLAYLIST_URI="https://open.spotify.com/playlist/37i9dQZF1DX?si=abc123",
    )
    config = load_config(env_path=env)
    assert config.playlist_uri == "spotify:playlist:37i9dQZF1DX"


def test_playlist_url_without_query_normalized(tmp_path):
    env = write_env(
        tmp_path / ".env",
        PLAYLIST_URI="https://open.spotify.com/playlist/37i9dQZF1DX",
    )
    config = load_config(env_path=env)
    assert config.playlist_uri == "spotify:playlist:37i9dQZF1DX"


def test_yaml_overrides_env(tmp_path):
    env = write_env(tmp_path / ".env", POLL_INTERVAL="30")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "poll_interval: 60\n"
        "paused_counts_as_playing: false\n"
        "device:\n"
        "  preferred_name: Living Room\n"
        "  launch_wait_seconds: 12\n"
        "logging:\n"
        "  level: DEBUG\n"
        "  file: logs/app.log\n"
        "  max_bytes: 2048\n"
        "  backup_count: 5\n"
    )

    config = load_config(env_path=env, yaml_path=yaml_path)

    assert config.poll_interval == 60
    assert config.paused_counts_as_playing is False
    assert config.preferred_device_name == "Living Room"
    assert config.launch_wait_seconds == 12
    assert config.log_level == "DEBUG"
    assert config.log_file == "logs/app.log"
    assert config.log_max_bytes == 2048
    assert config.log_backup_count == 5
