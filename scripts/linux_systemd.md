# Linux autostart — systemd user unit

Run idle_player as a per-user service that starts at login.

> Prerequisite: run `python -m idle_player` manually once to complete the
> one-time browser OAuth and cache the token. Headless boxes: do this auth
> step on a machine with a browser, then copy the token cache over.

## Unit template

Save as `~/.config/systemd/user/spotify-perpetual.service`.
Replace `%h` paths if your checkout lives elsewhere.

```ini
[Unit]
Description=spotify-perpetual — keep Spotify playing when idle
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/spotify-perpetual/src
Environment=PYTHONPATH=%h/spotify-perpetual/src
ExecStart=/usr/bin/python3 -m idle_player
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

## Enable / start

```sh
systemctl --user daemon-reload
systemctl --user enable --now spotify-perpetual.service
journalctl --user -u spotify-perpetual -f   # follow logs
```

To keep it running after logout (headless), enable lingering:

```sh
loginctl enable-linger "$USER"
```
