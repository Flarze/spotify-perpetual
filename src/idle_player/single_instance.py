"""Single-instance lock so duplicate launches do not stack polling daemons.

The lock is a small file holding the owning PID. It is created atomically with
``O_CREAT | O_EXCL`` so that two processes starting at the same moment (e.g. a
race between autostart entries at login) cannot both acquire it. A lock left by
a process that is no longer alive is treated as stale and reclaimed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import psutil


def default_lock_path() -> Path:
    """Per-user lock path in the system temp dir."""
    return Path(tempfile.gettempdir()) / "idle_player.lock"


def _holder_alive(lock_path: Path) -> bool:
    try:
        pid = int(lock_path.read_text().strip())
    except (ValueError, OSError):
        return False
    return psutil.pid_exists(pid)


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
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
    return False


def release(lock_path) -> None:
    """Remove the lock file. Idempotent."""
    try:
        Path(lock_path).unlink()
    except FileNotFoundError:
        pass
