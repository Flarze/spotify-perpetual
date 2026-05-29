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
    assert lock.read_text().strip() == str(os.getpid())


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
    assert lock.read_text().strip() == str(os.getpid())


def test_acquire_reclaims_garbage_lock(tmp_path, monkeypatch):
    lock = tmp_path / "idle.lock"
    lock.write_text("not-a-pid")
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: True)
    assert single_instance.acquire(lock) is True


def test_release_removes_lock(tmp_path):
    lock = tmp_path / "idle.lock"
    single_instance.acquire(lock)
    single_instance.release(lock)
    assert not lock.exists()
    # release is idempotent
    single_instance.release(lock)
