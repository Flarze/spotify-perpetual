"""Tests for the pure autostart builders.

The functions that generate the .bat / plist / systemd-unit text and the
Windows pythonw swap are pure and tested here. The actual schtasks / launchctl
/ systemctl invocations are thin glue verified manually per OS.
"""

from idle_player import autostart


def test_windows_vbs_sets_workdir_and_runs_module_hidden():
    vbs = autostart._windows_vbs(r"C:\repo\.venv\Scripts\pythonw.exe", r"C:\repo")
    assert 'sh.CurrentDirectory = "C:\\repo"' in vbs
    assert r"C:\repo\.venv\Scripts\pythonw.exe" in vbs
    assert "-m idle_player" in vbs
    assert ", 0, False" in vbs  # hidden window, non-blocking


def test_macos_plist_has_paths_trigger_and_module():
    plist = autostart._macos_plist(
        "/repo/.venv/bin/python", "/repo", "com.spotify-perpetual.idle"
    )
    assert "com.spotify-perpetual.idle" in plist
    assert "/repo/.venv/bin/python" in plist
    assert "<string>/repo</string>" in plist  # WorkingDirectory
    assert "<key>RunAtLoad</key>" in plist
    assert "idle_player" in plist


def test_linux_unit_has_execstart_workdir_and_target():
    unit = autostart._linux_unit("/repo/.venv/bin/python", "/repo")
    assert "ExecStart=/repo/.venv/bin/python -m idle_player" in unit
    assert "WorkingDirectory=/repo" in unit
    assert "WantedBy=default.target" in unit


def test_pythonw_swaps_when_sibling_exists(tmp_path):
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    result = autostart._pythonw(str(tmp_path / "python.exe"))
    assert result == str(tmp_path / "pythonw.exe")


def test_pythonw_keeps_original_when_no_sibling(tmp_path):
    (tmp_path / "python.exe").write_text("")
    result = autostart._pythonw(str(tmp_path / "python.exe"))
    assert result == str(tmp_path / "python.exe")


def test_pythonw_passthrough_for_non_windows_name():
    assert autostart._pythonw("/usr/bin/python3") == "/usr/bin/python3"
