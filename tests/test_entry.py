"""Tests for the PyInstaller entry shim (packaging/entry.py).

The full exe build is Windows-only and verified manually; here we just check
the pure argv-resolution rule (no args -> tray) by loading the module from its
path, since packaging/ is not an installed package.
"""

import importlib.util
from pathlib import Path

_ENTRY = Path(__file__).resolve().parent.parent / "packaging" / "entry.py"
_spec = importlib.util.spec_from_file_location("entry", _ENTRY)
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def test_resolve_argv_defaults_to_tray():
    assert entry.resolve_argv([]) == ["tray"]


def test_resolve_argv_passes_subcommands_through():
    assert entry.resolve_argv(["setup"]) == ["setup"]
    assert entry.resolve_argv(["auth", "--no-browser"]) == ["auth", "--no-browser"]


def test_setup_and_auth_are_console_commands():
    assert "setup" in entry._CONSOLE_COMMANDS
    assert "auth" in entry._CONSOLE_COMMANDS
    assert "tray" not in entry._CONSOLE_COMMANDS  # tray stays windowed
