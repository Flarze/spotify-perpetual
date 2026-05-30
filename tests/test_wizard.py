"""Tests for the `idle-player setup` wizard.

run_setup takes injectable input/secret/output callables, so the whole
interactive flow runs without a TTY. The written config.yaml is then parsed and
loaded to confirm it is valid.
"""

import yaml

from idle_player.config import load_config
from idle_player.wizard import run_setup


class Script:
    """Feed canned answers to the prompt callable in order."""

    def __init__(self, answers):
        self._it = iter(answers)

    def __call__(self, prompt=""):
        return next(self._it)


def _run(tmp_path, answers, secret="topsecret"):
    out = []
    path = tmp_path / "config.yaml"
    rc = run_setup(
        config_path=str(path),
        input_fn=Script(answers),
        secret_fn=lambda prompt="": secret,
        output=out.append,
    )
    return rc, path, "\n".join(out)


def test_setup_writes_valid_multi_playlist_config(tmp_path):
    answers = [
        "cid",                                          # client id
        "",                                             # redirect uri -> default
        "https://open.spotify.com/playlist/aaa",        # playlist #1
        "spotify:playlist:bbb",                         # playlist #2
        "",                                             # finish playlists
        "random",                                       # selection (>1 playlist)
        "y",                                            # shuffle
        "context",                                      # repeat
        "70",                                           # volume
        "",                                             # fade-in -> default 0
        "y",                                            # auto-resume on pause
        "n",                                            # resume same track?
        "45",                                           # poll interval
    ]
    rc, path, out = _run(tmp_path, answers)

    assert rc == 0
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    assert data["client_id"] == "cid"
    assert data["client_secret"] == "topsecret"
    assert data["redirect_uri"] == "http://127.0.0.1:8888/callback"
    assert data["playlists"] == "spotify:playlist:aaa, spotify:playlist:bbb"
    assert data["playlist_selection"] == "random"
    assert data["shuffle"] is True
    assert data["repeat"] == "context"
    assert data["volume"] == 70
    assert data["fade_in_seconds"] == 0
    assert data["poll_interval"] == 45
    assert data["paused_counts_as_playing"] is False  # auto-resume => false
    assert data["resume_paused_track"] is False
    assert "Config is valid." in out

    # And it actually loads.
    config = load_config(env_path=tmp_path / ".env", yaml_path=path)
    assert config.playlists() == ["spotify:playlist:aaa", "spotify:playlist:bbb"]
    assert config.playlist_selection == "random"
    assert config.shuffle is True
    assert config.repeat == "context"
    assert config.paused_counts_as_playing is False


def test_setup_single_playlist_skips_selection_prompt(tmp_path):
    # Only one playlist -> the selection question is not asked, so no answer for it.
    answers = [
        "cid",                          # client id
        "http://127.0.0.1:9999/cb",     # redirect uri (custom)
        "spotify:playlist:solo",        # playlist #1
        "",                             # finish playlists
        "",                             # shuffle -> default False
        "",                             # repeat -> default off
        "",                             # volume -> blank (unset)
        "",                             # fade-in -> default 0
        "n",                            # auto-resume on pause -> False
        "",                             # poll interval -> default 30
    ]
    rc, path, out = _run(tmp_path, answers)

    assert rc == 0
    data = yaml.safe_load(path.read_text())
    assert data["playlists"] == "spotify:playlist:solo"
    assert data["playlist_selection"] == "rotate"
    assert data["shuffle"] is False
    assert data["repeat"] == "off"
    assert "volume" not in data  # blank volume -> key left out (commented)
    assert data["fade_in_seconds"] == 0
    assert data["poll_interval"] == 30
    assert data["paused_counts_as_playing"] is True   # declined auto-resume
    assert data["resume_paused_track"] is False


def test_setup_requires_nonempty_secret(tmp_path):
    # Secret is empty first, then provided; wizard must re-ask, not accept blank.
    answers = ["cid", "", "spotify:playlist:a", "", "", "", "", "", "n", ""]
    out = []
    rc = run_setup(
        config_path=str(tmp_path / "config.yaml"),
        input_fn=Script(answers),
        secret_fn=Script(["", "realsecret"]),
        output=out.append,
    )
    assert rc == 0
    data = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert data["client_secret"] == "realsecret"


def test_setup_bool_reasks_on_garbage(tmp_path):
    # "maybe" is not yes/no -> re-ask; then "y" -> True.
    answers = ["cid", "", "spotify:playlist:a", "", "maybe", "y", "", "", "", "n", ""]
    out = []
    rc = run_setup(
        config_path=str(tmp_path / "config.yaml"),
        input_fn=Script(answers),
        secret_fn=lambda prompt="": "s",
        output=out.append,
    )
    assert rc == 0
    data = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert data["shuffle"] is True


def test_setup_blank_applies_all_defaults(tmp_path):
    # One playlist given; every optional answer left blank -> documented defaults.
    # Order: id, redirect, playlist, finish, shuffle, repeat, volume, fade,
    # auto-resume, resume-track (asked because auto-resume defaults yes), poll.
    answers = ["cid", "", "spotify:playlist:a", "", "", "", "", "", "", "", ""]
    out = []
    rc = run_setup(
        config_path=str(tmp_path / "config.yaml"),
        input_fn=Script(answers),
        secret_fn=lambda prompt="": "s",
        output=out.append,
    )
    assert rc == 0
    data = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert data["redirect_uri"] == "http://127.0.0.1:8888/callback"
    assert data["shuffle"] is False
    assert data["repeat"] == "off"
    assert data["poll_interval"] == 30
    assert data["paused_counts_as_playing"] is False  # auto-resume default yes
    assert data["resume_paused_track"] is False


def test_setup_aborts_without_overwrite(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("playlists: spotify:playlist:keep\n")

    rc, _, out = _run(tmp_path, ["n"])  # decline overwrite

    assert rc == 1
    assert "Aborted" in out
    assert "keep" in path.read_text()  # untouched
