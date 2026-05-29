# Build plan

Step-by-step from scaffold to working app. Each step lists what to build, why,
and how to verify before moving on. Order matters: pure logic first (testable
without Spotify), I/O after, autostart last.

---

## Step 0 — Environment

- [ ] Create virtualenv: `python -m venv .venv && source .venv/bin/activate`
- [ ] `pip install -r requirements.txt`
- [ ] `pip install pytest` (or `pip install -e ".[dev]"`)
- [ ] Confirm `python -c "import spotipy, dotenv, psutil, yaml"` works.

**Done when:** imports succeed, venv active.

---

## Step 1 — Config loader (`config.py`)

Build first because everything depends on it.

- [ ] Load `.env` via python-dotenv.
- [ ] Optionally merge `config.yaml` (YAML overrides/extends env).
- [ ] Define a `Config` dataclass: `client_id`, `client_secret`, `redirect_uri`,
      `playlist_uri`, `poll_interval`, `token_cache_path`,
      `paused_counts_as_playing`, device prefs, logging settings.
- [ ] Validate required fields; raise clear error if missing (never crash with
      a bare KeyError). No credentials hardcoded.

**Verify:** unit test — load from a temp `.env`, assert fields parsed and a
missing required field raises a readable error.

---

## Step 2 — Decision logic (`player.py`, pure part)

The one piece worth testing. No network here.

- [ ] `should_start_playback(playback, paused_counts_as_playing) -> bool`
      where `playback` is the `current_playback()` response shape (or `None`).
- [ ] Cases:
  - `playback is None` (nothing / no device) → `True`
  - `is_playing == True` → `False`
  - paused (`is_playing == False`, has `item`) → return `not paused_counts`
- [ ] Keep it pure: input = data + flag, output = bool. No spotipy calls.

**Verify:** fill in `tests/test_player.py`, remove the skip guard, all cases
green. `pytest` passes.

---

## Step 3 — Auth (`auth.py`)

- [ ] `build_client(config) -> spotipy.Spotify` using `SpotifyOAuth` with scopes
      `user-read-playback-state user-modify-playback-state`.
- [ ] Point `cache_path` at `config.token_cache_path`.
- [ ] First call opens browser once; subsequent calls reuse cache + auto-refresh.

**Verify:** run a throwaway `python -m idle_player`-style script that calls
`build_client()` then `sp.current_playback()`. Browser opens once; second run
does not. Token cache file appears (and is gitignored — confirm `git status`
does NOT list it).

---

## Step 4 — Spotify process detect + launch (`spotify_process.py`)

- [ ] `is_running() -> bool` via psutil (match process name, case-insensitive,
      cross-platform — `Spotify.exe` / `Spotify`).
- [ ] `launch()` branches per `sys.platform`:
  - win32 → `os.startfile("spotify:")` or `start spotify`
  - darwin → `open -a Spotify`
  - linux → `spotify` / xdg `spotify:` URI
  - Don't hardcode install paths.
- [ ] `ensure_running(wait_seconds)`: if not running, launch, sleep
      `wait_seconds` so it registers as a Connect device.

**Verify:** on your OS — kill Spotify, call `ensure_running()`, confirm it
launches and `is_running()` flips to True.

---

## Step 5 — Playback actions (`player.py`, I/O part)

- [ ] `get_playback(sp)` → `sp.current_playback()`.
- [ ] `start_playlist(sp, playlist_uri, device_id=None)` →
      `sp.start_playback(context_uri=..., device_id=...)`.
- [ ] `pick_device(sp, preferred_name)` → choose Connect device; return None if
      none (caller triggers launch fallback).
- [ ] Catch the **"no active device" 404** specifically — that's the launch
      trigger, not a crash.

**Verify:** manual — with Spotify open and idle, call `start_playlist()`;
music plays. With no device, confirm 404 is caught (not raised).

---

## Step 6 — Loop + logging (`loop.py`)

Ties it together.

- [ ] Set up rotating file logger (path/level/rotation from config).
- [ ] `run(config, sp)`:
  1. `playback = get_playback(sp)`
  2. `if should_start_playback(playback, flag):`
     - `ensure_running(wait)`; re-pick device
     - `start_playlist(...)`; on 404 → `ensure_running()` then retry once
  3. else → log "playing, skip"
  4. `sleep(poll_interval)`, repeat
- [ ] Wrap loop body in try/except: log transient API/network errors, continue
      (don't kill the process). Allow clean exit on KeyboardInterrupt.

**Verify:** run for a few minutes. Play music → it does nothing. Stop music →
within one interval it restarts the playlist. Pull network briefly → it logs
an error and keeps looping.

---

## Step 7 — Entry point (`__main__.py`)

- [ ] `main()`: `config = load_config()` → `sp = build_client(config)` →
      `run(config, sp)`.
- [ ] Wire `python -m idle_player` and the `idle-player` console script.

**Verify:** `python -m idle_player` runs the full loop end to end.

---

## Step 8 — Autostart (per-OS, docs already scaffolded)

- [ ] Test the script for your OS (Task Scheduler / launchd / systemd).
- [ ] Confirm it survives reboot/login and reuses the cached token (headless).
- [ ] Fill in any path/command gaps found while testing in `scripts/*.md`.

**Verify:** reboot (or re-login). App starts on its own, no browser prompt,
logs show polling.

---

## Step 9 — Polish

- [ ] README: final setup steps, screenshot/log sample, troubleshooting.
- [ ] Re-check `.gitignore` — `.env` and token cache must be ignored.
- [ ] `pytest` green; manual end-to-end pass on at least one OS.
- [ ] Tag `v0.1.0`.

**Done when:** fresh clone → fill `.env` → run once (auth) → autostart →
Spotify never sits idle.

---

## Dependency order (quick view)

```
config ──> player(pure) ──tests
   │            │
   ├──> auth    │
   ├──> spotify_process
   └──> player(I/O) ──> loop ──> __main__ ──> autostart
```
