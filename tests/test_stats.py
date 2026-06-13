"""Tests for usage statistics: persistence, recording, and the report."""

import json
from datetime import date

from idle_player import stats
from idle_player.stats import (
    StatsRecorder,
    format_stats,
    format_summary,
    load_stats,
    save_stats,
)


class FakeClock:
    """Monotonic clock advanced manually by tests."""

    def __init__(self, start=100.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_recorder(tmp_path, today=date(2026, 6, 9)):
    clock = FakeClock()
    rec = StatsRecorder(tmp_path / "stats.json", clock=clock, today=lambda: today)
    return rec, clock


# --- load / save ------------------------------------------------------------


def test_load_stats_missing_file_returns_empty(tmp_path):
    data = load_stats(tmp_path / "stats.json")

    assert data["sessions"] == 0
    assert data["totals"] == {}
    assert data["daily"] == {}


def test_load_stats_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text("{not json")

    data = load_stats(path)

    assert data["totals"] == {}


def test_load_stats_non_dict_json_returns_empty(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text("[1, 2, 3]")

    assert load_stats(path)["sessions"] == 0


def test_save_stats_roundtrip_and_no_tmp_left_behind(tmp_path):
    path = tmp_path / "sub" / "stats.json"
    data = load_stats(path)
    data["sessions"] = 3

    save_stats(data, path)

    assert load_stats(path)["sessions"] == 3
    assert list(path.parent.iterdir()) == [path]  # tmp file replaced, not left


# --- StatsRecorder ----------------------------------------------------------


def test_start_session_sets_first_run_and_counts_sessions(tmp_path):
    rec, _ = make_recorder(tmp_path)

    rec.start_session()
    rec.start_session()

    data = load_stats(tmp_path / "stats.json")
    assert data["sessions"] == 2
    assert data["first_run"]  # set once
    first = data["first_run"]
    rec.start_session()
    assert load_stats(tmp_path / "stats.json")["first_run"] == first


def test_record_counts_totals_and_daily(tmp_path):
    rec, _ = make_recorder(tmp_path)
    rec.start_session()

    rec.record("started")
    rec.record("skip")
    rec.record("skip")

    data = load_stats(tmp_path / "stats.json")
    assert data["totals"] == {"started": 1, "skip": 2}
    assert data["daily"]["2026-06-09"] == {"started": 1, "skip": 2}


def test_record_ignores_unknown_action(tmp_path):
    rec, _ = make_recorder(tmp_path)
    rec.start_session()

    rec.record("bogus")

    assert load_stats(tmp_path / "stats.json")["totals"] == {}


def test_record_accumulates_runtime_between_events(tmp_path):
    rec, clock = make_recorder(tmp_path)
    rec.start_session()

    clock.advance(30)
    rec.record("skip")
    clock.advance(30)
    rec.record("skip")

    data = load_stats(tmp_path / "stats.json")
    assert data["runtime_seconds"] == 60


def test_runtime_survives_restart_without_counting_downtime(tmp_path):
    rec, clock = make_recorder(tmp_path)
    rec.start_session()
    clock.advance(30)
    rec.record("skip")

    # New process much later: the gap must not count as watch time.
    rec2 = StatsRecorder(
        tmp_path / "stats.json", clock=FakeClock(99999.0), today=lambda: date(2026, 6, 9)
    )
    rec2.start_session()
    rec2.record("skip")

    data = load_stats(tmp_path / "stats.json")
    assert data["runtime_seconds"] == 30
    assert data["sessions"] == 2


def test_daily_counts_pruned_after_retention(tmp_path):
    path = tmp_path / "stats.json"
    old_day = "2026-01-01"
    save_stats({**load_stats(path), "daily": {old_day: {"skip": 5}}}, path)
    rec, _ = make_recorder(tmp_path)  # today=2026-06-09, far past retention

    rec.record("skip")

    daily = load_stats(path)["daily"]
    assert old_day not in daily
    assert "2026-06-09" in daily


def test_today_interventions_counts_only_today_starts_and_resumes(tmp_path):
    path = tmp_path / "stats.json"
    save_stats(
        {
            **load_stats(path),
            "daily": {
                "2026-06-09": {"started": 2, "resumed": 1, "skip": 50, "error": 1},
                "2026-06-08": {"started": 9},  # yesterday: excluded
            },
        },
        path,
    )
    rec, _ = make_recorder(tmp_path)

    assert rec.today_interventions() == 3


def test_today_interventions_zero_when_no_data(tmp_path):
    rec, _ = make_recorder(tmp_path)

    assert rec.today_interventions() == 0


def test_record_survives_failed_write(tmp_path, monkeypatch):
    rec, _ = make_recorder(tmp_path)

    def boom(data, path):
        raise OSError("disk full")

    monkeypatch.setattr(stats, "save_stats", boom)

    rec.record("started")  # must not raise


# --- snapshot ---------------------------------------------------------------


def test_snapshot_reflects_recorded_data(tmp_path):
    rec, _ = make_recorder(tmp_path)
    rec.record("started")
    rec.record("skip")

    snap = rec.snapshot()
    assert snap["totals"] == {"started": 1, "skip": 1}


def test_snapshot_is_a_copy_not_the_live_state(tmp_path):
    rec, _ = make_recorder(tmp_path)
    rec.record("started")

    snap = rec.snapshot()
    snap["totals"]["started"] = 999  # mutate the copy
    snap["daily"].clear()

    assert rec.snapshot()["totals"]["started"] == 1  # recorder unaffected


# --- format_summary ---------------------------------------------------------


def test_format_summary_zeroed_before_any_data(tmp_path):
    lines = format_summary(load_stats(tmp_path / "stats.json"))
    assert len(lines) == 6
    assert lines[1] == "Checks          0"
    assert lines[4] == "Errors          0"


def test_format_summary_counts_and_today(tmp_path):
    data = {
        **load_stats(tmp_path / "stats.json"),
        "runtime_seconds": 3 * 3600 + 25 * 60,
        "totals": {"skip": 40, "started": 5, "resumed": 2, "no_device": 1, "error": 3},
        "daily": {"2026-06-09": {"skip": 8, "started": 1, "resumed": 1}},
    }
    lines = format_summary(data, today=lambda: date(2026, 6, 9))

    assert lines[0] == "Watch time      3h 25m"
    assert lines[1] == "Checks          48"  # 40 + 5 + 2 + 1 (error excluded)
    assert lines[2] == "Interventions   7 (started 5, resumed 2)"
    assert lines[3] == "No device       1"
    assert lines[4] == "Errors          3"
    assert lines[5] == "Today           10 checks, 2 interventions"


# --- format_stats -----------------------------------------------------------


def test_format_stats_empty(tmp_path):
    out = format_stats(load_stats(tmp_path / "stats.json"))

    assert "No statistics yet" in out


def test_format_stats_report(tmp_path):
    rec, clock = make_recorder(tmp_path)
    rec.start_session()
    clock.advance(3600)
    rec.record("started")
    rec.record("resumed")
    rec.record("skip")
    rec.record("no_device")
    rec.record("error")

    out = format_stats(load_stats(tmp_path / "stats.json"), today=lambda: date(2026, 6, 9))

    assert "1 session(s)" in out
    assert "Watch time     1h 0m" in out
    assert "Checks         4" in out  # error not counted as a check
    assert "Interventions  2 (started 1, resumed 1)" in out
    assert "No device      1" in out
    assert "Errors         1" in out
    assert "2026-06-09   checks 4, interventions 2" in out


def test_format_stats_last_7_days_excludes_old_days(tmp_path):
    path = tmp_path / "stats.json"
    data = load_stats(path)
    data["sessions"] = 1
    data["totals"] = {"started": 2}
    data["daily"] = {"2026-06-08": {"started": 1}, "2026-05-01": {"started": 1}}

    out = format_stats(data, today=lambda: date(2026, 6, 9))

    assert "2026-06-08" in out
    assert "2026-05-01" not in out


def test_stats_file_is_valid_json(tmp_path):
    rec, _ = make_recorder(tmp_path)
    rec.start_session()
    rec.record("started")

    parsed = json.loads((tmp_path / "stats.json").read_text())
    assert parsed["version"] == 1
