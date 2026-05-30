"""Tests for the PyInstaller entry shim (packaging/entry.py).

The full exe build is Windows-only and verified manually; here we just load the
module from its path (packaging/ is not an installed package) and check the
console-command set that drives whether a console is allocated.
"""

import importlib.util
from pathlib import Path

_ENTRY = Path(__file__).resolve().parent.parent / "packaging" / "entry.py"
_spec = importlib.util.spec_from_file_location("entry", _ENTRY)
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def test_setup_and_auth_are_console_commands():
    assert "setup" in entry._CONSOLE_COMMANDS
    assert "auth" in entry._CONSOLE_COMMANDS
    assert "tray" not in entry._CONSOLE_COMMANDS  # tray stays windowed
