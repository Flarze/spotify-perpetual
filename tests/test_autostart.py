"""Tests for the pure autostart builders.

The functions that generate the .bat / plist / systemd-unit text and the
Windows pythonw swap are pure and tested here. The actual schtasks / launchctl
/ systemctl invocations are thin glue verified manually per OS.
"""

from idle_player import autostart


def test_windows_shortcut_script_sets_target_args_and_workdir():
    script = autostart._windows_shortcut_script(
        r"C:\startup\Spotify Perpetual.lnk",
        r"C:\repo\.venv\Scripts\pythonw.exe",
        r"C:\repo",
        "-m idle_player",
    )
    assert r"C:\startup\Spotify Perpetual.lnk" in script
    assert r"C:\repo\.venv\Scripts\pythonw.exe" in script  # TargetPath
    assert "$s.Arguments = '-m idle_player'" in script
    assert r"C:\repo" in script  # WorkingDirectory
    assert "CreateShortcut" in script


def test_windows_shortcut_script_targets_exe_with_no_args():
    script = autostart._windows_shortcut_script(
        r"C:\startup\Spotify Perpetual.lnk",
        r"C:\app\Spotify Perpetual.exe",
        r"C:\app",
        "",
    )
    assert r"C:\app\Spotify Perpetual.exe" in script  # TargetPath = the exe
    assert "$s.Arguments = ''" in script  # no args -> open-and-run -> tray


def test_launch_plan_source_mode(monkeypatch):
    monkeypatch.setattr(autostart.sys, "frozen", False, raising=False)
    assert autostart._launch_plan(False)["arguments"] == "-m idle_player"
    assert autostart._launch_plan(True)["arguments"] == "-m idle_player tray"


def test_launch_plan_frozen_targets_exe(monkeypatch, tmp_path):
    exe = tmp_path / "Spotify Perpetual.exe"
    exe.write_text("")
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(exe))

    plan = autostart._launch_plan(tray=True)  # tray flag irrelevant when frozen

    assert plan["target"] == str(exe)
    assert plan["arguments"] == ""  # exe with no args = open-and-run
    assert plan["workdir"] == str(tmp_path)


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


def test_module_args_tray_vs_plain():
    assert autostart._module_args(False) == "-m idle_player"
    assert autostart._module_args(True) == "-m idle_player tray"


def test_windows_shortcut_passes_tray_arguments_through():
    tray = autostart._windows_shortcut_script(r"C:\x.lnk", r"C:\py.exe", r"C:\repo", "-m idle_player tray")
    assert "$s.Arguments = '-m idle_player tray'" in tray


def test_linux_unit_tray_execstart():
    unit = autostart._linux_unit("/repo/.venv/bin/python", "/repo", tray=True)
    assert "ExecStart=/repo/.venv/bin/python -m idle_player tray" in unit


def test_macos_plist_tray_adds_arg():
    plain = autostart._macos_plist("/py", "/repo", "lbl")
    tray = autostart._macos_plist("/py", "/repo", "lbl", tray=True)
    assert "<string>tray</string>" not in plain
    assert "<string>tray</string>" in tray


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
