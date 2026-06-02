"""Cross-thread control for the polling loop.

A Controller lets a UI (e.g. the system-tray icon) pause/resume the watcher,
ask it to stop, and read a human-readable status - while the loop runs on a
background thread. It is just two threading.Events plus a status string, so it
is trivially testable without any GUI.
"""

from __future__ import annotations

import threading


class Controller:
    """Shared pause/stop flags and status text for the running loop."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._status = "starting"
        self._track = ""
        self._lock = threading.Lock()

    # --- stop ---
    def stop(self) -> None:
        self._stop.set()

    @property
    def stop_event(self) -> threading.Event:
        return self._stop

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    # --- pause ---
    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def toggle_pause(self) -> None:
        self.resume() if self.paused else self.pause()

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    # --- status ---
    def set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def status(self) -> str:
        with self._lock:
            return self._status

    # --- track (SMTC-driven, instant) ---
    def set_track(self, track: str) -> None:
        """Set the currently-displayed track label (pushed by the SMTC listener)."""
        with self._lock:
            self._track = track

    def track(self) -> str:
        """The last track label seen via SMTC, or "" if none."""
        with self._lock:
            return self._track
