"""Open-and-run launcher for the packaged app.

A double-clicked exe should "just work": if it is not configured yet, run the
setup wizard; if there is no usable token, run the auth flow; then start the
tray. No commands for the user to remember.

The orchestration here is dependency-injected so it can be unit-tested without
a console, a browser, or a real tray.
"""

from __future__ import annotations

from .auth import TOKEN_OK, run_auth_flow, token_health
from .config import load_config
from .tray import run_tray
from .wizard import run_setup


def launch(
    *,
    ensure_console=lambda: None,
    load=load_config,
    setup=run_setup,
    auth=run_auth_flow,
    health=token_health,
    tray=run_tray,
    output=print,
) -> int:
    """Set up + authorize as needed, then run the tray. Returns an exit code.

    ``ensure_console`` is called right before any interactive step (the wizard
    or the auth flow), so a windowed exe can allocate a console only when
    prompts actually need to be shown.
    """
    # 1. Configured? If load_config fails (missing/invalid config), run setup.
    try:
        config = load()
    except Exception:  # noqa: BLE001 - any config problem means "needs setup"
        ensure_console()
        output("First run — let's set up Spotify Perpetual.")
        if setup() != 0:
            output("Setup was cancelled; nothing to run.")
            return 1
        config = load()

    # 2. Usable token? If not, authorize (browser).
    if health(config) != TOKEN_OK:
        ensure_console()
        output("Authorizing with Spotify (a browser window will open)...")
        auth(config, open_browser=True)

    # 3. Everything ready — run the tray.
    return tray()
