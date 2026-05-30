"""The polling loop, error handling, and logging.

Polls playback every poll_interval seconds. Transient API/network errors are
logged and the loop continues rather than killing the process. Logging is to a
rotating file so autostart/headless runs are debuggable.
"""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config
from .player import (
    PremiumRequiredError,
    get_playback,
    pick_device,
    should_start_playback,
    start_playlist,
)
from .spotify_process import ensure_running

LOGGER_NAME = "idle_player"


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


def run_once(config: Config, sp, logger: logging.Logger) -> str:
    """Run one decide-and-act cycle. Returns the action taken.

    Returns one of: "skip" (already playing), "started", or "no_device" (still
    no active device after launching and retrying once).
    """
    playback = get_playback(sp)
    if not should_start_playback(playback, config.paused_counts_as_playing):
        logger.info("playback active, nothing to do")
        return "skip"

    # Idle: make sure Spotify is up, pick a device, start the playlist.
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if start_playlist(sp, config.playlist_uri, device_id):
        logger.info("started playlist on device %s", device_id)
        return "started"

    # "No active device" 404: launch (if needed) and retry once.
    logger.info("no active device; launching Spotify and retrying")
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if start_playlist(sp, config.playlist_uri, device_id):
        logger.info("started playlist on device %s after relaunch", device_id)
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


def run(config: Config, sp) -> None:
    """Poll forever: each interval, run one cycle. Resilient to transient errors.

    Transient API/network errors are logged and the loop continues, backing off
    exponentially on repeated failures and resuming normal cadence on recovery.
    Ctrl-C (KeyboardInterrupt) exits cleanly.
    """
    logger = setup_logging(config)
    logger.info("idle_player started; polling every %ss", config.poll_interval)
    failures = 0
    while True:
        try:
            run_once(config, sp, logger)
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
