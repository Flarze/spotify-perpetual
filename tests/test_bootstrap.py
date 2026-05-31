"""Tests for the open-and-run launch flow (setup -> auth -> tray).

Covers both the GUI path (Tk available) and the console fallback (no Tk).
"""

from idle_player import bootstrap
from idle_player.auth import TOKEN_INVALID, TOKEN_OK


def _kwargs(calls, *, has_gui, **overrides):
    """Default injected callables that just record which step ran."""
    base = dict(
        ensure_console=lambda: calls.append("console"),
        has_gui=lambda: has_gui,
        gui_setup=lambda: calls.append("gui_setup") or 0,
        console_setup=lambda: calls.append("console_setup") or 0,
        gui_auth=lambda c: calls.append("gui_auth"),
        console_auth=lambda c, open_browser: calls.append(("console_auth", open_browser)),
        health=lambda c: TOKEN_OK,
        tray=lambda: calls.append("tray") or 0,
        output=lambda *a: None,
    )
    base.update(overrides)
    return base


def test_launch_runs_tray_when_already_configured():
    calls = []
    rc = bootstrap.launch(load=lambda: "CONFIG", **_kwargs(calls, has_gui=True))
    assert rc == 0
    assert calls == ["tray"]  # no setup, no auth, no console


def test_launch_runs_gui_setup_when_unconfigured():
    loaded = iter([RuntimeError("missing"), "CONFIG"])

    def load():
        v = next(loaded)
        if isinstance(v, Exception):
            raise v
        return v

    calls = []
    rc = bootstrap.launch(load=load, **_kwargs(calls, has_gui=True))
    assert rc == 0
    assert calls == ["gui_setup", "tray"]  # GUI setup, no console allocated


def test_launch_falls_back_to_console_setup_without_gui():
    loaded = iter([RuntimeError("missing"), "CONFIG"])

    def load():
        v = next(loaded)
        if isinstance(v, Exception):
            raise v
        return v

    calls = []
    rc = bootstrap.launch(load=load, **_kwargs(calls, has_gui=False))
    assert rc == 0
    assert calls == ["console", "console_setup", "tray"]


def test_launch_aborts_if_gui_setup_cancelled():
    calls = []
    rc = bootstrap.launch(
        load=lambda: (_ for _ in ()).throw(ValueError("no config")),
        **_kwargs(calls, has_gui=True, gui_setup=lambda: 1),  # user closed the form
    )
    assert rc == 1
    assert calls == []  # never auths or starts the tray


def test_launch_runs_gui_auth_when_token_not_ok():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(calls, has_gui=True, health=lambda c: TOKEN_INVALID),
    )
    assert rc == 0
    assert calls == ["gui_auth", "tray"]


def test_launch_falls_back_to_console_auth_without_gui():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(calls, has_gui=False, health=lambda c: TOKEN_INVALID),
    )
    assert rc == 0
    assert calls == ["console", ("console_auth", True), "tray"]
