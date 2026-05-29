"""Entry point: ``python -m idle_player``.

With no arguments, wires together config load, auth, and the polling loop, then
runs it. Subcommands manage OS autostart:

    idle-player            run the polling loop (default)
    idle-player install    create an OS autostart entry
    idle-player uninstall  remove it
    idle-player status     report whether it is installed
"""

import argparse
from typing import Optional, Sequence

from . import autostart, single_instance
from .auth import build_client
from .config import load_config
from .loop import run


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Parse arguments and dispatch to the loop or an autostart subcommand."""
    parser = argparse.ArgumentParser(prog="idle-player")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install", help="create an OS autostart entry")
    sub.add_parser("uninstall", help="remove the OS autostart entry")
    sub.add_parser("status", help="report whether autostart is installed")
    args = parser.parse_args(argv)

    if args.command == "install":
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
            sp = build_client(config)
            run(config, sp)
        finally:
            single_instance.release(lock_path)


if __name__ == "__main__":
    main()
