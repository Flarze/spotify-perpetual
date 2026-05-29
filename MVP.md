MVP scope and repo structure, no code.
Functionality (MVP)
Core behavior

Poll current_playback() on an interval (configurable, default ~30s).
If nothing is playing OR no active device: ensure Spotify is running, then start the configured playlist.
If something is already playing: do nothing.

Auth

OAuth2 via SpotifyOAuth (spotipy) with scopes user-read-playback-state user-modify-playback-state.
Cache the refresh token to disk so it's a one-time browser login. spotipy handles refresh automatically.
Credentials (client ID/secret, redirect URI, playlist URI, poll interval) come from a .env or config file — never hardcoded, since this is public.

Spotify-launch fallback

Detect if the Spotify process is running (cross-platform process check).
If not, launch it via OS-appropriate command, wait a few seconds for it to register as a Connect device, then retry playback.
Handle the "no active device" 404 gracefully — that's the trigger for the launch fallback, not a crash.

Cross-platform

Process detection and launch must branch per OS (Windows/macOS/Linux). Use psutil for detection to avoid OS-specific parsing.
Don't assume Spotify's install path; rely on the OS to resolve it (spotify URI / start spotify / open -a Spotify).

Resilience

Wrap the loop so transient API/network errors log and continue rather than kill the process.
Basic logging to a file (rotating) so autostart/headless runs are debuggable.

spotify-perpetual/
├── README.md
├── LICENSE                  # pick one (MIT is the obvious default for this)
├── .gitignore               # must exclude .env, token cache, __pycache__, logs
├── .env.example             # template with empty CLIENT_ID etc., committed
├── requirements.txt         # spotipy, python-dotenv, psutil
├── pyproject.toml           # optional but better than requirements-only for an OSS project
├── config.example.yaml      # optional: poll interval, playlist URI, device preferences
├── src/
│   └── idle_player/
│       ├── __init__.py
│       ├── __main__.py      # entry point: python -m idle_player
│       ├── config.py        # load/validate env + config
│       ├── auth.py          # SpotifyOAuth setup, token cache handling
│       ├── player.py        # playback state checks + start logic
│       ├── spotify_process.py  # cross-platform detect + launch
│       └── loop.py          # the polling loop, error handling, logging
├── scripts/
│   ├── windows_task_scheduler.md   # setup instructions + .xml or .bat template
│   ├── macos_launchd.md            # plist template
│   └── linux_systemd.md            # user service unit template
└── tests/
    └── test_player.py       # mock spotipy responses; test the decision logic

Notes for whoever builds it

- Autostart is per-OS, not one script. Windows = Task Scheduler "At log on" running pythonw -m idle_player. macOS = launchd plist. Linux = systemd user unit. Provide all three under scripts/ rather than pretending one works everywhere. You said Task Scheduler specifically — that's the Windows path; include the others since it's meant to be portable.
- First run can't be headless — OAuth needs a browser once. Document that the user runs it manually once to authorize, then autostart uses the cached token.
- The token cache is a secret. It must be in .gitignore. Make this loud in the README; people leak these.
- Decision logic belongs in its own function (separate from the API calls) so it's unit-testable without hitting Spotify. That's the one piece worth testing; everything else is I/O.
- The "is anything playing" check has an edge case: paused-but-has-track vs. truly idle. Decide explicitly whether a paused session counts as "listening" — your call, but make it a config flag rather than a buried assumption.