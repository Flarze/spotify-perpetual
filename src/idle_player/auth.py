"""Spotify OAuth setup and token cache handling.

Wraps spotipy.SpotifyOAuth with scopes:
    user-read-playback-state user-modify-playback-state

Caches the refresh token to disk (path from config) so browser login is a
one-time step; spotipy refreshes automatically thereafter. The cache file is
a SECRET and must stay gitignored.
"""

from __future__ import annotations

from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from .config import Config

SCOPES = "user-read-playback-state user-modify-playback-state"

# Token health states returned by token_health().
TOKEN_OK = "ok"            # a usable (or refreshable) token is cached
TOKEN_MISSING = "missing"  # no token cached yet — first-time login needed
TOKEN_INVALID = "invalid"  # cached token expired/revoked and cannot refresh


def build_auth_manager(config: Config, open_browser: bool = True) -> SpotifyOAuth:
    """Build the SpotifyOAuth manager (file-backed cache, package scopes)."""
    return SpotifyOAuth(
        client_id=config.client_id,
        client_secret=config.client_secret,
        redirect_uri=config.redirect_uri,
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=config.token_cache_path),
        open_browser=open_browser,
    )


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
    return spotipy.Spotify(auth_manager=build_auth_manager(config, open_browser))


def token_health(config: Config, auth_manager: SpotifyOAuth | None = None) -> str:
    """Classify the cached token before the loop starts.

    Returns one of ``TOKEN_OK``, ``TOKEN_MISSING``, or ``TOKEN_INVALID``.

    Reads the cached token directly (no network) and only reaches out to
    Spotify if the token is expired and must be refreshed — at which point a
    revoked/invalid refresh token surfaces as ``TOKEN_INVALID`` instead of
    blowing up later inside the poll loop.
    """
    if auth_manager is None:
        auth_manager = build_auth_manager(config, open_browser=False)

    token_info = auth_manager.cache_handler.get_cached_token()
    if not token_info:
        return TOKEN_MISSING

    if not auth_manager.is_token_expired(token_info):
        return TOKEN_OK

    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        return TOKEN_INVALID

    try:
        auth_manager.refresh_access_token(refresh_token)
    except SpotifyOauthError:
        return TOKEN_INVALID
    return TOKEN_OK


def run_auth_flow(config: Config, open_browser: bool = True) -> None:
    """Force a fresh interactive login, replacing any cached token.

    Used by ``idle-player auth`` for first-time setup and for re-linking after
    a token is revoked or expires beyond refresh. Removes the existing cache
    first so spotipy runs the full authorization flow instead of trying (and
    failing) to refresh a dead token.

    Set ``open_browser=False`` on headless/WSL hosts: spotipy prints the
    authorize URL and prompts for the redirected URL to paste back.
    """
    cache_path = Path(config.token_cache_path)
    if cache_path.exists():
        cache_path.unlink()

    auth_manager = build_auth_manager(config, open_browser=open_browser)
    # Triggers the browser/paste flow and writes a fresh token to the cache.
    auth_manager.get_access_token(as_dict=False)
