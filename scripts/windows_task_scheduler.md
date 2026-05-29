# Windows autostart — Task Scheduler

Run idle_player at log on, headless, using `pythonw` (no console window).

> Prerequisite: run `python -m idle_player` manually once to complete the
> one-time browser OAuth and cache the token. Autostart reuses that cache.

## GUI setup

1. Open **Task Scheduler** → **Create Task** (not "Basic Task").
2. **General**: name it `spotify-perpetual`. Check "Run only when user is
   logged on". (Don't tick "hidden" expecting headless — `pythonw` handles the
   no-window part.)
3. **Triggers** → New → "At log on".
4. **Actions** → New → Start a program:
   - Program/script: `pythonw`
   - Arguments: `-m idle_player`
   - Start in: `C:\path\to\spotify-perpetual\src`
5. **Conditions**: uncheck "Start only on AC power" for laptops.
6. Save.

## .bat template (alternative / for testing)

```bat
@echo off
cd /d "C:\path\to\spotify-perpetual\src"
pythonw -m idle_player
```

## schtasks one-liner

```cmd
schtasks /Create /TN "spotify-perpetual" /SC ONLOGON ^
  /TR "pythonw -m idle_player" /RL LIMITED
```

Set the working dir via the GUI ("Start in") or wrap with a .bat as above —
`schtasks /TR` has no separate working-directory flag.
