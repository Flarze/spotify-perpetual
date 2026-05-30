"""Tests for the `idle-player doctor` diagnostics report.

run_doctor takes its dependencies (config loader, network probe, client
builder, token health) as injectable callables, so every check path is
exercised without touching the network or Spotify.
"""

from idle_player.auth import TOKEN_INVALID, TOKEN_MISSING, TOKEN_OK
from idle_player.config import Config
from idle_player.doctor import run_doctor


def make_config(**overrides):
    base = dict(
        client_id="cid",
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        playlist_uri="spotify:playlist:abc",
    )
    base.update(overrides)
    return Config(**base)


class FakeSpotify:
    def __init__(self, product="premium", devices=None):
        self._product = product
        self._devices = devices if devices is not None else [{"name": "Laptop"}]

    def me(self):
        return {"product": self._product}

    def devices(self):
        return {"devices": self._devices}


def _deps(config=None, net=True, health=TOKEN_OK, sp=None):
    """Build a kwargs dict of injected dependencies with healthy defaults."""
    return dict(
        load=lambda: config or make_config(),
        probe=lambda *a: net,
        health=lambda c: health,
        build=lambda c: sp or FakeSpotify(),
    )


def test_all_green_passes(capsys):
    ok = run_doctor(**_deps())
    out = capsys.readouterr().out
    assert ok is True
    assert "[PASS] Credentials" in out
    assert "[PASS] Network" in out
    assert "[PASS] Token" in out
    assert "[PASS] Account" in out
    assert "[PASS] Devices" in out
    assert "Laptop" in out


def test_bad_credentials_fails_fast(capsys):
    def boom():
        raise ValueError("Missing required config: set SPOTIFY_CLIENT_ID")

    ok = run_doctor(**{**_deps(), "load": boom})
    out = capsys.readouterr().out
    assert ok is False
    assert "[FAIL] Credentials" in out
    # Downstream checks skipped — no client built.
    assert "Network" not in out


def test_network_unreachable_fails(capsys):
    ok = run_doctor(**_deps(net=False))
    out = capsys.readouterr().out
    assert ok is False
    assert "[FAIL] Network" in out
    # Devices/account skipped when offline.
    assert "skipped" in out


def test_missing_token_fails_with_guidance(capsys):
    ok = run_doctor(**_deps(health=TOKEN_MISSING))
    out = capsys.readouterr().out
    assert ok is False
    assert "[FAIL] Token" in out
    assert "idle-player auth" in out


def test_invalid_token_fails(capsys):
    ok = run_doctor(**_deps(health=TOKEN_INVALID))
    assert ok is False
    assert "[FAIL] Token" in capsys.readouterr().out


def test_free_account_warns_but_passes(capsys):
    ok = run_doctor(**_deps(sp=FakeSpotify(product="free")))
    out = capsys.readouterr().out
    assert ok is True  # WARN does not fail the report
    assert "[WARN] Account" in out
    assert "needs Premium" in out


def test_unknown_tier_warns_but_passes(capsys):
    # me().product is None without the user-read-private scope (the common case).
    ok = run_doctor(**_deps(sp=FakeSpotify(product=None)))
    out = capsys.readouterr().out
    assert ok is True
    assert "[WARN] Account" in out
    assert "unreadable" in out


def test_no_devices_warns_but_passes(capsys):
    ok = run_doctor(**_deps(sp=FakeSpotify(devices=[])))
    out = capsys.readouterr().out
    assert ok is True
    assert "[WARN] Devices" in out


def test_spotify_query_error_fails(capsys):
    class Boom:
        def me(self):
            raise RuntimeError("boom")

    ok = run_doctor(**_deps(sp=Boom()))
    out = capsys.readouterr().out
    assert ok is False
    assert "[FAIL] Spotify" in out
