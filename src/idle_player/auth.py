"""Spotify OAuth setup and token cache handling.

Wraps spotipy.SpotifyOAuth with scopes:
    user-read-playback-state user-modify-playback-state

Caches the refresh token to disk (path from config) so browser login is a
one-time step; spotipy refreshes automatically thereafter. The cache file is
a SECRET and must stay gitignored.
"""
