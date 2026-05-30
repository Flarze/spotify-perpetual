"""Tests that main() wires config -> client -> loop in order."""

from idle_player import __main__ as entry
from idle_player.auth import TOKEN_INVALID, TOKEN_MISSING, TOKEN_OK


def test_main_wires_config_client_and_run(monkeypatch):
    calls = {}
    fake_config = object()
    fake_client = object()

    def fake_load_config():
        calls["load"] = True
        return fake_config

    def fake_build_client(config):
        calls["build"] = config
        return fake_client

    def fake_run(config, sp):
        calls["run"] = (config, sp)

    monkeypatch.setattr(entry, "load_config", fake_load_config)
    monkeypatch.setattr(entry, "build_client", fake_build_client)
    monkeypatch.setattr(entry, "run", fake_run)
    monkeypatch.setattr(entry, "token_health", lambda c: TOKEN_OK)
    monkeypatch.setattr(entry, "setup_logging", lambda c: None)
    monkeypatch.setattr(entry, "wait_for_network", lambda c, logger: True)
    monkeypatch.setattr(entry.single_instance, "acquire", lambda path: True)
    monkeypatch.setattr(entry.single_instance, "release", lambda path: None)

    entry.main([])

    assert calls["load"] is True
    assert calls["build"] is fake_config
    assert calls["run"] == (fake_config, fake_client)


def test_main_aborts_loop_when_token_unhealthy(monkeypatch, capsys):
    for state, expect in ((TOKEN_MISSING, "authorize"), (TOKEN_INVALID, "re-link")):
        calls = {"build": False, "run": False}
        monkeypatch.setattr(entry, "load_config", lambda: object())
        monkeypatch.setattr(entry, "setup_logging", lambda c: None)
        monkeypatch.setattr(entry, "wait_for_network", lambda c, logger: True)
        monkeypatch.setattr(entry, "token_health", lambda c, s=state: s)
        monkeypatch.setattr(entry, "build_client", lambda c: calls.__setitem__("build", True))
        monkeypatch.setattr(entry, "run", lambda c, sp: calls.__setitem__("run", True))
        released = {"v": False}
        monkeypatch.setattr(entry.single_instance, "acquire", lambda path: True)
        monkeypatch.setattr(entry.single_instance, "release", lambda path: released.__setitem__("v", True))

        entry.main([])

        out = capsys.readouterr().out
        assert "idle-player auth" in out and expect in out
        assert calls["build"] is False  # never auths or loops
        assert calls["run"] is False
        assert released["v"] is True  # lock still released


def test_main_auth_subcommand_runs_flow(monkeypatch, capsys):
    calls = {}
    fake_config = type("C", (), {"token_cache_path": ".cache"})()
    monkeypatch.setattr(entry, "load_config", lambda: fake_config)
    monkeypatch.setattr(entry, "run_auth_flow", lambda c, open_browser: calls.update(cfg=c, browser=open_browser))

    entry.main(["auth"])
    assert calls == {"cfg": fake_config, "browser": True}

    entry.main(["auth", "--no-browser"])
    assert calls["browser"] is False
    assert "Token cached at .cache" in capsys.readouterr().out


def test_main_exits_if_another_instance_running(monkeypatch):
    calls = {"run": False}
    monkeypatch.setattr(entry, "load_config", lambda: object())
    monkeypatch.setattr(entry, "build_client", lambda c: (_ for _ in ()).throw(AssertionError("should not auth")))
    monkeypatch.setattr(entry, "run", lambda c, sp: calls.__setitem__("run", True))
    monkeypatch.setattr(entry.single_instance, "acquire", lambda path: False)

    entry.main([])  # should return without running

    assert calls["run"] is False


def test_main_dispatches_subcommands(monkeypatch):
    calls = []
    monkeypatch.setattr(entry.autostart, "install", lambda: calls.append("install"))
    monkeypatch.setattr(entry.autostart, "uninstall", lambda: calls.append("uninstall"))
    monkeypatch.setattr(entry.autostart, "status", lambda: calls.append("status"))

    entry.main(["install"])
    entry.main(["uninstall"])
    entry.main(["status"])

    assert calls == ["install", "uninstall", "status"]


def test_main_dispatches_doctor(monkeypatch):
    called = {"v": False}
    monkeypatch.setattr(entry, "run_doctor", lambda: called.__setitem__("v", True))

    entry.main(["doctor"])

    assert called["v"] is True
