"""Manual smoke test for spotify-perpetual features.

Run on the machine that actually plays audio (the Windows host), where Spotify
is installed and the OAuth token is already cached:

    .\\.venv\\Scripts\\python.exe scripts\\smoketest.py          # dry run, no playback
    .\\.venv\\Scripts\\python.exe scripts\\smoketest.py --play   # actually start playback

Dry run (default) checks config, account, devices, and previews playlist
rotation without touching playback. With ``--play`` it starts the first
playlist with your configured shuffle/repeat, then reads playback back and
reports whether shuffle_state / repeat_state match what you asked for.
"""

import argparse
import sys
import time
from pathlib import Path

# Allow running straight from the repo without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from idle_player.auth import build_client  # noqa: E402
from idle_player.config import load_config  # noqa: E402
from idle_player.player import (  # noqa: E402
    PlaylistRotator,
    get_playback,
    pick_device,
    start_playlist,
)
from idle_player.spotify_process import ensure_running  # noqa: E402


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="spotify-perpetual feature smoke test")
    ap.add_argument(
        "--play",
        action="store_true",
        help="actually start playback to verify shuffle/repeat take effect",
    )
    args = ap.parse_args()

    config = load_config()
    playlists = config.playlists()

    print("=== Config ===")
    print(f"  selection : {config.playlist_selection}")
    print(f"  shuffle   : {config.shuffle}")
    print(f"  repeat    : {config.repeat}")
    print(f"  playlists : {len(playlists)}")
    for uri in playlists:
        print(f"    - {uri}")

    # Rotation preview is pure logic — safe to show without any playback.
    print("\n=== Playlist rotation preview ===")
    rotator = PlaylistRotator(playlists, config.playlist_selection)
    preview = [rotator.next() for _ in range(max(4, len(playlists) * 2))]
    for i, uri in enumerate(preview, 1):
        print(f"  start #{i}: {uri}")

    print("\n=== Spotify connection ===")
    sp = build_client(config, open_browser=False)
    me = sp.me() or {}
    _check("authenticated", bool(me.get("id")), f"user={me.get('id')} product={me.get('product')}")
    devices = (sp.devices() or {}).get("devices", [])
    names = [d.get("name") for d in devices]
    _check("a Connect device is available", bool(devices), f"devices={names or 'NONE — open Spotify'}")

    if not args.play:
        print("\nDry run complete. Re-run with --play to test shuffle/repeat on a real device.")
        return 0

    print("\n=== Live playback (shuffle/repeat) ===")
    ensure_running(config.launch_wait_seconds)
    device_id = pick_device(sp, config.preferred_device_name)
    if not device_id:
        print("No usable device. Open the Spotify desktop app and re-run.")
        return 1

    uri = playlists[0]
    print(f"Starting {uri} (shuffle={config.shuffle}, repeat={config.repeat}) on {device_id} ...")
    started = start_playlist(
        sp, uri, device_id, shuffle=config.shuffle, repeat=config.repeat
    )
    if not _check("start_playlist returned True", started):
        return 1

    time.sleep(2)  # let Spotify apply the state
    pb = get_playback(sp) or {}
    track = (pb.get("item") or {}).get("name")
    print(f"Now playing: {track}")
    ok = True
    ok &= _check(
        "shuffle_state matches config",
        pb.get("shuffle_state") == config.shuffle,
        f"got={pb.get('shuffle_state')} want={config.shuffle}",
    )
    ok &= _check(
        "repeat_state matches config",
        pb.get("repeat_state") == config.repeat,
        f"got={pb.get('repeat_state')} want={config.repeat}",
    )
    print("\nRESULT:", "PASS" if ok else "CHECK — states differ (Spotify can lag; re-run to confirm)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
