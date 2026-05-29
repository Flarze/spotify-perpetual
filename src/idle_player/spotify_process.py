"""Cross-platform Spotify process detection and launch.

Detection uses psutil to avoid OS-specific output parsing. Launch branches per
OS and relies on the OS to resolve Spotify's location (don't assume install
path):
    Windows : start spotify  (or the spotify: URI)
    macOS   : open -a Spotify
    Linux   : spotify URI / spotify command

After launching, wait a few seconds for Spotify to register as a Connect
device before retrying playback. A "no active device" 404 is the trigger for
this launch fallback, not a crash.
"""
