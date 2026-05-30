"""Tests for the cross-thread Controller (pause/stop/status flags)."""

from idle_player.control import Controller


def test_controller_starts_running_and_not_paused():
    c = Controller()
    assert c.stopped is False
    assert c.paused is False
    assert c.status() == "starting"


def test_controller_pause_resume_toggle():
    c = Controller()
    c.pause()
    assert c.paused is True
    c.resume()
    assert c.paused is False
    c.toggle_pause()
    assert c.paused is True
    c.toggle_pause()
    assert c.paused is False


def test_controller_stop_is_sticky():
    c = Controller()
    c.stop()
    assert c.stopped is True
    assert c.stop_event.is_set() is True


def test_controller_status_roundtrip():
    c = Controller()
    c.set_status("watching")
    assert c.status() == "watching"
