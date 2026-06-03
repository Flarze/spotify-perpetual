"""Single-instance lock so duplicate launches do not stack polling daemons.

The lock is a small file holding the owning PID and that process's start time.
It is created atomically with ``O_CREAT | O_EXCL`` so that two processes
starting at the same moment (e.g. a race between autostart entries at login)
cannot both acquire it. A lock left by a process that is no longer alive is
treated as stale and reclaimed.

Recording the start time guards against PID reuse: after a crash the OS may
hand the dead daemon's PID to an unrelated process, which would make a bare
``pid_exists`` check report the lock as still held and refuse to start. The
holder is only considered alive when the live process's start time matches the
one recorded in the lock.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import psutil


def default_lock_path() -> Path:
    """Per-user lock path in the system temp dir."""
    return Path(tempfile.gettempdir()) / "idle_player.lock"


def _identity() -> str:
    """This process's lock payload: ``"<pid> <start_time>"`` (or just pid)."""
    pid = os.getpid()
    try:
        return f"{pid} {psutil.Process(pid).create_time()}"
    except psutil.Error:
        return str(pid)


def _holder_alive(lock_path: Path) -> bool:
    """True if the PID in the lock is a live process that still looks like ours.

    Reads ``"<pid> <start_time>"``. The PID must exist and, when a start time
    was recorded, the live process's start time must match it — otherwise the
    PID was recycled by an unrelated process and the lock is stale.
    """
    try:
        parts = lock_path.read_text().split()
    except OSError:
        return False
    if not parts:
        return False
    try:
        pid = int(parts[0])
    except ValueError:
        return False
    if not psutil.pid_exists(pid):
        return False
    if len(parts) < 2:
        return True  # legacy lock without a start time: trust pid_exists
    try:
        recorded = float(parts[1])
        actual = psutil.Process(pid).create_time()
    except (ValueError, psutil.Error):
        return True  # cannot verify; assume alive rather than stomp a live lock
    return abs(actual - recorded) < 1.0


def acquire(lock_path) -> bool:
    """Try to acquire the lock. Return True on success, False if held alive."""
    lock_path = Path(lock_path)
    for _ in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _holder_alive(lock_path):
                return False
            # Stale lock from a dead process: remove and retry once.
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            continue
        else:
            os.write(fd, _identity().encode())
            os.close(fd)
            return True
    return False


def release(lock_path) -> None:
    """Remove the lock file. Idempotent."""
    try:
        Path(lock_path).unlink()
    except FileNotFoundError:
        pass
