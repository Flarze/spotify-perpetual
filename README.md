# spotify-perpetual

Keep the music going. spotify-perpetual watches your Spotify playback and
resumes a playlist whenever nothing is playing, launching the Spotify app first
if it isn't running. Set it up once and your speakers stay active.

## Features

- **Idle detection:** polls playback on a configurable interval (default 30s).
- **Auto-resume:** starts your chosen playlist as soon as playback stops or no
  device is active.
- **App launch fallback:** if Spotify isn't running, it launches the app, waits
  for it to come online as a Connect device, then starts playback.
- **Set and forget:** runs in the system tray after a one-time login, recovers
  from transient network and API errors, and can start automatically at login.
- **Configurable:** playlists, shuffle, repeat, volume, interval, and how
  pausing is handled are all settings in the setup screen.
- **Hybrid status (Windows):** optionally read playback state from the local OS
  (Windows SMTC) instead of polling the Web API. The Web API is then called only
  to start or resume playback - never to check status - and the tray shows the
  current track within ~1s. See [Status mode](#status-mode-api-vs-hybrid).
- **Resume delay:** an optional grace period before acting on a pause, so a
  deliberate pause isn't undone instantly.

## Before you start

You need three things (all free except Premium):

1. A Spotify Premium account. Remote playback control is Premium-only.
2. The Spotify desktop app, installed on the machine that plays the audio.
3. A free Spotify app for the login keys. This takes about two minutes:
   - Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
     and click Create app.
   - Give it any name. For the Redirect URI, enter exactly
     `http://127.0.0.1:8888/callback`.
   - Save, then open the app's Settings and copy its Client ID and Client
     Secret. You paste these into the setup screen.

The setup screen has an "Open Spotify Developer Dashboard" button and shows the
exact redirect URI to paste, so there is nothing to memorize.

## Install (Windows)

1. Download `SpotifyPerpetualSetup.exe` from the
   [latest release](https://github.com/Flarze/spotify-perpetual/releases).
2. Double-click it and follow the installer. No admin rights are required.
   Leave "Start automatically when I log in" ticked to keep it always on.
3. The app launches when the installer finishes. On the first run, a setup
   window opens: paste your Client ID and Secret, add your playlist links, pick
   your options, and click Save and continue.
4. Click "Log in with Spotify". Your browser opens once to authorize the app,
   which then moves to the system tray and starts playing.

Every later login goes straight to the tray with no prompts. To change settings
later, right-click the tray icon and open the config, or run setup again.

To uninstall, use Settings > Apps or the Start Menu uninstall entry. This
removes the app along with your saved login and config.

## Using it

The tray icon shows status (green for watching, grey for paused) and a menu to
pause or resume, open the logs or config, and quit. The watcher runs in the
background; the icon controls and reports it.

Edits to the config are applied live, with no restart. Open the config from the
tray menu and save; within one poll interval the app reloads the new playlists,
shuffle, repeat, volume, and interval. A broken edit is logged and ignored, and
the previous settings stay in effect.

### Usage statistics

The watcher keeps a running tally of what it does: total watch time, how many
checks it ran, how often it actually started or resumed playback, and a per-day
breakdown of the last week. Run the exe with the `stats` argument (or
`idle-player stats` from source):

```
"Spotify Perpetual.exe" stats
```

The counts live in a small `stats.json` next to the config; delete it to reset
them. Recording is best-effort and never interferes with the watcher itself.

## Troubleshooting

The app ships with a self-check. From the install folder, run the exe with the
`doctor` argument:

```
"Spotify Perpetual.exe" doctor
```

It prints a pass or fail line for your credentials, network, saved login,
account tier, and reachable Connect devices.

The OAuth token grants access to your Spotify account, so treat the install
folder as private. Do not share its `.cache` or `config.yaml`.

## Advanced configuration

The setup screen covers what most people need. To edit files directly, the app
reads a `config.yaml` (and/or `.env`) located next to the exe.

`config.yaml` (copy [`config.example.yaml`](config.example.yaml)):

```yaml
client_id: "..."
client_secret: "..."
redirect_uri: "http://127.0.0.1:8888/callback"

playlists: spotify:playlist:aaaa, spotify:playlist:bbbb
playlist_selection: rotate   # with several: rotate (cycle in order) | random
shuffle: true                # shuffle on each start
repeat: context              # off | context (loop playlist) | track (loop song)
volume: 60                   # 0-100; omit to leave device volume alone
fade_in_seconds: 0           # >0 ramps volume up on start/resume
poll_interval: 30
paused_counts_as_playing: false   # false = pausing also makes the app act
resume_paused_track: false        # resume the same track instead of a fresh playlist
resume_delay_seconds: 0           # wait this long before acting on a pause (0 = instant)

mode: api                         # api (Web API status) | hybrid (local SMTC status)
listener_poll_seconds: 1.0        # hybrid: how often the tray re-reads SMTC
```

Playlists accept either a `spotify:playlist:...` URI or an `open.spotify.com`
link. With several playlists, `rotate` advances to the next one each time
playback resumes, and `random` picks one at random.

The same settings exist as `.env` variables (`SPOTIFY_CLIENT_ID`,
`SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, `PLAYLISTS`, `POLL_INTERVAL`,
`PAUSED_COUNTS_AS_PLAYING`, `RESUME_PAUSED_TRACK`, `RESUME_DELAY_SECONDS`,
`MODE`, `LISTENER_POLL_SECONDS`, `VOLUME`, `FADE_IN_SECONDS`); copy
[`.env.example`](.env.example). When both files exist, `config.yaml` wins.

### Status mode: api vs hybrid

`mode` controls how the app reads "what is Spotify doing right now":

- **`api`** (default) - reads playback with the Spotify Web API, polling
  `current_playback` every `poll_interval`. Works on every platform.
- **`hybrid`** (Windows only) - reads playback from the OS via Windows System
  Media Transport Controls (SMTC), the same local mechanism a desktop overlay
  uses to show the current track. No Web API status polling and no rate-limit
  cost: **the Web API is called only at the moment playback is started or
  resumed**, never to check status. While music is playing it makes zero API
  calls. The tray also reflects the current track within ~1s
  (`listener_poll_seconds`), instead of once per `poll_interval`.

Hybrid still uses the Web API (and Premium) for *control* - starting and
resuming playback - so credentials and login are unchanged. It needs the SMTC
binding, installed via the `smtc` extra:

```bash
pip install -e ".[tray,smtc]"
```

If SMTC is unavailable (non-Windows, or the binding is missing), `hybrid`
falls back to the Web API automatically. `idle-player doctor` reports whether
SMTC is available when `mode: hybrid`.

`resume_delay_seconds` adds a grace period before acting on a pause: the app
waits, then re-checks, and if you have resumed or switched track in the
meantime it leaves playback alone instead of restarting it. Applies in both
modes.

## Run from source / other platforms

The app also runs as a standard Python package on Windows, macOS, and Linux.

```bash
git clone https://github.com/Flarze/spotify-perpetual.git
cd spotify-perpetual
pip install -e ".[tray]"     # installs the `idle-player` command + tray extra
```

```bash
idle-player setup            # interactive console wizard (writes config.yaml)
idle-player auth             # one-time browser login (--no-browser for headless/WSL)
idle-player tray             # run with the tray icon
idle-player                  # run headless (no icon)
idle-player doctor           # diagnostics
idle-player stats            # usage statistics
```

Start at login without the installer:

```bash
idle-player install          # headless watcher   (--tray for the tray UI)
idle-player status           # is it installed?
idle-player uninstall        # remove it
```

This creates the right entry per platform: a Startup-folder shortcut on Windows
(no admin), a launchd agent on macOS, or a systemd user service on Linux. Run
`idle-player auth` once first so autostart can run without a browser prompt.
Per-OS manual templates live in [`scripts/`](scripts/).

### Build the installer

```powershell
.\packaging\build_windows.ps1
```

This produces the app folder `dist\Spotify Perpetual\` (a one-dir PyInstaller
build, which avoids the antivirus false positives that one-file exes trigger).
If [Inno Setup](https://jrsoftware.org/isdl.php) is installed, it also produces
`dist\SpotifyPerpetualSetup.exe`, the single installer you distribute to users.

## License

[MIT](LICENSE).
