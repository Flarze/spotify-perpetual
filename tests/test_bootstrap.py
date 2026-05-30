"""Tests for the open-and-run launch flow (setup -> auth -> tray)."""

from idle_player import bootstrap
from idle_player.auth import TOKEN_INVALID, TOKEN_OK


def _spy():
    calls = []
    return calls


def test_launch_runs_tray_when_already_configured():
    calls = []
    rc = bootstrap.launch(
        ensure_console=lambda: calls.append("console"),
        load=lambda: "CONFIG",
        setup=lambda: calls.append("setup") or 0,
        auth=lambda c, open_browser: calls.append("auth"),
        health=lambda c: TOKEN_OK,
        tray=lambda: calls.append("tray") or 0,
        output=lambda *a: None,
    )
    assert rc == 0
    assert calls == ["tray"]  # no setup, no auth, no console


def test_launch_runs_setup_when_unconfigured():
    loaded = iter([RuntimeError("missing"), "CONFIG"])

    def load():
        v = next(loaded)
        if isinstance(v, Exception):
            raise v
        return v

    calls = []
    rc = bootstrap.launch(
        ensure_console=lambda: calls.append("console"),
        load=load,
        setup=lambda: calls.append("setup") or 0,
        auth=lambda c, open_browser: calls.append("auth"),
        health=lambda c: TOKEN_OK,
        tray=lambda: calls.append("tray") or 0,
        output=lambda *a: None,
    )
    assert rc == 0
    assert calls == ["console", "setup", "tray"]  # setup ran, then tray


def test_launch_aborts_if_setup_cancelled():
    calls = []
    rc = bootstrap.launch(
        ensure_console=lambda: None,
        load=lambda: (_ for _ in ()).throw(ValueError("no config")),
        setup=lambda: 1,  # user aborted the overwrite / wizard
        auth=lambda c, open_browser: calls.append("auth"),
        health=lambda c: TOKEN_OK,
        tray=lambda: calls.append("tray") or 0,
        output=lambda *a: None,
    )
    assert rc == 1
    assert calls == []  # never auths or starts the tray


def test_launch_runs_auth_when_token_not_ok():
    calls = []
    rc = bootstrap.launch(
        ensure_console=lambda: calls.append("console"),
        load=lambda: "CONFIG",
        setup=lambda: calls.append("setup") or 0,
        auth=lambda c, open_browser: calls.append(("auth", open_browser)),
        health=lambda c: TOKEN_INVALID,
        tray=lambda: calls.append("tray") or 0,
        output=lambda *a: None,
    )
    assert rc == 0
    assert calls == ["console", ("auth", True), "tray"]  # auth then tray
