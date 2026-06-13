"""Playback status sources and SMTC (Windows) integration.

Two ways to read "what is Spotify doing right now":

- ``ApiStatusSource`` wraps the Web API ``current_playback()`` call - the
  original behavior. Needs a developer app + a Premium token, and each read is
  a network request that counts against the API rate limit.
- ``SmtcStatusSource`` reads Windows System Media Transport Controls (SMTC),
  the same local OS mechanism a Wallpaper Engine background uses to show the
  current track. It needs no developer app, no token, and no network: it reads
  the desktop app's published media session directly. It can only *read* -
  control (start/resume) still goes through the Web API.

Both return the subset of the ``current_playback()`` response shape that the
decision logic in :mod:`player` consumes::

    None  |  {"is_playing": bool, "item": {"name", "artists": [{"name"}]} | None}

The WinRT calls are isolated in ``_read_smtc`` / ``_winrt_subscribe``; the pure
mapping (``map_smtc``) and the listener's start/stop plumbing are unit-tested
without Windows, because the dev box is WSL and cannot read the Windows host's
SMTC.
"""

from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from .player import track_label

# SMTC normalized playback states.
PLAYING = "playing"
PAUSED = "paused"
STOPPED = "stopped"


class SmtcSnapshot(NamedTuple):
    """A point-in-time read of the Spotify SMTC session.

    ``status`` is one of PLAYING / PAUSED / STOPPED. ``title``/``artist`` are
    empty strings when no media properties are available (e.g. a stopped
    session with nothing loaded).
    """

    status: str
    title: str = ""
    artist: str = ""


def _item(snapshot: SmtcSnapshot) -> Optional[dict]:
    """Build the ``item`` sub-dict from a snapshot, or None when no track."""
    if not snapshot.title:
        return None
    artists = [{"name": snapshot.artist}] if snapshot.artist else []
    return {"name": snapshot.title, "artists": artists}


def map_smtc(snapshot: Optional[SmtcSnapshot]) -> Optional[dict]:
    """Map an SMTC snapshot to the ``current_playback()`` dict shape.

    ``None`` (no Spotify session at all) maps to ``None`` so the decision logic
    treats it as idle and starts playback. A stopped/closed session maps to an
    active-but-empty state (``item`` None), which also triggers a start.
    """
    if snapshot is None:
        return None
    if snapshot.status == PLAYING:
        return {"is_playing": True, "item": _item(snapshot)}
    if snapshot.status == PAUSED:
        return {"is_playing": False, "item": _item(snapshot)}
    # STOPPED / unknown: app is up but nothing loaded -> truly idle.
    return {"is_playing": False, "item": None}


def label_for(snapshot: Optional[SmtcSnapshot]) -> str:
    """A short human label for the tray: "Playing: Song - Artist" / "Idle"."""
    playback = map_smtc(snapshot)
    if playback is None:
        return "Idle"
    label = track_label(playback)
    state = (PLAYING if playback.get("is_playing") else PAUSED).capitalize()
    return f"{state}: {label}" if label else state


class ApiStatusSource:
    """Status via the Spotify Web API (wraps ``sp.current_playback()``)."""

    def __init__(self, sp):
        self._sp = sp

    def get_playback(self) -> Optional[dict]:
        return self._sp.current_playback()


class SmtcStatusSource:
    """Status via Windows SMTC - local, no network, no token.

    ``reader`` returns an :class:`SmtcSnapshot` or None. It defaults to the
    WinRT reader but is injectable so the mapping can be tested off-Windows.
    Read failures propagate so the loop's error handling backs off rather than
    silently treating an SMTC glitch as "idle" and restarting playback.
    """

    def __init__(self, reader: Optional[Callable[[], Optional[SmtcSnapshot]]] = None):
        self._reader = reader or _read_smtc

    def get_playback(self) -> Optional[dict]:
        return map_smtc(self._reader())


def smtc_available() -> bool:
    """True if the WinRT SMTC API can be imported (Windows + bindings present)."""
    try:
        _media_control()
    except Exception:  # noqa: BLE001 - any import failure means "not available"
        return False
    return True


def _media_control():
    """Return the ``...windows.media.control`` module from whichever WinRT
    binding is installed.

    ``winsdk`` (the older all-in-one bundle) ships wheels up to ~Python 3.12;
    the maintained successor splits the same projection into ``winrt-*``
    packages (module ``winrt.windows.media.control``), which carry wheels for
    newer Pythons. Both expose the identical WinRT API, so we try winsdk first
    and fall back to winrt.
    """
    try:
        from winsdk.windows.media import control
    except ImportError:
        from winrt.windows.media import control
    return control


# Transient COM/WinRT errors that mean "the media app was momentarily busy".
# The WinRT projection surfaces these as ``OSError`` with a signed ``winerror``
# HRESULT in the RPC_E_CALL_* family. They are spurious - a short in-place retry
# almost always succeeds - so we retry rather than let them propagate to the
# loop, where they would escalate the backoff (5s -> 10s -> 20s -> 40s) and stop
# monitoring playback for no real reason.
_RETRYABLE_HRESULTS = frozenset(
    {
        -2147418111,  # 0x80010001 RPC_E_CALL_REJECTED
        -2147418110,  # 0x80010002 RPC_E_CALL_CANCELED ("canceled by the message filter")
        -2147417846,  # 0x8001010A RPC_E_SERVERCALL_RETRYLATER
    }
)
SMTC_READ_ATTEMPTS = 3
SMTC_RETRY_SECONDS = 0.3


def _read_with_retry(read, attempts, retry_seconds, sleep) -> Optional[SmtcSnapshot]:
    """Call ``read`` (a 0-arg WinRT reader), retrying transient COM rejections.

    Only HRESULTs in :data:`_RETRYABLE_HRESULTS` are retried; any other error -
    and the final attempt - propagates so a genuine read failure still reaches
    the loop's backoff. Pure (``read``/``sleep`` injected) so it is unit-tested
    without WinRT.
    """
    for attempt in range(1, attempts + 1):
        try:
            return read()
        except OSError as exc:
            if (
                getattr(exc, "winerror", None) not in _RETRYABLE_HRESULTS
                or attempt == attempts
            ):
                raise
            sleep(retry_seconds)
    return None  # unreachable: the loop always returns or raises


def _read_smtc() -> Optional[SmtcSnapshot]:
    """Read the current Spotify SMTC session synchronously (Windows only).

    Returns None when no Spotify media session exists. Retries transient COM
    rejections; raises any other WinRT failure so the caller can distinguish
    "nothing playing" from "could not read". Spotify is matched by a substring
    of the source app id so both the desktop (``Spotify.exe``) and Microsoft
    Store builds match.
    """
    import asyncio
    import time

    return _read_with_retry(
        lambda: asyncio.run(_async_read_smtc()),
        SMTC_READ_ATTEMPTS,
        SMTC_RETRY_SECONDS,
        time.sleep,
    )


async def _async_read_smtc() -> Optional[SmtcSnapshot]:
    control = _media_control()
    Manager = control.GlobalSystemMediaTransportControlsSessionManager
    PlaybackStatus = control.GlobalSystemMediaTransportControlsSessionPlaybackStatus

    manager = await Manager.request_async()
    for session in manager.get_sessions():
        app_id = (session.source_app_user_model_id or "").lower()
        if "spotify" not in app_id:
            continue
        status = session.get_playback_info().playback_status
        props = await session.try_get_media_properties_async()
        title = getattr(props, "title", "") or ""
        artist = getattr(props, "artist", "") or ""
        if status == PlaybackStatus.PLAYING:
            normalized = PLAYING
        elif status == PlaybackStatus.PAUSED:
            normalized = PAUSED
        else:
            normalized = STOPPED
        return SmtcSnapshot(normalized, title, artist)
    return None


# How often the listener re-reads SMTC to refresh the tray (seconds). The read
# is a local OS call (no network), so a tight interval is cheap and gives a
# near-instant display without depending on WinRT event delivery.
LISTENER_POLL_SECONDS = 1.0


class SmtcListener:
    """Push SMTC track/status changes to a callback for near-instant tray display.

    The main poll loop only refreshes the displayed status once per
    ``poll_interval`` (e.g. 30s); this watches SMTC on a tight ~1s cadence and
    calls ``on_change(label)`` only when the label actually changes, so the tray
    reflects the current track within a second of it changing.

    ``subscribe(on_change) -> stop_callable`` runs the watcher on its own
    background thread; it is injectable so start/stop can be tested off-Windows.
    No-op (``start`` returns False) when SMTC is unavailable, so callers can
    start it unconditionally and fall back to the loop-driven status.
    """

    def __init__(
        self,
        subscribe: Optional[Callable[[Callable[[str], None]], Callable[[], None]]] = None,
        available: Callable[[], bool] = smtc_available,
        poll_seconds: float = LISTENER_POLL_SECONDS,
    ):
        self._subscribe = subscribe or (
            lambda on_change: _smtc_subscribe(on_change, poll_seconds)
        )
        self._available = available
        self._stop_fn: Optional[Callable[[], None]] = None

    def start(self, on_change: Callable[[str], None]) -> bool:
        """Begin listening; return whether a listener was actually started."""
        if self._stop_fn is not None or not self._available():
            return False
        self._stop_fn = self._subscribe(on_change)
        return True

    def stop(self) -> None:
        """Stop listening (idempotent)."""
        if self._stop_fn is not None:
            try:
                self._stop_fn()
            finally:
                self._stop_fn = None


def _smtc_subscribe(
    on_change: Callable[[str], None], poll_seconds: float = LISTENER_POLL_SECONDS
) -> Callable[[], None]:
    """Watch SMTC on a background thread; call ``on_change`` when the label
    changes. Returns a stop function.

    WinRT change events proved unreliable to deliver from a headless/daemon
    thread, so this polls ``_read_smtc`` every ``poll_seconds`` instead - the
    read is an OS call with no network cost. Read failures are swallowed (the
    next tick retries); a display refresh must never crash the app. Windows-only;
    the read itself is untested under WSL (the dev host cannot read SMTC).
    """
    import threading

    stop_event = threading.Event()

    def run() -> None:
        last = None
        while not stop_event.is_set():
            try:
                label = label_for(_read_smtc())
            except Exception:  # noqa: BLE001 - a display refresh must never crash
                label = None
            if label is not None and label != last:
                last = label
                on_change(label)
            stop_event.wait(poll_seconds)

    thread = threading.Thread(target=run, name="smtc-listener", daemon=True)
    thread.start()

    return stop_event.set
