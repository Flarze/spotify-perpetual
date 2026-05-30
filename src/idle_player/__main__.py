"""Entry point: ``python -m idle_player``.

With no arguments, wires together config load, auth, and the polling loop, then
runs it. Subcommands manage OS autostart:

    idle-player            run the polling loop (default)
    idle-player tray       run the watcher with a system-tray icon
    idle-player setup      interactively create config.yaml
    idle-player auth       (re-)authorize Spotify and cache the token
    idle-player doctor     run diagnostics and print a pass/fail report
    idle-player install    create an OS autostart entry
    idle-player uninstall  remove it
    idle-player status     report whether it is installed
"""

import argparse
from typing import Optional, Sequence

from . import autostart, single_instance
from .doctor import run_doctor
from .tray import run_tray
from .wizard import run_setup
from .auth import (
    TOKEN_INVALID,
    TOKEN_MISSING,
    build_client,
    run_auth_flow,
    token_health,
)
from .config import load_config
from .loop import run, setup_logging, wait_for_network


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Parse arguments and dispatch to the loop or an autostart subcommand."""
    parser = argparse.ArgumentParser(prog="idle-player")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup", help="interactively create config.yaml")
    auth_p = sub.add_parser("auth", help="(re-)authorize Spotify and cache the token")
    auth_p.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authorize URL and prompt for the redirect (headless/WSL)",
    )
    sub.add_parser("tray", help="run the watcher with a system-tray icon")
    sub.add_parser("doctor", help="run diagnostics and print a pass/fail report")
    install_p = sub.add_parser("install", help="create an OS autostart entry")
    install_p.add_argument(
        "--tray",
        action="store_true",
        help="autostart the system-tray UI instead of the headless loop",
    )
    sub.add_parser("uninstall", help="remove the OS autostart entry")
    sub.add_parser("status", help="report whether autostart is installed")
    args = parser.parse_args(argv)

    if args.command == "setup":
        run_setup()
    elif args.command == "auth":
        config = load_config()
        run_auth_flow(config, open_browser=not args.no_browser)
        print(f"Authorized. Token cached at {config.token_cache_path}.")
    elif args.command == "doctor":
        run_doctor()
    elif args.command == "tray":
        lock_path = single_instance.default_lock_path()
        if not single_instance.acquire(lock_path):
            print("idle_player is already running; exiting.")
            return
        try:
            run_tray()
        finally:
            single_instance.release(lock_path)
    elif args.command == "install":
        autostart.install(tray=args.tray)
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
            logger = setup_logging(config)
            # Autostart may run before the network is up; wait briefly first so
            # the token check / first poll do not fail spuriously.
            wait_for_network(config, logger)
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
