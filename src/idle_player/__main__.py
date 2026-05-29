"""Entry point: ``python -m idle_player``.

Wires together config load, auth, and the polling loop, then runs it.
"""

from .auth import build_client
from .config import load_config
from .loop import run


def main() -> None:
    """Load config, authenticate, and run the polling loop."""
    config = load_config()
    sp = build_client(config)
    run(config, sp)


if __name__ == "__main__":
    main()
