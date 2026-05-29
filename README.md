# spotify-perpetual

Keeps Spotify playing. Polls playback state on an interval; if nothing is
playing (or no active Connect device exists), launches Spotify if needed and
starts a configured playlist.

## Status

MVP scaffold. See [MVP.md](MVP.md) for scope.

## How it works

- Poll `current_playback()` every `POLL_INTERVAL` seconds (default ~30s).
- Something playing → do nothing.
- Nothing playing / no active device → ensure Spotify running, then start the
  configured playlist.

## Setup

1. Create a Spotify app at https://developer.spotify.com/dashboard and note the
   client ID, client secret, and a redirect URI.
2. Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**
3. Install deps:
   ```
   pip install -r requirements.txt
   ```
4. **First run is not headless** — OAuth opens a browser once to authorize.
   Run it manually the first time:
   ```
   python -m idle_player
   ```
   After that the refresh token is cached and runs can be headless/autostarted.

## ⚠️ Secrets

The OAuth **token cache file is a secret** — it grants access to your account.
It is excluded by `.gitignore`. Do not commit it. People leak these constantly.

## Autostart

Autostart is per-OS. See `scripts/`:

- Windows → Task Scheduler ("At log on", running `pythonw -m idle_player`)
- macOS → launchd plist
- Linux → systemd user unit

## License

MIT — see [LICENSE](LICENSE).
