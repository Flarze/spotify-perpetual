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


def test_blank_numeric_env_uses_default(tmp_path):
    # A user blanking an optional numeric field must not crash with int("").
    env = write_env(tmp_path / ".env", POLL_INTERVAL="")
    config = load_config(env_path=env)
    assert config.poll_interval == 30


def test_missing_credential_raises_readable_error(tmp_path):
    env = write_env(tmp_path / ".env", SPOTIFY_CLIENT_ID="")

    with pytest.raises(ValueError) as exc:
        load_config(env_path=env)

    assert "SPOTIFY_CLIENT_ID" in str(exc.value)


def test_missing_playlist_raises_readable_error(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI="")

    with pytest.raises(ValueError) as exc:
        load_config(env_path=env)

    msg = str(exc.value).lower()
    assert "playlist" in msg


def test_playlists_comma_separated_env(tmp_path):
    env = write_env(
        tmp_path / ".env",
        PLAYLIST_URI=None,
        PLAYLISTS="spotify:playlist:a, spotify:playlist:b ,spotify:playlist:c",
    )
    config = load_config(env_path=env)
    assert config.playlists() == [
        "spotify:playlist:a",
        "spotify:playlist:b",
        "spotify:playlist:c",
    ]


def test_playlists_comma_separated_yaml(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI=None)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("playlists: spotify:playlist:a, spotify:playlist:b\n")
    config = load_config(env_path=env, yaml_path=yaml_path)
    assert config.playlists() == ["spotify:playlist:a", "spotify:playlist:b"]


def test_playlists_single_string_yaml(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI=None)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("playlists: https://open.spotify.com/playlist/37i9dQZF1DX\n")
    config = load_config(env_path=env, yaml_path=yaml_path)
    assert config.playlists() == ["spotify:playlist:37i9dQZF1DX"]


def test_playlists_key_takes_precedence_over_legacy(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI="spotify:playlist:legacy")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("playlists: spotify:playlist:new1, spotify:playlist:new2\n")
    config = load_config(env_path=env, yaml_path=yaml_path)
    assert config.playlists() == ["spotify:playlist:new1", "spotify:playlist:new2"]


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


def test_yaml_auto_discovered_next_to_env(tmp_path):
    # No yaml_path passed: a config.yaml beside the .env is found and applied.
    env = write_env(tmp_path / ".env", POLL_INTERVAL="30")
    (tmp_path / "config.yaml").write_text("poll_interval: 90\n")

    config = load_config(env_path=env)

    assert config.poll_interval == 90


def test_yaml_overrides_backoff(tmp_path):
    env = write_env(tmp_path / ".env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("backoff:\n  factor: 3\n  max_seconds: 120\n")

    config = load_config(env_path=env, yaml_path=yaml_path)

    assert config.backoff_factor == 3
    assert config.backoff_max_seconds == 120


def test_volume_and_fade_defaults(tmp_path):
    config = load_config(env_path=write_env(tmp_path / ".env"))
    assert config.volume is None  # unset = leave device volume alone
    assert config.fade_in_seconds == 0


def test_volume_and_fade_from_yaml(tmp_path):
    env = write_env(tmp_path / ".env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("volume: 55\nfade_in_seconds: 3\n")
    config = load_config(env_path=env, yaml_path=yaml_path)
    assert config.volume == 55
    assert config.fade_in_seconds == 3


def test_volume_blank_stays_none(tmp_path):
    env = write_env(tmp_path / ".env", VOLUME="")
    assert load_config(env_path=env).volume is None


def test_invalid_volume_raises(tmp_path):
    env = write_env(tmp_path / ".env", VOLUME="150")
    with pytest.raises(ValueError) as exc:
        load_config(env_path=env)
    assert "volume" in str(exc.value).lower()


def test_resume_paused_track_defaults_false(tmp_path):
    config = load_config(env_path=write_env(tmp_path / ".env"))
    assert config.resume_paused_track is False


def test_resume_paused_track_from_env(tmp_path):
    env = write_env(tmp_path / ".env", RESUME_PAUSED_TRACK="true")
    assert load_config(env_path=env).resume_paused_track is True


def test_single_playlist_back_compat(tmp_path):
    env = write_env(tmp_path / ".env", PLAYLIST_URI="spotify:playlist:abc")
    config = load_config(env_path=env)
    assert config.playlist_uri == "spotify:playlist:abc"
    assert config.playlists() == ["spotify:playlist:abc"]
    assert config.shuffle is False
    assert config.repeat == "off"
    assert config.playlist_selection == "rotate"


def test_yaml_playlist_list_and_modes(tmp_path):
    env = write_env(tmp_path / ".env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "playlist_uris:\n"
        "  - https://open.spotify.com/playlist/aaa?si=x\n"
        "  - spotify:playlist:bbb\n"
        "playlist_selection: random\n"
        "shuffle: true\n"
        "repeat: context\n"
    )
    config = load_config(env_path=env, yaml_path=yaml_path)
    # URLs normalized; list preserved; single playlist_uri backs first entry.
    assert config.playlists() == ["spotify:playlist:aaa", "spotify:playlist:bbb"]
    assert config.playlist_uri == "spotify:playlist:aaa"
    assert config.playlist_selection == "random"
    assert config.shuffle is True
    assert config.repeat == "context"


def test_yaml_playlist_list_satisfies_required_without_single(tmp_path):
    # A yaml list alone is enough; no PLAYLIST_URI needed.
    env = write_env(tmp_path / ".env", PLAYLIST_URI=None)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("playlist_uris:\n  - spotify:playlist:only\n")
    config = load_config(env_path=env, yaml_path=yaml_path)
    assert config.playlists() == ["spotify:playlist:only"]


def test_invalid_repeat_raises(tmp_path):
    env = write_env(tmp_path / ".env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("repeat: loop\n")
    with pytest.raises(ValueError) as exc:
        load_config(env_path=env, yaml_path=yaml_path)
    assert "repeat" in str(exc.value)


def test_invalid_selection_raises(tmp_path):
    env = write_env(tmp_path / ".env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("playlist_selection: shuffle\n")
    with pytest.raises(ValueError) as exc:
        load_config(env_path=env, yaml_path=yaml_path)
    assert "playlist_selection" in str(exc.value)


def test_yaml_can_supply_credentials_standalone(tmp_path):
    # config.yaml alone satisfies required fields when .env lacks them.
    env = tmp_path / ".env"  # does not exist
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "client_id: yid\n"
        "client_secret: ysecret\n"
        "redirect_uri: http://127.0.0.1:8888/callback\n"
        "playlist_uri: https://open.spotify.com/playlist/37i9dQZF1DX\n"
    )

    config = load_config(env_path=env, yaml_path=yaml_path)

    assert config.client_id == "yid"
    assert config.client_secret == "ysecret"
    assert config.redirect_uri == "http://127.0.0.1:8888/callback"
    # Normalization still applies to a yaml-supplied playlist URL.
    assert config.playlist_uri == "spotify:playlist:37i9dQZF1DX"
