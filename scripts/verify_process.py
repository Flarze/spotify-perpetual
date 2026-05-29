"""Verify Spotify process detect + launch (Step 4) on the real OS.

Run on Windows/macOS/Linux where Spotify is installed:

    python scripts/verify_process.py

Prints whether Spotify is running, then ensures it is (launching if needed and
waiting a few seconds), then prints the state again.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from idle_player.spotify_process import ensure_running, is_running


def main() -> None:
    print(f"is_running (before): {is_running()}")
    already = ensure_running(wait_seconds=8)
    print(f"was already running: {already}")
    print(f"is_running (after):  {is_running()}")


if __name__ == "__main__":
    main()
