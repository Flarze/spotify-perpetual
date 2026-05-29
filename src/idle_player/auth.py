"""Spotify OAuth setup and token cache handling.

Wraps spotipy.SpotifyOAuth with scopes:
    user-read-playback-state user-modify-playback-state

Caches the refresh token to disk (path from config) so browser login is a
one-time step; spotipy refreshes automatically thereafter. The cache file is
a SECRET and must stay gitignored.
"""

from __future__ import annotations

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

from .config import Config

SCOPES = "user-read-playback-state user-modify-playback-state"


def build_client(config: Config, open_browser: bool = True) -> spotipy.Spotify:
    """Build an authenticated spotipy client.

    Uses SpotifyOAuth with a file-backed token cache at
    ``config.token_cache_path``. The first call (when a token is actually
    requested) opens a browser once; later runs reuse the cache and refresh
    automatically. Constructing the client itself performs no network I/O.

    Set ``open_browser=False`` for headless/WSL environments: spotipy then
    prints the authorize URL and prompts for the redirected URL instead of
    trying to launch a browser.
    """
    auth_manager = SpotifyOAuth(
        client_id=config.client_id,
        client_secret=config.client_secret,
        redirect_uri=config.redirect_uri,
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=config.token_cache_path),
        open_browser=open_browser,
    )
    return spotipy.Spotify(auth_manager=auth_manager)
