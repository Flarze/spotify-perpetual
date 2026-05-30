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
- A Spotify **Premium** account — remote playback control is Premium-only. On a
  free account the app detects the 403 and exits with a clear message.
- A free [Spotify developer app](https://developer.spotify.com/dashboard)
  (for the client ID/secret)
- The Spotify desktop app installed on the machine that plays audio

## Installation

```bash
git clone https://github.com/Flarze/spotify-perpetual.git
cd spotify-perpetual
pip install -e .
```

This installs the dependencies and the `idle-player` command. (Use a
virtualenv if you prefer to keep things isolated.)

## Configuration

1. Create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard)
   and add a redirect URI (e.g. `http://127.0.0.1:8888/callback`).

### Quick setup (recommended)

Run the wizard — it asks for your credentials, playlists, and options, then
writes `config.yaml` for you (no hand-editing):

```bash
idle-player setup
idle-player auth     # one-time browser login
idle-player          # start it
```

### Manual setup

Prefer to edit files yourself? Copy the template and fill in your values:

   ```bash
   cp .env.example .env
   ```

   | Setting | Description |
   |---------|-------------|
   | `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | From your developer app |
   | `SPOTIFY_REDIRECT_URI` | Must match the dashboard exactly |
   | `PLAYLISTS` | Playlist(s) to resume — one, or several separated by commas, e.g. `spotify:playlist:aaaa,spotify:playlist:bbbb` |
   | `POLL_INTERVAL` | Seconds between checks (default `30`) |
   | `PAUSED_COUNTS_AS_PLAYING` | If `true`, a paused track is treated as "listening" and won't trigger a restart |
   | `RESUME_PAUSED_TRACK` | If `true` (and `PAUSED_COUNTS_AS_PLAYING=false`), resume the paused track instead of starting a fresh playlist. Default `false` |

### Multiple playlists, shuffle, and repeat

`PLAYLISTS` takes one playlist or several, comma-separated. For shuffle and
repeat as well, use `config.yaml` (copy `config.example.yaml`); it is
auto-loaded from next to your `.env`:

```yaml
playlists: spotify:playlist:aaaa, spotify:playlist:bbbb
playlist_selection: rotate   # with several: rotate (cycle in order) | random
shuffle: true                # shuffle on each start
repeat: context              # off | context (loop playlist) | track (loop song)
```

URIs or `open.spotify.com` links both work. With several playlists, `rotate`
advances to the next one each time playback resumes; `random` picks one each
time.

### Changing settings while it runs

Edits are picked up live — no restart. Save your `.env` or `config.yaml` and
within one `poll_interval` the daemon reloads and applies the new playback
settings (playlists, selection, shuffle, repeat, interval), logging
`config reloaded ...`. A broken edit is logged and the previous config is kept,
so the daemon stays up. Changing credentials triggers a Spotify client rebuild
automatically.

## Usage

The first run opens a browser once to authorize your account:

```bash
idle-player          # or: python -m idle_player
```

After that, the access token is cached and every later run is headless, with no
browser needed. Leave it running and it keeps your playlist alive.

You can also authorize explicitly (useful for first-time setup or to re-link a
revoked account) without starting the loop:

```bash
idle-player auth               # opens a browser to authorize
idle-player auth --no-browser  # headless/WSL: prints a URL to paste back
```

On startup the app checks the saved login first. If it is missing, expired, or
revoked, it prints a clear `Run idle-player auth ...` message and exits instead
of silently failing on every poll.

## Troubleshooting

Run the built-in diagnostics to check everything at once:

```bash
idle-player doctor
```

It reports a pass/fail line for your credentials, network reachability, saved
token, account tier, and reachable Connect devices — handy when autostart is
not doing anything and you need to know why.

## Running at startup

From the repo root, in the same environment where you installed the package,
run the built-in installer:

```bash
idle-player install      # create the autostart entry for your OS
idle-player status       # check whether it is installed
idle-player uninstall    # remove it
```

This creates the right entry for your platform automatically: a Startup-folder
launcher on Windows (no admin needed), a launchd agent on macOS, or a systemd
user service on Linux.
Run `idle-player` once first to complete the browser login so autostart can run
headless.

Prefer to set it up by hand? Per-OS templates and step-by-step instructions
live in [`scripts/`](scripts/):

- **Windows:** [Task Scheduler](scripts/windows_task_scheduler.md)
- **macOS:** [launchd agent](scripts/macos_launchd.md)
- **Linux:** [systemd user service](scripts/linux_systemd.md)

## Security

The OAuth token cache grants access to your Spotify account, so **treat it as a
secret.** It and your `.env` are excluded by `.gitignore` and should never be
committed or shared.

## License

[MIT](LICENSE).
