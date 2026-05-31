"""Open-and-run launcher for the packaged app.

A double-clicked exe should "just work": if it is not configured yet, run the
setup form; if there is no usable token, run the login flow; then start the
tray. No commands for the user to remember.

When a Tk display is available (the normal case for the windowed exe) the
graphical setup form and login dialog are used — no console, no typed prompts.
On a headless host (or a build without Tk) it falls back to the console wizard,
allocating a console first via ``ensure_console``.

The orchestration is dependency-injected so it can be unit-tested without a
console, a browser, a Tk display, or a real tray.
"""

from __future__ import annotations

from .auth import TOKEN_OK, run_auth_flow, token_health
from .config import load_config
from .gui_setup import gui_available, run_gui_auth, run_gui_setup
from .tray import run_tray
from .wizard import run_setup


def launch(
    *,
    ensure_console=lambda: None,
    load=load_config,
    has_gui=gui_available,
    gui_setup=run_gui_setup,
    console_setup=run_setup,
    gui_auth=run_gui_auth,
    console_auth=run_auth_flow,
    health=token_health,
    tray=run_tray,
    output=print,
) -> int:
    """Set up + authorize as needed, then run the tray. Returns an exit code.

    ``ensure_console`` is called only on the console fallback path (no Tk), so a
    windowed exe with a display never allocates a console.
    """
    # 1. Configured? If load_config fails (missing/invalid config), run setup.
    try:
        config = load()
    except Exception:  # noqa: BLE001 - any config problem means "needs setup"
        if has_gui():
            if gui_setup() != 0:
                return 1
        else:
            ensure_console()
            output("First run — let's set up Spotify Perpetual.")
            if console_setup() != 0:
                output("Setup was cancelled; nothing to run.")
                return 1
        config = load()

    # 2. Usable token? If not, authorize (browser).
    if health(config) != TOKEN_OK:
        if has_gui():
            gui_auth(config)
        else:
            ensure_console()
            output("Authorizing with Spotify (a browser window will open)...")
            console_auth(config, open_browser=True)

    # 3. Everything ready — run the tray.
    return tray()
