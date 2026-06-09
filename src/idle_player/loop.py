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
from .config import Config, app_dir, load_config
from .player import (
    PlaylistRotator,
    PremiumRequiredError,
    is_paused_with_track,
    pick_device,
    resume_playback,
    should_start_playback,
    start_playlist,
    track_label,
)
from .spotify_process import ensure_running
from .status import ApiStatusSource, SmtcStatusSource, smtc_available

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
    budget - the caller continues anyway, leaving the loop's normal error
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


def run_once(
    config: Config,
    sp,
    logger: logging.Logger,
    rotator=None,
    controller=None,
    status_source=None,
) -> str:
    """Run one decide-and-act cycle. Returns the action taken.

    Returns one of: "skip" (already playing, or a pending pause that resolved
    during the resume-delay grace), "resumed" (continued a paused track),
    "started", or "no_device" (still no active device after launching and
    retrying once).

    ``rotator`` chooses which playlist to start; without one the first
    configured playlist is used. The playlist is chosen once per cycle so the
    404 retry reuses the same selection (rotation advances per start, not per
    attempt). ``controller`` (optional) gets a human-readable status, including
    the current track name where known.

    ``status_source`` decides how playback state is read - the Web API or local
    SMTC. It defaults to the Web API so existing callers are unaffected; control
    (start/resume) always goes through the Web API client ``sp``.
    """
    if status_source is None:
        status_source = ApiStatusSource(sp)

    def _status(msg: str) -> None:
        if controller is not None:
            controller.set_status(msg)

    playback = status_source.get_playback()
    label = track_label(playback)
    if not should_start_playback(playback, config.paused_counts_as_playing):
        logger.info("playback active, nothing to do")
        _status(f"playing: {label}" if label else "music playing")
        return "skip"

    # A loaded-but-paused session is what triggered us. Optional grace period:
    # wait, then re-read. If the user resumed or switched track meanwhile, leave
    # it alone instead of fighting them. Applies to BOTH actions below (resume
    # in place, or start a fresh playlist), so a deliberate pause is never acted
    # on instantly when a delay is configured.
    if config.resume_delay_seconds > 0 and is_paused_with_track(playback):
        logger.info("paused; waiting %ss before acting", config.resume_delay_seconds)
        _status(f"paused - acting in {config.resume_delay_seconds}s")
        if _sleep(config.resume_delay_seconds, controller):
            return "skip"  # stop requested during the grace period
        playback = status_source.get_playback()
        label = track_label(playback)
        if not should_start_playback(playback, config.paused_counts_as_playing):
            logger.info("no longer idle after grace; leaving it alone")
            _status(f"playing: {label}" if label else "music playing")
            return "skip"

    # If configured, resume a paused track in place rather than starting a fresh
    # playlist. Rotation is untouched here - it only advances on a real start.
    if config.resume_paused_track and is_paused_with_track(playback):
        ensure_running(config.launch_wait_seconds)
        device_id = pick_device(sp, config.preferred_device_name)
        if resume_playback(
            sp, device_id, volume=config.volume, fade_in_seconds=config.fade_in_seconds
        ):
            logger.info("resumed paused track on device %s", device_id)
            _status(f"resumed: {label}" if label else "resumed paused track")
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
        _status("started playlist")
        return "started"

    # "No active device" 404: launch (if needed) and retry once.
    logger.info("no active device; launching Spotify and retrying")
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if _start(device_id):
        logger.info("started %s on device %s after relaunch", playlist_uri, device_id)
        _status("started playlist")
        return "started"

    logger.warning("no active device after retry; will try again next poll")
    _status("no Connect device")
    return "no_device"


def _make_status_source(config: Config, sp, logger: logging.Logger):
    """Pick the status backend for ``config.mode``.

    "hybrid" reads playback from local SMTC (no API status calls); if SMTC is
    unavailable (non-Windows, or winsdk missing) it logs and falls back to the
    Web API so the daemon still works. "api" (the default) always uses the
    Web API. Control always uses ``sp`` regardless of mode.
    """
    if config.mode == "hybrid":
        if smtc_available():
            logger.info("mode=hybrid: reading playback status from local SMTC")
            return SmtcStatusSource()
        logger.warning("mode=hybrid but SMTC unavailable; using Web API for status")
    return ApiStatusSource(sp)


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
    """Snapshot the modification times of the watched config files (in app_dir)."""
    base = app_dir()
    return {
        p: (os.path.getmtime(base / p) if (base / p).exists() else None)
        for p in paths
    }


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


def _sleep(delay, controller) -> bool:
    """Sleep for ``delay``. Return True if the loop should stop.

    With a controller, waits on its stop event so Quit is responsive. Without
    one, plain sleep with Ctrl-C handling (unchanged legacy behavior).
    """
    if controller is not None:
        return controller.stop_event.wait(delay)
    try:
        time.sleep(delay)
        return False
    except KeyboardInterrupt:
        return True


def run(config: Config, sp, controller=None, recorder=None) -> None:
    """Poll forever: each interval, run one cycle. Resilient to transient errors.

    Transient API/network errors are logged and the loop continues, backing off
    exponentially on repeated failures and resuming normal cadence on recovery.
    Config files are watched for edits and reloaded live. Ctrl-C
    (KeyboardInterrupt) exits cleanly.

    ``controller`` (optional) lets a UI pause/resume/stop the watcher and reads
    a status string the loop keeps updated. When omitted the loop runs forever
    as before.

    ``recorder`` (optional, a :class:`~idle_player.stats.StatsRecorder`) counts
    each cycle's outcome for ``idle-player stats``. Omitted in tests and
    library use; the entry points wire one in.
    """
    logger = setup_logging(config)
    if recorder is not None:
        recorder.start_session()
    rotator = PlaylistRotator(config.playlists(), config.playlist_selection)
    logger.info(
        "idle_player started; polling every %ss, %d playlist(s), selection=%s",
        config.poll_interval,
        len(config.playlists()),
        config.playlist_selection,
    )
    mtimes = _watch_mtimes()
    status_source = _make_status_source(config, sp, logger)
    failures = 0
    while True:
        if controller is not None and controller.stopped:
            logger.info("stop requested; shutting down")
            break

        config, sp, rotator, mtimes, reloaded = maybe_reload(
            config, sp, rotator, mtimes, logger
        )
        if reloaded:
            status_source = _make_status_source(config, sp, logger)

        if controller is not None and controller.paused:
            controller.set_status("paused (watcher off)")
            if _sleep(config.poll_interval, controller):
                break
            continue

        try:
            action = run_once(config, sp, logger, rotator, controller, status_source)
            failures = 0  # recovered: drop back to normal cadence
            if recorder is not None:
                recorder.record(action)
        except KeyboardInterrupt:
            logger.info("interrupted; shutting down")
            break
        except PremiumRequiredError as exc:
            # Free account: retrying never succeeds, so stop instead of looping.
            logger.error("%s", exc)
            if controller is not None:
                controller.set_status("stopped - Premium required")
            if recorder is not None:
                recorder.record("error")
            break
        except Exception:  # noqa: BLE001 - keep the daemon alive on transient errors
            failures += 1
            logger.exception("transient error; continuing")
            if controller is not None:
                controller.set_status("error - retrying")
            if recorder is not None:
                recorder.record("error")

        delay = _backoff_delay(config, failures)
        if failures:
            logger.warning(
                "backing off %ss after %d consecutive failure(s)", delay, failures
            )
        if _sleep(delay, controller):
            if controller is None:
                logger.info("interrupted; shutting down")
            break
