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
        acquire=lambda path: True,
        release=lambda path: None,
        lock_path="ignored",
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


def _health_then_ok(states):
    """A health() that yields each state in turn (INVALID before auth, OK after)."""
    it = iter(states)

    def health(_config):
        return next(it)

    return health


def test_launch_runs_gui_auth_when_token_not_ok():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(
            calls,
            has_gui=True,
            health=_health_then_ok([TOKEN_INVALID, TOKEN_OK]),
        ),
    )
    assert rc == 0
    assert calls == ["gui_auth", "tray"]


def test_launch_falls_back_to_console_auth_without_gui():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(
            calls,
            has_gui=False,
            health=_health_then_ok([TOKEN_INVALID, TOKEN_OK]),
        ),
    )
    assert rc == 0
    assert calls == ["console", ("console_auth", True), "tray"]


def test_launch_aborts_when_gui_auth_does_not_connect():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        gui_error=lambda *a: calls.append("gui_error"),
        **_kwargs(calls, has_gui=True, health=lambda c: TOKEN_INVALID),
    )
    assert rc == 1
    assert calls == ["gui_auth", "gui_error"]  # never starts the tray


def test_launch_aborts_when_console_auth_does_not_connect():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(calls, has_gui=False, health=lambda c: TOKEN_INVALID),
    )
    assert rc == 1
    assert calls == ["console", ("console_auth", True)]  # never starts the tray


def test_launch_exits_when_already_running():
    calls = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(calls, has_gui=True, acquire=lambda path: False),
    )
    assert rc == 0  # exit cleanly, not an error
    assert calls == []  # never sets up, auths, or starts a second tray


def test_launch_releases_lock_after_tray():
    calls = []
    released = []
    rc = bootstrap.launch(
        load=lambda: "CONFIG",
        **_kwargs(
            calls,
            has_gui=True,
            release=lambda path: released.append(path),
        ),
    )
    assert rc == 0
    assert calls == ["tray"]
    assert released == ["ignored"]  # lock released even though run succeeded
