"""Cross-platform autostart install/uninstall/status.

`idle-player install` creates an OS autostart entry so the polling loop runs at
login without manual Task Scheduler / launchd / systemd setup. Paths are
captured at install time (current interpreter + cwd), so run `install` from the
repo root in the target venv.

Pure builders (text generation) are separated from the side-effecting
subprocess calls so the former can be unit-tested without shelling out.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import load_config

TASK_NAME = "spotify-perpetual"
MACOS_LABEL = "com.spotify-perpetual.idle"


# --- pure builders --------------------------------------------------------


def _pythonw(python_exe: str) -> str:
    """On Windows, prefer the sibling pythonw.exe (no console window)."""
    path = Path(python_exe)
    if path.name.lower() == "python.exe":
        candidate = path.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return python_exe


def _windows_vbs(python_exe: str, workdir: str) -> str:
    """A startup .vbs that launches idle_player hidden, with the repo as cwd.

    Run mode 0 = no window; False = don't wait. Setting CurrentDirectory means
    `.env` and `logs\\` resolve against the repo root.
    """
    return (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{workdir}"\r\n'
        f'sh.Run """{python_exe}"" -m idle_player", 0, False\r\n'
    )


def _windows_startup_dir() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def _macos_plist(python_exe: str, workdir: str, label: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{label}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{python_exe}</string>\n"
        "        <string>-m</string>\n"
        "        <string>idle_player</string>\n"
        "    </array>\n"
        "    <key>WorkingDirectory</key>\n"
        f"    <string>{workdir}</string>\n"
        "    <key>EnvironmentVariables</key>\n"
        "    <dict>\n"
        "        <key>PYTHONPATH</key>\n"
        f"        <string>{workdir}/src</string>\n"
        "    </dict>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _linux_unit(python_exe: str, workdir: str) -> str:
    return (
        "[Unit]\n"
        "Description=spotify-perpetual: keep Spotify playing when idle\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={workdir}\n"
        f"Environment=PYTHONPATH={workdir}/src\n"
        f"ExecStart={python_exe} -m idle_player\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


# --- helpers --------------------------------------------------------------


def _warn_if_no_token() -> None:
    """Remind the user to auth once if no token cache exists yet."""
    try:
        cache = Path(load_config().token_cache_path)
    except Exception:
        return
    if not cache.exists():
        print(
            "Warning: no token cache found. Run `idle-player` once to complete "
            "the one-time browser login before relying on autostart."
        )


def _run(cmd) -> None:
    subprocess.run(cmd, check=True)


# --- install / uninstall / status ----------------------------------------


def install() -> None:
    workdir = str(Path.cwd())
    python_exe = _pythonw(sys.executable)
    platform = sys.platform

    if platform == "win32":
        vbs_path = _windows_startup_dir() / f"{TASK_NAME}.vbs"
        vbs_path.parent.mkdir(parents=True, exist_ok=True)
        vbs_path.write_text(_windows_vbs(python_exe, workdir), encoding="ascii")
        print(f"Installed startup entry at {vbs_path}.")
    elif platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_macos_plist(python_exe, workdir, MACOS_LABEL))
        _run(["launchctl", "load", str(plist_path)])
        print(f"Installed LaunchAgent at {plist_path}.")
    elif platform.startswith("linux"):
        unit_path = Path.home() / ".config" / "systemd" / "user" / f"{TASK_NAME}.service"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(_linux_unit(python_exe, workdir))
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", f"{TASK_NAME}.service"])
        print(f"Installed and started systemd user service at {unit_path}.")
    else:
        raise SystemExit(f"Unsupported platform for autostart: {platform}")

    _warn_if_no_token()


def uninstall() -> None:
    platform = sys.platform

    if platform == "win32":
        vbs_path = _windows_startup_dir() / f"{TASK_NAME}.vbs"
        vbs_path.unlink(missing_ok=True)
        print("Removed startup entry.")
    elif platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            plist_path.unlink()
        print("Removed LaunchAgent.")
    elif platform.startswith("linux"):
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{TASK_NAME}.service"],
            check=False,
        )
        unit_path = Path.home() / ".config" / "systemd" / "user" / f"{TASK_NAME}.service"
        unit_path.unlink(missing_ok=True)
        print("Removed systemd user service.")
    else:
        raise SystemExit(f"Unsupported platform for autostart: {platform}")


def status() -> None:
    platform = sys.platform

    if platform == "win32":
        vbs_path = _windows_startup_dir() / f"{TASK_NAME}.vbs"
        print("installed" if vbs_path.exists() else "not installed")
    elif platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"
        print("installed" if plist_path.exists() else "not installed")
    elif platform.startswith("linux"):
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", f"{TASK_NAME}.service"],
            capture_output=True, text=True,
        )
        print("installed" if result.returncode == 0 else "not installed")
    else:
        raise SystemExit(f"Unsupported platform for autostart: {platform}")
