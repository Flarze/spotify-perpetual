"""The polling loop, error handling, and logging.

Polls playback every poll_interval seconds. Transient API/network errors are
logged and the loop continues rather than killing the process. Logging is to a
rotating file so autostart/headless runs are debuggable.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .auth import build_client
from .config import Config, load_config
from .player import (
    PlaylistRotator,
    PremiumRequiredError,
    get_playback,
    is_paused_with_track,
    pick_device,
    resume_playback,
    should_start_playback,
    start_playlist,
)
from .spotify_process import ensure_running

LOGGER_NAME = "idle_player"

# Config files watched for live edits (relative to the working directory, the
# same place load_config reads them from).
WATCH_FILES = (".env", "config.yaml")

# Fields whose change requires rebuilding the Spotify client, not just swapping
# the config in place.
_AUTH_FIELDS = ("client_id", "client_secret", "redirect_uri", "token_cache_path")

# Host probed to decide whether the network is up at boot.
PROBE_HOST = "api.spotify.com"
PROBE_PORT = 443


def _probe(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def wait_for_network(config: Config, logger: logging.Logger, probe=_probe) -> bool:
    """Block until Spotify is reachable, or the attempt budget is exhausted.

    Autostart at login can fire before the network is up; without this the very
    first API call (or token refresh) fails. Retries a quick TCP probe up to
    ``network_wait_attempts`` times, ``network_wait_interval`` seconds apart.

    Returns True once reachable. Returns False if still unreachable after the
    budget — the caller continues anyway, leaving the loop's normal error
    handling to cope.
    """
    attempts = max(1, config.network_wait_attempts)
    for attempt in range(1, attempts + 1):
        if probe(PROBE_HOST, PROBE_PORT, config.network_probe_timeout):
            if attempt > 1:
                logger.info("network reachable after %d attempt(s)", attempt)
            return True
        if attempt < attempts:
            logger.info(
                "network not up yet (attempt %d/%d); retrying in %ss",
                attempt,
                attempts,
                config.network_wait_interval,
            )
            time.sleep(config.network_wait_interval)
    logger.warning(
        "network still unreachable after %d attempt(s); continuing anyway", attempts
    )
    return False


def setup_logging(config: Config) -> logging.Logger:
    """Configure and return the package logger with a rotating file handler."""
    log_path = Path(config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    # Avoid stacking duplicate handlers if called more than once.
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Console output so foreground runs are not silent. RotatingFileHandler is a
    # StreamHandler subclass, so match on exact type to detect the console one.
    if not any(type(h) is logging.StreamHandler for h in logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

    return logger


def run_once(config: Config, sp, logger: logging.Logger, rotator=None) -> str:
    """Run one decide-and-act cycle. Returns the action taken.

    Returns one of: "skip" (already playing), "resumed" (continued a paused
    track), "started", or "no_device" (still no active device after launching
    and retrying once).

    ``rotator`` chooses which playlist to start; without one the first
    configured playlist is used. The playlist is chosen once per cycle so the
    404 retry reuses the same selection (rotation advances per start, not per
    attempt).
    """
    playback = get_playback(sp)
    if not should_start_playback(playback, config.paused_counts_as_playing):
        logger.info("playback active, nothing to do")
        return "skip"

    # If configured, resume a paused track in place rather than starting a fresh
    # playlist. Rotation is untouched here — it only advances on a real start.
    if config.resume_paused_track and is_paused_with_track(playback):
        ensure_running(config.launch_wait_seconds)
        device_id = pick_device(sp, config.preferred_device_name)
        if resume_playback(
            sp, device_id, volume=config.volume, fade_in_seconds=config.fade_in_seconds
        ):
            logger.info("resumed paused track on device %s", device_id)
            return "resumed"
        logger.info("could not resume paused track; falling back to playlist")

    playlist_uri = rotator.next() if rotator is not None else config.playlists()[0]

    def _start(device_id):
        return start_playlist(
            sp,
            playlist_uri,
            device_id,
            shuffle=config.shuffle,
            repeat=config.repeat,
            volume=config.volume,
            fade_in_seconds=config.fade_in_seconds,
        )

    # Idle: make sure Spotify is up, pick a device, start the playlist.
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if _start(device_id):
        logger.info("started %s on device %s", playlist_uri, device_id)
        return "started"

    # "No active device" 404: launch (if needed) and retry once.
    logger.info("no active device; launching Spotify and retrying")
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if _start(device_id):
        logger.info("started %s on device %s after relaunch", playlist_uri, device_id)
        return "started"

    logger.warning("no active device after retry; will try again next poll")
    return "no_device"


def _backoff_delay(config: Config, failures: int) -> int:
    """Seconds to wait before the next cycle given consecutive failure count.

    ``failures == 0`` (last cycle succeeded) → normal ``poll_interval``. Each
    further consecutive failure multiplies the delay by ``backoff_factor``,
    capped at ``backoff_max_seconds``. So the first failure waits one normal
    interval, the second ``poll_interval * factor``, and so on, instead of
    hammering the API every ``poll_interval``.
    """
    if failures <= 0:
        return config.poll_interval
    delay = config.poll_interval * (config.backoff_factor ** (failures - 1))
    return min(delay, config.backoff_max_seconds)


def _watch_mtimes(paths=WATCH_FILES) -> dict:
    """Snapshot the modification times of the watched config files."""
    return {p: (os.path.getmtime(p) if os.path.exists(p) else None) for p in paths}


def maybe_reload(config, sp, rotator, mtimes, logger, load=load_config, build=build_client):
    """Reload config if a watched file changed since ``mtimes``.

    Returns ``(config, sp, rotator, mtimes, reloaded)``. On an unchanged config
    the inputs pass through. On a changed-but-invalid config the previous one is
    kept (the edit is logged, the daemon stays up). Credential changes rebuild
    the Spotify client; everything else is applied by swapping the config and
    rebuilding the playlist rotator.
    """
    current = _watch_mtimes()
    if current == mtimes:
        return config, sp, rotator, mtimes, False

    try:
        new_config = load()
    except Exception as exc:  # noqa: BLE001 - a bad edit must not kill the daemon
        logger.error("config changed but reload failed (%s); keeping previous", exc)
        return config, sp, rotator, current, False

    if any(getattr(config, f) != getattr(new_config, f) for f in _AUTH_FIELDS):
        sp = build(new_config)
        logger.info("config reloaded (credentials changed; rebuilt Spotify client)")
    else:
        logger.info(
            "config reloaded: %d playlist(s), selection=%s, shuffle=%s, repeat=%s",
            len(new_config.playlists()),
            new_config.playlist_selection,
            new_config.shuffle,
            new_config.repeat,
        )
    rotator = PlaylistRotator(new_config.playlists(), new_config.playlist_selection)
    return new_config, sp, rotator, current, True


def run(config: Config, sp) -> None:
    """Poll forever: each interval, run one cycle. Resilient to transient errors.

    Transient API/network errors are logged and the loop continues, backing off
    exponentially on repeated failures and resuming normal cadence on recovery.
    Config files are watched for edits and reloaded live. Ctrl-C
    (KeyboardInterrupt) exits cleanly.
    """
    logger = setup_logging(config)
    rotator = PlaylistRotator(config.playlists(), config.playlist_selection)
    logger.info(
        "idle_player started; polling every %ss, %d playlist(s), selection=%s",
        config.poll_interval,
        len(config.playlists()),
        config.playlist_selection,
    )
    mtimes = _watch_mtimes()
    failures = 0
    while True:
        config, sp, rotator, mtimes, _ = maybe_reload(
            config, sp, rotator, mtimes, logger
        )
        try:
            run_once(config, sp, logger, rotator)
            failures = 0  # recovered: drop back to normal cadence
        except KeyboardInterrupt:
            logger.info("interrupted; shutting down")
            break
        except PremiumRequiredError as exc:
            # Free account: retrying never succeeds, so stop instead of looping.
            logger.error("%s", exc)
            break
        except Exception:  # noqa: BLE001 - keep the daemon alive on transient errors
            failures += 1
            logger.exception("transient error; continuing")

        delay = _backoff_delay(config, failures)
        if failures:
            logger.warning(
                "backing off %ss after %d consecutive failure(s)", delay, failures
            )
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            logger.info("interrupted; shutting down")
            break
