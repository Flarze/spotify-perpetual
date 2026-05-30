"""Entry point: ``python -m idle_player``.

With no arguments, wires together config load, auth, and the polling loop, then
runs it. Subcommands manage OS autostart:

    idle-player            run the polling loop (default)
    idle-player auth       (re-)authorize Spotify and cache the token
    idle-player install    create an OS autostart entry
    idle-player uninstall  remove it
    idle-player status     report whether it is installed
"""

import argparse
from typing import Optional, Sequence

from . import autostart, single_instance
from .auth import (
    TOKEN_INVALID,
    TOKEN_MISSING,
    build_client,
    run_auth_flow,
    token_health,
)
from .config import load_config
from .loop import run


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Parse arguments and dispatch to the loop or an autostart subcommand."""
    parser = argparse.ArgumentParser(prog="idle-player")
    sub = parser.add_subparsers(dest="command")
    auth_p = sub.add_parser("auth", help="(re-)authorize Spotify and cache the token")
    auth_p.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authorize URL and prompt for the redirect (headless/WSL)",
    )
    sub.add_parser("install", help="create an OS autostart entry")
    sub.add_parser("uninstall", help="remove the OS autostart entry")
    sub.add_parser("status", help="report whether autostart is installed")
    args = parser.parse_args(argv)

    if args.command == "auth":
        config = load_config()
        run_auth_flow(config, open_browser=not args.no_browser)
        print(f"Authorized. Token cached at {config.token_cache_path}.")
    elif args.command == "install":
        autostart.install()
    elif args.command == "uninstall":
        autostart.uninstall()
    elif args.command == "status":
        autostart.status()
    else:
        lock_path = single_instance.default_lock_path()
        if not single_instance.acquire(lock_path):
            print("idle_player is already running; exiting.")
            return
        try:
            config = load_config()
            if not _check_token(config):
                return
            sp = build_client(config)
            run(config, sp)
        finally:
            single_instance.release(lock_path)


def _check_token(config) -> bool:
    """Verify the cached token before looping. Return False (with guidance) if
    the user must (re-)authorize, so the caller can exit instead of failing
    silently poll after poll."""
    health = token_health(config)
    if health == TOKEN_MISSING:
        print("No saved Spotify login found. Run `idle-player auth` to authorize.")
        return False
    if health == TOKEN_INVALID:
        print(
            "Saved Spotify login has expired or was revoked. "
            "Run `idle-player auth` to re-link your account."
        )
        return False
    return True


if __name__ == "__main__":
    main()
