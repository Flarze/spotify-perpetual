"""Load and validate configuration.

Reads credentials and settings from environment (.env) and an optional
config.yaml. Credentials are never hardcoded. Exposes a validated config
object consumed by the rest of the package.

Precedence: defaults < .env < config.yaml (YAML overrides env).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values


@dataclass
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str
    playlist_uri: str
    poll_interval: int = 30
    token_cache_path: str = ".cache"
    paused_counts_as_playing: bool = True
    preferred_device_name: str = ""
    launch_wait_seconds: int = 8
    backoff_factor: int = 2
    backoff_max_seconds: int = 600
    log_level: str = "INFO"
    log_file: str = "logs/idle_player.log"
    log_max_bytes: int = 1048576
    log_backup_count: int = 3


_REQUIRED = ("client_id", "client_secret", "redirect_uri", "playlist_uri")


def _normalize_playlist_uri(value: str) -> str:
    """Accept either a Spotify URI or an open.spotify.com link, return the URI.

    ``spotify:playlist:<id>`` is returned unchanged. A web link such as
    ``https://open.spotify.com/playlist/<id>?si=...`` is rewritten to
    ``spotify:playlist:<id>`` (query string dropped). Anything else is returned
    as-is for the caller/Spotify to reject.
    """
    value = value.strip()
    if value.startswith("https://open.spotify.com/"):
        path = urlparse(value).path.strip("/")  # e.g. "playlist/<id>"
        parts = path.split("/")
        if len(parts) >= 2:
            kind, item_id = parts[0], parts[1]
            return f"spotify:{kind}:{item_id}"
    return value


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _to_int(value, default: int) -> int:
    """Parse an int, falling back to default for None or blank values.

    Avoids ``int("")`` crashing when a user leaves an optional numeric field
    blank in .env.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return int(text)


def load_config(
    env_path: Optional[os.PathLike] = None,
    yaml_path: Optional[os.PathLike] = None,
) -> Config:
    """Build a validated Config from a .env file and optional config.yaml.

    Args:
        env_path: path to a .env file. Defaults to ".env" in the cwd.
        yaml_path: optional path to config.yaml whose keys override .env values.

    Raises:
        ValueError: if a required field is missing or empty, with the offending
            env var name in the message.
    """
    env_path = Path(env_path) if env_path is not None else Path(".env")
    env = dotenv_values(env_path) if env_path.exists() else {}

    values = {
        "client_id": env.get("SPOTIFY_CLIENT_ID"),
        "client_secret": env.get("SPOTIFY_CLIENT_SECRET"),
        "redirect_uri": env.get("SPOTIFY_REDIRECT_URI"),
        "playlist_uri": env.get("PLAYLIST_URI"),
        "poll_interval": env.get("POLL_INTERVAL"),
        "token_cache_path": env.get("TOKEN_CACHE_PATH"),
        "paused_counts_as_playing": env.get("PAUSED_COUNTS_AS_PLAYING"),
    }

    if yaml_path is not None and Path(yaml_path).exists():
        data = yaml.safe_load(Path(yaml_path).read_text()) or {}
        _merge_yaml(values, data)

    # Required fields must be present and non-empty.
    env_names = {
        "client_id": "SPOTIFY_CLIENT_ID",
        "client_secret": "SPOTIFY_CLIENT_SECRET",
        "redirect_uri": "SPOTIFY_REDIRECT_URI",
        "playlist_uri": "PLAYLIST_URI",
    }
    for field in _REQUIRED:
        if not values.get(field):
            raise ValueError(
                f"Missing required config: set {env_names[field]} in your .env "
                f"(or {field} in config.yaml)."
            )

    defaults = Config(client_id="", client_secret="", redirect_uri="", playlist_uri="")
    return Config(
        client_id=values["client_id"],
        client_secret=values["client_secret"],
        redirect_uri=values["redirect_uri"],
        playlist_uri=_normalize_playlist_uri(values["playlist_uri"]),
        poll_interval=_to_int(values.get("poll_interval"), defaults.poll_interval),
        token_cache_path=values["token_cache_path"] or defaults.token_cache_path,
        paused_counts_as_playing=(
            _to_bool(values["paused_counts_as_playing"])
            if values.get("paused_counts_as_playing") is not None
            else defaults.paused_counts_as_playing
        ),
        preferred_device_name=values.get("preferred_device_name", defaults.preferred_device_name),
        launch_wait_seconds=_to_int(values.get("launch_wait_seconds"), defaults.launch_wait_seconds),
        backoff_factor=_to_int(values.get("backoff_factor"), defaults.backoff_factor),
        backoff_max_seconds=_to_int(values.get("backoff_max_seconds"), defaults.backoff_max_seconds),
        log_level=values.get("log_level", defaults.log_level),
        log_file=values.get("log_file", defaults.log_file),
        log_max_bytes=_to_int(values.get("log_max_bytes"), defaults.log_max_bytes),
        log_backup_count=_to_int(values.get("log_backup_count"), defaults.log_backup_count),
    )


def _merge_yaml(values: dict, data: dict) -> None:
    """Override env-derived values with config.yaml keys (in place)."""
    for key in ("poll_interval", "playlist_uri", "paused_counts_as_playing", "token_cache_path"):
        if key in data:
            values[key] = data[key]

    device = data.get("device") or {}
    if "preferred_name" in device:
        values["preferred_device_name"] = device["preferred_name"]
    if "launch_wait_seconds" in device:
        values["launch_wait_seconds"] = device["launch_wait_seconds"]

    backoff = data.get("backoff") or {}
    if "factor" in backoff:
        values["backoff_factor"] = backoff["factor"]
    if "max_seconds" in backoff:
        values["backoff_max_seconds"] = backoff["max_seconds"]

    logging_cfg = data.get("logging") or {}
    if "level" in logging_cfg:
        values["log_level"] = logging_cfg["level"]
    if "file" in logging_cfg:
        values["log_file"] = logging_cfg["file"]
    if "max_bytes" in logging_cfg:
        values["log_max_bytes"] = logging_cfg["max_bytes"]
    if "backup_count" in logging_cfg:
        values["log_backup_count"] = logging_cfg["backup_count"]
