"""Usage statistics for the watcher.

Counts what the watcher does (checks, starts, resumes, errors) and how long it
has been watching, persisted to ``stats.json`` beside the config so the numbers
survive restarts. ``idle-player stats`` prints a human-readable report from the
same file.

Recording must never break the daemon: a corrupt file is replaced with a fresh
one on load, and a failed write is logged and swallowed.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import app_dir

STATS_FILE = "stats.json"

# Per-cycle outcomes recorded by the loop. "skip" means playback was already
# active (nothing to do); "started"/"resumed" mean the watcher intervened;
# "no_device" means it wanted to act but found no Connect device; "error" means
# the cycle raised and the loop is backing off.
ACTIONS = ("skip", "started", "resumed", "no_device", "error")

# Outcomes where the watcher actually changed playback.
INTERVENTIONS = ("started", "resumed")

# Per-day counts older than this are dropped to keep the file small.
DAILY_RETENTION_DAYS = 30


def stats_path() -> Path:
    """Where the stats file lives (beside config/cache/logs)."""
    return app_dir() / STATS_FILE


def _empty() -> dict:
    return {
        "version": 1,
        "first_run": None,
        "sessions": 0,
        "runtime_seconds": 0.0,
        "totals": {},
        "daily": {},
    }


def load_stats(path: Optional[Path] = None) -> dict:
    """Load stats, treating a missing or corrupt file as a fresh start."""
    path = path or stats_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    base = _empty()
    base.update(data)
    return base


def save_stats(data: dict, path: Optional[Path] = None) -> None:
    """Write stats atomically (tmp + replace) so a crash cannot corrupt them."""
    path = path or stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


class StatsRecorder:
    """Thread-safe accumulator, persisted after every recorded event.

    Watch time is accumulated as the monotonic delta between consecutive
    events within a session, so time while the process is stopped is never
    counted. ``clock`` and ``today`` are injectable for tests.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        clock=time.monotonic,
        today=date.today,
    ):
        self._path = path or stats_path()
        self._clock = clock
        self._today = today
        self._lock = threading.Lock()
        self._data = load_stats(self._path)
        self._mark = clock()

    def start_session(self) -> None:
        """Mark a new watcher session (process start)."""
        with self._lock:
            if not self._data["first_run"]:
                self._data["first_run"] = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )
            self._data["sessions"] += 1
            self._mark = self._clock()
            self._flush()

    def record(self, action: str) -> None:
        """Count one cycle outcome (ignores unknown actions)."""
        if action not in ACTIONS:
            return
        with self._lock:
            now = self._clock()
            self._data["runtime_seconds"] += max(0.0, now - self._mark)
            self._mark = now
            totals = self._data["totals"]
            totals[action] = totals.get(action, 0) + 1
            day = self._today().isoformat()
            daily = self._data["daily"].setdefault(day, {})
            daily[action] = daily.get(action, 0) + 1
            self._prune(day)
            self._flush()

    def today_interventions(self) -> int:
        """How many times the watcher started/resumed playback today (for the
        tray menu)."""
        with self._lock:
            counts = self._data["daily"].get(self._today().isoformat(), {})
            return sum(counts.get(a, 0) for a in INTERVENTIONS)

    def _prune(self, today_iso: str) -> None:
        cutoff = (
            date.fromisoformat(today_iso) - timedelta(days=DAILY_RETENTION_DAYS)
        ).isoformat()
        self._data["daily"] = {
            d: v for d, v in self._data["daily"].items() if d >= cutoff
        }

    def _flush(self) -> None:
        try:
            save_stats(self._data, self._path)
        except OSError:
            logging.getLogger("idle_player").warning(
                "could not write stats to %s", self._path
            )


def _format_duration(seconds: float) -> str:
    """Compact human duration: "3d 4h 12m", "4h 12m", "12m", "45s"."""
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def format_stats(data: dict, today=date.today) -> str:
    """Render the stats dict as the report ``idle-player stats`` prints."""
    totals = data.get("totals", {})
    checks = sum(totals.get(a, 0) for a in ACTIONS if a != "error")
    if not checks and not data.get("sessions"):
        return "No statistics yet. Run the watcher and they will accumulate here."

    interventions = sum(totals.get(a, 0) for a in INTERVENTIONS)
    since = (data.get("first_run") or "")[:10] or "unknown"
    lines = [
        f"Usage statistics (since {since}, {data.get('sessions', 0)} session(s))",
        "",
        f"  Watch time     {_format_duration(data.get('runtime_seconds', 0))}",
        f"  Checks         {checks}",
        f"  Interventions  {interventions}"
        f" (started {totals.get('started', 0)},"
        f" resumed {totals.get('resumed', 0)})",
        f"  No device      {totals.get('no_device', 0)}",
        f"  Errors         {totals.get('error', 0)}",
    ]

    daily = data.get("daily", {})
    window = [(today() - timedelta(days=i)).isoformat() for i in range(7)]
    recent = [(d, daily[d]) for d in window if d in daily]
    if recent:
        lines += ["", "  Last 7 days:"]
        for day, counts in recent:
            day_checks = sum(counts.get(a, 0) for a in ACTIONS if a != "error")
            day_acted = sum(counts.get(a, 0) for a in INTERVENTIONS)
            lines.append(
                f"    {day}   checks {day_checks}, interventions {day_acted}"
            )
    return "\n".join(lines)
