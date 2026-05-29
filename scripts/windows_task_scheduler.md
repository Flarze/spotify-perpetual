# Windows autostart: Task Scheduler

Run idle_player at log on, headless, using `pythonw` (no console window).

> Prerequisites:
> 1. Install the package into a venv: from the repo root,
>    `py -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -e .`
> 2. Run it once manually to complete the one-time browser OAuth and cache the
>    token: `.\.venv\Scripts\python.exe -m idle_player` (Ctrl-C to stop).
>    Autostart reuses that cached token.

The app reads `.env` and writes `logs\` relative to its working directory, so
the task's **Start in** must be the repo root. Use the venv's `pythonw.exe` so
the installed dependencies are on the path.

## GUI setup

1. Open **Task Scheduler** -> **Create Task** (not "Basic Task").
2. **General**: name it `spotify-perpetual`. Check "Run only when user is
   logged on". (Don't tick "hidden" expecting headless; `pythonw` handles the
   no-window part.)
3. **Triggers** -> New -> "At log on".
4. **Actions** -> New -> Start a program:
   - Program/script: `C:\path\to\spotify-perpetual\.venv\Scripts\pythonw.exe`
   - Arguments: `-m idle_player`
   - Start in: `C:\path\to\spotify-perpetual`
5. **Conditions**: uncheck "Start only on AC power" for laptops.
6. Save.

## schtasks one-liner

```cmd
schtasks /Create /TN "spotify-perpetual" /SC ONLOGON ^
  /TR "C:\path\to\spotify-perpetual\.venv\Scripts\pythonw.exe -m idle_player" /RL LIMITED
```

`schtasks /TR` has no separate working-directory flag, so prefer the GUI
("Start in") or wrap the command in a `.bat` that `cd`s to the repo root first:

```bat
@echo off
cd /d "C:\path\to\spotify-perpetual"
.venv\Scripts\pythonw.exe -m idle_player
```
