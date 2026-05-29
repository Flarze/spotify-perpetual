# spotify-perpetual

Never let the music stop. **spotify-perpetual** watches your Spotify playback
and automatically resumes a playlist whenever nothing is playing, launching
the Spotify app first if it isn't running. Set it up once, add it to startup,
and your speakers are never silent again.

## Features

- **Idle detection:** polls playback on a configurable interval (default ~30s).
- **Auto-resume:** starts your chosen playlist the moment playback stops or no
  device is active.
- **App launch fallback:** if Spotify isn't running, launches it, waits for it
  to come online as a Connect device, then starts playback.
- **Cross-platform:** Windows, macOS, and Linux process detection and launch.
- **Set-and-forget:** runs headless after a one-time login, resilient to
  transient network/API errors.
- **Configurable:** playlist, interval, and whether a paused track counts as
  "still listening" are all settings, not hardcoded.

## Requirements

- Python 3.9+
- A Spotify account and a free [Spotify developer app](https://developer.spotify.com/dashboard)
  (for the client ID/secret)
- The Spotify desktop app installed on the machine that plays audio

## Installation

```bash
git clone https://github.com/Flarze/spotify-perpetual.git
cd spotify-perpetual
pip install -r requirements.txt
```

## Configuration

1. Create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard)
   and add a redirect URI (e.g. `http://127.0.0.1:8888/callback`).
2. Copy the template and fill in your values:

   ```bash
   cp .env.example .env
   ```

   | Setting | Description |
   |---------|-------------|
   | `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | From your developer app |
   | `SPOTIFY_REDIRECT_URI` | Must match the dashboard exactly |
   | `PLAYLIST_URI` | Playlist to resume, e.g. `spotify:playlist:...` |
   | `POLL_INTERVAL` | Seconds between checks (default `30`) |
   | `PAUSED_COUNTS_AS_PLAYING` | If `true`, a paused track is treated as "listening" and won't trigger a restart |

## Usage

The first run opens a browser once to authorize your account:

```bash
python -m idle_player
```

After that, the access token is cached and every later run is headless, with no
browser needed. Leave it running and it keeps your playlist alive.

## Running at startup

Autostart is configured per operating system. Step-by-step guides and templates
live in [`scripts/`](scripts/):

- **Windows:** [Task Scheduler](scripts/windows_task_scheduler.md) ("At log on", via `pythonw`)
- **macOS:** [launchd agent](scripts/macos_launchd.md)
- **Linux:** [systemd user service](scripts/linux_systemd.md)

## Security

The OAuth token cache grants access to your Spotify account, so **treat it as a
secret.** It and your `.env` are excluded by `.gitignore` and should never be
committed or shared.

## License

[MIT](LICENSE).
