"""Tests for the single-instance lock.

acquire() creates the lock file atomically (O_EXCL) so simultaneous launches at
login cannot both win. A lock held by a dead PID is treated as stale and
reclaimed. psutil.pid_exists is monkeypatched so tests do not depend on real
process state.
"""

import os

from idle_player import single_instance


def test_acquire_on_fresh_path_succeeds(tmp_path):
    lock = tmp_path / "idle.lock"
    assert single_instance.acquire(lock) is True
    # Payload is "<pid> <start_time>"; the pid is the first field.
    assert lock.read_text().split()[0] == str(os.getpid())


def test_acquire_fails_when_holder_alive(tmp_path, monkeypatch):
    lock = tmp_path / "idle.lock"
    lock.write_text("4242")
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: True)
    assert single_instance.acquire(lock) is False


def test_acquire_reclaims_stale_lock(tmp_path, monkeypatch):
    lock = tmp_path / "idle.lock"
    lock.write_text("4242")  # dead pid
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: False)
    assert single_instance.acquire(lock) is True
    assert lock.read_text().split()[0] == str(os.getpid())


def test_acquire_reclaims_garbage_lock(tmp_path, monkeypatch):
    lock = tmp_path / "idle.lock"
    lock.write_text("not-a-pid")
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: True)
    assert single_instance.acquire(lock) is True


def test_acquire_reclaims_recycled_pid(tmp_path, monkeypatch):
    """A live PID whose start time differs from the lock's is a recycled PID."""
    lock = tmp_path / "idle.lock"
    lock.write_text("4242 1000.0")  # recorded start time
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: True)

    class _Proc:
        def __init__(self, pid):
            pass

        def create_time(self):
            return 9999.0  # different process now holds pid 4242

    monkeypatch.setattr(single_instance.psutil, "Process", _Proc)
    assert single_instance.acquire(lock) is True
    assert lock.read_text().split()[0] == str(os.getpid())


def test_acquire_fails_when_start_time_matches(tmp_path, monkeypatch):
    """Same PID and matching start time means the real holder is still alive."""
    lock = tmp_path / "idle.lock"
    lock.write_text("4242 1000.0")
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: True)

    class _Proc:
        def __init__(self, pid):
            pass

        def create_time(self):
            return 1000.0

    monkeypatch.setattr(single_instance.psutil, "Process", _Proc)
    assert single_instance.acquire(lock) is False


def test_release_removes_lock(tmp_path):
    lock = tmp_path / "idle.lock"
    single_instance.acquire(lock)
    single_instance.release(lock)
    assert not lock.exists()
    # release is idempotent
    single_instance.release(lock)
