"""One-time auth verification (Step 3).

Run:  python scripts/verify_auth.py

First run opens (or prints) the Spotify authorize URL. Log in, then you are
redirected to http://localhost:8888/callback?code=...  — if no browser opens
(e.g. WSL/headless), copy that full redirected URL from the address bar and
paste it back when prompted. A token cache file is then written; later runs
print playback with no prompt.
"""

import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from idle_player.auth import build_client
from idle_player.config import load_config


def main() -> None:
    config = load_config(env_path=".env")
    # open_browser=False: print the URL and prompt for the redirected URL,
    # which works in headless/WSL terminals where launching a browser fails.
    sp = build_client(config, open_browser=False)
    playback = sp.current_playback()
    if playback is None:
        print("Auth OK. current_playback() -> None (nothing playing / no device).")
    else:
        print(f"Auth OK. is_playing={playback.get('is_playing')}")


if __name__ == "__main__":
    main()
