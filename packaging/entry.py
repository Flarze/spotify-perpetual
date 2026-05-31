"""PyInstaller entry point for the branded ``Spotify Perpetual.exe``.

The exe is built windowed (no console window) so it can sit in the tray without
a black box. Therefore:

* No arguments (double-click / autostart) -> launch the tray UI.
* Interactive subcommands (setup, auth, doctor, ...) need a console for their
  prompts and output, so one is allocated on demand on Windows.
"""

import sys

# Subcommands that print to / read from a console.
_CONSOLE_COMMANDS = {"setup", "auth", "doctor", "status", "install", "uninstall"}


def _ensure_std_streams() -> None:
    """Give the windowed process non-None stdout/stderr/stdin.

    A windowed (``console=False``) exe starts with all three set to ``None``.
    Any stray ``print`` — or tkinter writing a traceback — then raises and kills
    the process silently. Point them at the null device so that never happens;
    the GUI path needs no real console.
    """
    import os

    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r")


def _ensure_console() -> None:
    """Attach a console to the windowed process so prompts/output are visible."""
    if sys.platform != "win32":
        return
    if sys.stdout is not None:  # console build already has one
        return
    import ctypes

    if ctypes.windll.kernel32.AllocConsole():
        sys.stdout = open("CONOUT$", "w", buffering=1)
        sys.stderr = open("CONOUT$", "w", buffering=1)
        sys.stdin = open("CONIN$", "r")


def main() -> None:
    raw = sys.argv[1:]
    if not raw:
        # Double-click / autostart: open-and-run (setup + auth if needed, then
        # tray). No real console here — the GUI handles prompts — but the
        # windowed process must still have safe std streams so a stray write
        # (or tkinter traceback) can't kill it silently.
        _ensure_std_streams()
        from idle_player.bootstrap import launch

        raise SystemExit(launch(ensure_console=_ensure_console))

    if raw[0] in _CONSOLE_COMMANDS:
        _ensure_console()
    from idle_player.__main__ import main as run_main

    run_main(raw)


if __name__ == "__main__":
    main()
