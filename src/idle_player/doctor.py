"""``idle-player doctor`` - a one-shot diagnostics report.

Checks the things that make the daemon fail silently in the background:
credentials, network reachability, token validity, Spotify account tier, and
reachable Connect devices. Prints a pass/fail report and returns whether every
check passed (warnings do not count as failure).
"""

from __future__ import annotations

from .auth import TOKEN_MISSING, TOKEN_OK, build_client, token_health
from .config import Config, load_config
from .loop import PROBE_HOST, PROBE_PORT, _probe
from .status import smtc_available

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def _format(results: list[tuple[str, str, str]]) -> str:
    """Render check results as an aligned report."""
    width = max((len(name) for _, name, _ in results), default=0)
    lines = [f"[{status}] {name.ljust(width)}  {detail}" for status, name, detail in results]
    return "\n".join(lines)


def run_doctor(
    load=load_config,
    probe=_probe,
    build=build_client,
    health=token_health,
) -> bool:
    """Run all checks, print a report, and return True if none failed."""
    results: list[tuple[str, str, str]] = []

    # 1. Credentials - everything downstream needs a valid config.
    try:
        config: Config = load()
        results.append((PASS, "Credentials", "loaded successfully"))
    except ValueError as exc:
        results.append((FAIL, "Credentials", str(exc)))
        print(_format(results))
        return False

    # Mode - in hybrid, playback status is read from local SMTC. Control still
    # needs the Web API (checked below), so this is a WARN, never a FAIL.
    if config.mode == "hybrid":
        if smtc_available():
            results.append((PASS, "SMTC", "available; status read locally"))
        else:
            results.append(
                (WARN, "SMTC", "unavailable; falling back to Web API for status")
            )

    # 2. Network - can we reach Spotify at all?
    net_ok = probe(PROBE_HOST, PROBE_PORT, config.network_probe_timeout)
    results.append(
        (PASS, "Network", f"{PROBE_HOST} reachable")
        if net_ok
        else (FAIL, "Network", f"cannot reach {PROBE_HOST}:{PROBE_PORT}")
    )

    # 3. Token - is the saved login usable?
    state = health(config)
    if state == TOKEN_OK:
        results.append((PASS, "Token", "valid or refreshable"))
    elif state == TOKEN_MISSING:
        results.append((FAIL, "Token", "no saved login; run `idle-player auth`"))
    else:
        results.append((FAIL, "Token", "expired or revoked; run `idle-player auth`"))

    # 4 & 5. Account tier and reachable devices - need a working client.
    if net_ok and state == TOKEN_OK:
        try:
            sp = build(config)
            # `product` is only populated when the token carries the
            # user-read-private scope, which this app does not request. So a
            # missing value means "unreadable", not "not Premium".
            product = (sp.me() or {}).get("product")
            if product == "premium":
                results.append((PASS, "Account", "Premium"))
            elif product:
                results.append((WARN, "Account", f"{product}; playback control needs Premium"))
            else:
                results.append(
                    (WARN, "Account", "tier unreadable (no user-read-private scope); needs Premium")
                )

            devices = (sp.devices() or {}).get("devices", [])
            if devices:
                names = ", ".join(d.get("name", "?") for d in devices)
                results.append((PASS, "Devices", f"{len(devices)} reachable: {names}"))
            else:
                results.append(
                    (WARN, "Devices", "none found; open Spotify so it registers as a device")
                )
        except Exception as exc:  # noqa: BLE001 - report any query failure, don't crash
            results.append((FAIL, "Spotify", f"could not query Spotify: {exc}"))
    else:
        results.append((WARN, "Account", "skipped (needs network + valid token)"))
        results.append((WARN, "Devices", "skipped (needs network + valid token)"))

    print(_format(results))
    return all(status != FAIL for status, _, _ in results)
