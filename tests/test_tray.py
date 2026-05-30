"""Tests for the tray entry point that do not need a display.

The pystray UI itself cannot run headless, so we only verify the graceful
missing-dependency path. Setting sys.modules['pystray'] to None makes
``import pystray`` raise ImportError deterministically, regardless of whether
pystray is actually installed.
"""

import sys

from idle_player import tray


def test_run_tray_reports_missing_dependency(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pystray", None)

    rc = tray.run_tray()

    out = capsys.readouterr().out
    assert rc == 1
    assert "pip install" in out
    assert ".[tray]" in out
