"""Tests for the tray entry point that do not need a display.

The pystray UI itself cannot run headless, so we only verify the graceful
missing-dependency path. Setting sys.modules['pystray'] to None makes
``import pystray`` raise ImportError deterministically, regardless of whether
pystray is actually installed.
"""

import sys

from idle_player import tray


def test_open_log_opens_file_when_present(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "app.log"
    log.parent.mkdir()
    log.write_text("hi")
    opened = []
    monkeypatch.setattr(tray, "_open_path", lambda p: opened.append(str(p)) or True)

    tray._open_log(str(log))

    assert opened == [str(log)]  # opened the file, no fallback


def test_open_log_falls_back_to_folder_when_open_fails(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "app.log"
    log.parent.mkdir()
    log.write_text("hi")
    opened = []

    def fake_open(p):
        opened.append(str(p))
        return False  # simulate "no app associated with .log"

    monkeypatch.setattr(tray, "_open_path", fake_open)
    tray._open_log(str(log))

    assert opened == [str(log), str(log.parent)]  # tried file, then folder


def test_open_log_opens_folder_when_file_missing(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "app.log"
    log.parent.mkdir()  # folder exists, file does not
    opened = []
    monkeypatch.setattr(tray, "_open_path", lambda p: opened.append(str(p)) or True)

    tray._open_log(str(log))

    assert opened == [str(log.parent)]  # straight to the folder


def test_run_tray_reports_missing_dependency(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pystray", None)

    rc = tray.run_tray()

    out = capsys.readouterr().out
    assert rc == 1
    assert "pip install" in out
    assert ".[tray]" in out
