"""``idle-player setup`` — interactive first-run configuration.

Prompts for credentials, playlists, and playback options, then writes a
``config.yaml`` (the single standalone config store) so a new user never has to
hand-edit YAML. The written file holds the client secret, so it is treated as a
secret (already gitignored). After writing it validates the result and points
the user at ``idle-player auth``.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from .config import _normalize_playlist_uri, load_config

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def _prompt(input_fn, label: str, default: str = None) -> str:
    """Prompt until a non-empty value is given, or return the default."""
    suffix = f" [{default}]" if default else ""
    while True:
        value = input_fn(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  (required)")


def _prompt_bool(input_fn, label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input_fn(f"{label} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes", "true", "1", "on")


def _prompt_choice(input_fn, label: str, choices, default: str) -> str:
    options = "/".join(choices)
    while True:
        value = input_fn(f"{label} ({options}) [{default}]: ").strip().lower()
        if not value:
            return default
        if value in choices:
            return value
        print(f"  choose one of: {options}")


def _prompt_int(input_fn, label: str, default: int) -> int:
    while True:
        value = input_fn(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print("  enter a whole number")


def _prompt_playlists(input_fn) -> list:
    """Collect one or more playlists (URL or URI), normalized to URIs."""
    print("Playlists to keep alive (paste a Spotify link or URI). Blank line to finish.")
    playlists: list = []
    while True:
        nth = len(playlists) + 1
        tail = " (blank to finish)" if playlists else ""
        raw = input_fn(f"  playlist #{nth}{tail}: ").strip()
        if not raw:
            if playlists:
                return playlists
            print("  at least one playlist is required")
            continue
        playlists.append(_normalize_playlist_uri(raw))


def _render_config(values: dict) -> str:
    """Render config.yaml text from collected values (commented, human-readable)."""
    playlists_line = ", ".join(values["playlists"])
    return f"""\
# Written by `idle-player setup`. This file holds your client secret -- it is a
# SECRET and is gitignored. Re-run `idle-player setup` to change these.

client_id: "{values['client_id']}"
client_secret: "{values['client_secret']}"
redirect_uri: "{values['redirect_uri']}"

# One playlist, or several separated by commas.
playlists: "{playlists_line}"
playlist_selection: {values['playlist_selection']}   # rotate | random
shuffle: {str(values['shuffle']).lower()}
repeat: "{values['repeat']}"                # off | context | track

poll_interval: {values['poll_interval']}

# false = pausing also makes the app act (resume / restart).
paused_counts_as_playing: {str(values['paused_counts_as_playing']).lower()}
# Resume the same paused track instead of starting a fresh playlist.
resume_paused_track: {str(values['resume_paused_track']).lower()}
"""


def run_setup(
    config_path: str = "config.yaml",
    input_fn=input,
    secret_fn=getpass.getpass,
    output=print,
) -> int:
    """Run the interactive wizard, write config_path, and validate it.

    Returns 0 on success, 1 if the user aborted at the overwrite prompt.
    """
    path = Path(config_path)
    if path.exists() and not _prompt_bool(
        input_fn, f"{config_path} already exists. Overwrite?", False
    ):
        output("Aborted; existing config left unchanged.")
        return 1

    output("\n== Spotify app credentials (https://developer.spotify.com/dashboard) ==")
    client_id = _prompt(input_fn, "Client ID")
    client_secret = secret_fn("Client secret: ").strip()
    redirect_uri = _prompt(input_fn, "Redirect URI", DEFAULT_REDIRECT_URI)

    output("\n== Playlists ==")
    playlists = _prompt_playlists(input_fn)

    output("\n== Playback options ==")
    selection = (
        _prompt_choice(input_fn, "Selection with several playlists", ("rotate", "random"), "rotate")
        if len(playlists) > 1
        else "rotate"
    )
    shuffle = _prompt_bool(input_fn, "Shuffle on start?", False)
    repeat = _prompt_choice(input_fn, "Repeat", ("off", "context", "track"), "off")
    resume_on_pause = _prompt_bool(input_fn, "Auto-resume when you pause playback?", True)
    resume_track = (
        _prompt_bool(input_fn, "  Resume the same track (not a new playlist)?", False)
        if resume_on_pause
        else False
    )
    poll_interval = _prompt_int(input_fn, "Poll interval (seconds)", 30)

    values = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "playlists": playlists,
        "playlist_selection": selection,
        "shuffle": shuffle,
        "repeat": repeat,
        "poll_interval": poll_interval,
        "paused_counts_as_playing": not resume_on_pause,
        "resume_paused_track": resume_track,
    }
    path.write_text(_render_config(values))
    output(f"\nWrote {config_path} ({len(playlists)} playlist(s)).")

    # Validate by loading it back (env beside the written file, so a stray .env
    # elsewhere does not interfere).
    try:
        load_config(env_path=path.parent / ".env", yaml_path=path)
        output("Config is valid.")
    except Exception as exc:  # noqa: BLE001 - surface the problem, do not crash
        output(f"Warning: config did not validate: {exc}")

    output("Next: run `idle-player auth` to authorize Spotify (one-time browser login).")
    return 0
