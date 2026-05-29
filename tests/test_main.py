"""Tests that main() wires config -> client -> loop in order."""

from idle_player import __main__ as entry


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
    monkeypatch.setattr(entry.single_instance, "acquire", lambda path: True)
    monkeypatch.setattr(entry.single_instance, "release", lambda path: None)

    entry.main([])

    assert calls["load"] is True
    assert calls["build"] is fake_config
    assert calls["run"] == (fake_config, fake_client)


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
