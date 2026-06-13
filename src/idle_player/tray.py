"""System-tray icon for the watcher (pystray + Pillow).

Runs the polling loop on a background thread and shows a tray icon with the
current status and a menu to pause/resume the watcher, open the logs or config,
and quit. pystray works on Windows, macOS, and Linux.

pystray and Pillow are optional extras; install with ``pip install -e .[tray]``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from .auth import (
    TOKEN_INVALID,
    TOKEN_MISSING,
    build_client,
    token_health,
)
from .config import app_dir, load_config
from .control import Controller
from .loop import run, setup_logging, wait_for_network
from .stats import StatsRecorder, format_stats, format_summary
from .status import SmtcListener

APP_NAME = "Spotify Perpetual"


def _open_path(path) -> bool:
    """Open a file or folder with the OS default handler. Return success.

    The path is resolved to an absolute one first (the tray's working directory
    is not guaranteed to match where the relative log/config paths point).
    """
    target = str(Path(path).expanduser().resolve())
    try:
        if sys.platform == "win32":
            os.startfile(target)  # noqa: S606 - intended shell open
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except OSError:
        return False


def _open_log(log_file) -> None:
    """Open the log file; fall back to its folder if it can't be opened.

    A missing file, or a ``.log`` extension with no associated app on Windows,
    would otherwise do nothing - opening the containing folder always works.
    """
    log = Path(log_file)
    if not log.exists() or not _open_path(log):
        _open_path(log.parent if str(log.parent) else ".")


def _make_image(running: bool):
    """A simple round status icon: green when watching, grey when paused."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), (24, 24, 24))
    draw = ImageDraw.Draw(img)
    color = (30, 215, 96) if running else (140, 140, 140)
    draw.ellipse((10, 10, 54, 54), fill=color)
    return img


def run_tray() -> int:
    """Start the watcher under a tray icon. Returns a process exit code."""
    try:
        import pystray
    except ImportError:
        print(
            "The tray needs extra packages. Install them with:\n"
            "    pip install -e .[tray]\n"
            "(or: pip install pystray Pillow)"
        )
        return 1

    config = load_config()
    logger = setup_logging(config)

    # Same pre-flight as the plain run path: wait for network, check the token.
    wait_for_network(config, logger)
    health = token_health(config)
    if health == TOKEN_MISSING:
        print("No saved Spotify login found. Run `idle-player auth` to authorize.")
        return 1
    if health == TOKEN_INVALID:
        print("Saved Spotify login expired or was revoked. Run `idle-player auth`.")
        return 1

    sp = build_client(config)
    controller = Controller()
    recorder = StatsRecorder()
    worker = threading.Thread(
        target=run, args=(config, sp, controller, recorder), daemon=True
    )
    worker.start()

    icon = pystray.Icon("idle_player", _make_image(running=True), APP_NAME)

    def _refresh() -> None:
        icon.icon = _make_image(running=not controller.paused)
        icon.update_menu()

    # Instant track/status display via SMTC (Windows): the polling loop only
    # refreshes status once per poll_interval; this updates the tray the moment
    # the track or play/pause state changes. No-op when SMTC is unavailable.
    listener = SmtcListener(poll_seconds=config.listener_poll_seconds)

    def _on_smtc_change(label: str) -> None:
        controller.set_track(label)
        try:
            # Tray menus only redraw when opened; the title is the live hover
            # tooltip, so update both for an instant-visible refresh.
            icon.title = f"{APP_NAME} - {label}"
            icon.update_menu()
        except Exception:  # noqa: BLE001 - a display refresh must never crash
            pass

    listener.start(_on_smtc_change)

    def on_toggle(_icon, _item) -> None:
        controller.toggle_pause()
        _refresh()

    def on_logs(_icon, _item) -> None:
        _open_log(config.log_file)

    def on_config(_icon, _item) -> None:
        cfg = app_dir() / "config.yaml"
        _open_path(cfg if cfg.exists() else cfg.parent)

    def _summary_line(index: int) -> str:
        """The index-th summary line from a fresh snapshot, re-read each time
        the menu opens so the numbers stay live."""
        lines = format_summary(recorder.snapshot())
        return lines[index] if index < len(lines) else ""

    def on_full_report(_icon, _item) -> None:
        # Write the full report (totals + 7-day history) and open it so the
        # user gets everything the `stats` CLI prints, in their text viewer.
        report = app_dir() / "stats-report.txt"
        try:
            report.write_text(format_stats(recorder.snapshot()), encoding="utf-8")
        except OSError:
            _open_path(app_dir())
            return
        _open_path(report)

    def on_quit(_icon, _item) -> None:
        controller.stop()
        _icon.stop()

    # One disabled line per summary metric; default-arg binds the index so each
    # lambda reports its own line when the submenu is rendered.
    summary_items = [
        pystray.MenuItem(lambda _i, idx=k: _summary_line(idx), None, enabled=False)
        for k in range(len(format_summary(recorder.snapshot())))
    ]

    icon.menu = pystray.Menu(
        # Live track from SMTC when available, else the watcher status.
        pystray.MenuItem(lambda _i: controller.track() or controller.status(), None, enabled=False),
        # Live numbers in a submenu, plus a full report opened in a text viewer.
        pystray.MenuItem(
            "Statistics",
            pystray.Menu(
                *summary_items,
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open full report", on_full_report),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda _i: "Resume watching" if controller.paused else "Pause watching",
            on_toggle,
        ),
        pystray.MenuItem("Open logs", on_logs),
        pystray.MenuItem("Open config", on_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon.run()  # blocks until on_quit stops it

    listener.stop()
    controller.stop()
    worker.join(timeout=5)
    return 0
