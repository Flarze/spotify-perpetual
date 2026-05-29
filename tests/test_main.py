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

    entry.main()

    assert calls["load"] is True
    assert calls["build"] is fake_config
    assert calls["run"] == (fake_config, fake_client)
