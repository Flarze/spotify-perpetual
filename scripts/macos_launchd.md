# macOS autostart — launchd

Run idle_player at login via a per-user LaunchAgent.

> Prerequisite: run `python -m idle_player` manually once to complete the
> one-time browser OAuth and cache the token.

## Plist template

Save as `~/Library/LaunchAgents/com.spotify-perpetual.idle.plist`.
Replace paths with absolute ones (launchd does not expand `~` inside args).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.spotify-perpetual.idle</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>idle_player</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/YOU/spotify-perpetual/src</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/YOU/spotify-perpetual/src</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/YOU/spotify-perpetual/logs/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOU/spotify-perpetual/logs/launchd.err.log</string>
</dict>
</plist>
```

## Load / unload

```sh
launchctl load  ~/Library/LaunchAgents/com.spotify-perpetual.idle.plist
launchctl unload ~/Library/LaunchAgents/com.spotify-perpetual.idle.plist
```
