"""Graphical first-run onboarding (tkinter).

Replaces the console wizard for the packaged app: a windowed form collects
credentials, playlists, and options and writes ``config.yaml``; a second small
dialog runs the one-time Spotify browser login. No console, no typed commands.

tkinter is imported lazily inside each function so importing this module never
fails on a build without Tk, and ``gui_available()`` lets the caller fall back
to the console wizard when Tk is genuinely missing. The file-writing and
validation are shared with the console wizard (``wizard._render_config``) so the
two paths produce identical config.
"""

from __future__ import annotations

import contextlib
import io
import threading
import traceback
import webbrowser
from pathlib import Path

from .auth import run_auth_flow
from .config import _normalize_playlist_uri, app_dir, load_config
from .wizard import DEFAULT_REDIRECT_URI, _render_config

DASHBOARD_URL = "https://developer.spotify.com/dashboard"


def _install_crash_handler(root, messagebox) -> None:
    """Surface (don't swallow) tkinter callback errors.

    A windowed exe has no stderr, so tkinter's default handler — which writes
    the traceback to stderr — itself crashes the process, closing the window
    with no message. Instead, show the traceback in a dialog and append it to a
    log file beside the exe so the failure is diagnosable.
    """
    def handler(exc, val, tb):
        msg = "".join(traceback.format_exception(exc, val, tb))
        with contextlib.suppress(Exception):
            (app_dir() / "setup_error.log").write_text(msg)
        with contextlib.suppress(Exception):
            messagebox.showerror("Spotify Perpetual — error", msg)

    root.report_callback_exception = handler


def gui_available() -> bool:
    """True if a Tk display can be opened (so the GUI path is usable)."""
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001 - no Tk at all
        return False
    try:
        root = tk.Tk()
    except Exception:  # noqa: BLE001 - Tk present but no display (headless)
        return False
    root.destroy()
    return True


def run_gui_setup(config_path: str | None = None) -> int:
    """Show the setup form, write ``config.yaml``. Return 0 on save, 1 on cancel.

    Mirrors ``wizard.run_setup`` but with a windowed form instead of console
    prompts. ``config_path`` defaults to ``config.yaml`` beside the exe.
    """
    import tkinter as tk
    from tkinter import messagebox, ttk

    path = Path(config_path) if config_path is not None else app_dir() / "config.yaml"
    result = {"code": 1}  # cancel unless Save succeeds

    root = tk.Tk()
    _install_crash_handler(root, messagebox)
    root.title("Spotify Perpetual — Setup")
    root.minsize(560, 0)
    root.columnconfigure(0, weight=1)

    pad = {"padx": 12, "pady": 4}
    row = 0

    def header(text: str) -> None:
        nonlocal row
        ttk.Label(root, text=text, font=("", 11, "bold")).grid(
            row=row, column=0, sticky="w", padx=12, pady=(12, 2)
        )
        row += 1

    def labeled_entry(label: str, default: str = "", show: str | None = None):
        nonlocal row
        ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        var = tk.StringVar(value=default)
        ttk.Entry(root, textvariable=var, show=show).grid(
            row=row, column=0, sticky="ew", padx=12
        )
        row += 1
        return var

    # --- credentials ------------------------------------------------------
    header("Spotify app credentials")
    ttk.Label(
        root,
        text=(
            "Create a free app at the Spotify Developer Dashboard, then add the\n"
            "redirect URI below to it exactly. Paste the app's Client ID and Secret here."
        ),
        justify="left",
    ).grid(row=row, column=0, sticky="w", padx=12)
    row += 1
    ttk.Button(
        root, text="Open Spotify Developer Dashboard",
        command=lambda: webbrowser.open(DASHBOARD_URL),
    ).grid(row=row, column=0, sticky="w", padx=12, pady=(2, 6))
    row += 1

    client_id = labeled_entry("Client ID")
    client_secret = labeled_entry("Client secret", show="•")
    redirect_uri = labeled_entry("Redirect URI (add this to your Spotify app)", DEFAULT_REDIRECT_URI)

    # --- playlists --------------------------------------------------------
    header("Playlists to keep alive")
    ttk.Label(
        root, text="One Spotify link or URI per line.", justify="left"
    ).grid(row=row, column=0, sticky="w", padx=12)
    row += 1
    playlists_text = tk.Text(root, height=4, width=60)
    playlists_text.grid(row=row, column=0, sticky="ew", padx=12)
    row += 1

    # --- options ----------------------------------------------------------
    header("Playback options")
    opts = ttk.Frame(root)
    opts.grid(row=row, column=0, sticky="ew", padx=12)
    opts.columnconfigure(1, weight=1)
    row += 1

    shuffle = tk.BooleanVar(value=False)
    resume_on_pause = tk.BooleanVar(value=True)
    resume_track = tk.BooleanVar(value=False)
    selection = tk.StringVar(value="rotate")
    repeat = tk.StringVar(value="off")
    volume = tk.StringVar(value="")
    fade_in = tk.StringVar(value="0")
    poll = tk.StringVar(value="30")

    orow = 0

    def opt_label(text: str) -> None:
        ttk.Label(opts, text=text).grid(row=orow, column=0, sticky="w", pady=3)

    opt_label("Repeat")
    ttk.Combobox(
        opts, textvariable=repeat, values=("off", "context", "track"),
        state="readonly", width=12,
    ).grid(row=orow, column=1, sticky="w")
    orow += 1

    opt_label("With several playlists, pick the next one by")
    ttk.Combobox(
        opts, textvariable=selection, values=("rotate", "random"),
        state="readonly", width=12,
    ).grid(row=orow, column=1, sticky="w")
    orow += 1

    opt_label("Volume on start (0–100, blank = leave unchanged)")
    ttk.Entry(opts, textvariable=volume, width=8).grid(row=orow, column=1, sticky="w")
    orow += 1

    opt_label("Fade-in seconds (0 = off)")
    ttk.Entry(opts, textvariable=fade_in, width=8).grid(row=orow, column=1, sticky="w")
    orow += 1

    opt_label("Poll interval (seconds)")
    ttk.Entry(opts, textvariable=poll, width=8).grid(row=orow, column=1, sticky="w")
    orow += 1

    ttk.Checkbutton(opts, text="Shuffle on start", variable=shuffle).grid(
        row=orow, column=0, columnspan=2, sticky="w", pady=2
    )
    orow += 1
    ttk.Checkbutton(
        opts, text="Auto-resume when I pause playback", variable=resume_on_pause
    ).grid(row=orow, column=0, columnspan=2, sticky="w", pady=2)
    orow += 1
    ttk.Checkbutton(
        opts, text="    …resume the same track (not a fresh playlist)",
        variable=resume_track,
    ).grid(row=orow, column=0, columnspan=2, sticky="w", pady=2)
    orow += 1

    # --- save / cancel ----------------------------------------------------
    def on_save() -> None:
        cid = client_id.get().strip()
        secret = client_secret.get().strip()
        redirect = redirect_uri.get().strip()
        if not cid or not secret or not redirect:
            messagebox.showerror("Missing", "Client ID, secret, and redirect URI are required.")
            return

        playlists = [
            _normalize_playlist_uri(line)
            for line in playlists_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        if not playlists:
            messagebox.showerror("Missing", "Add at least one playlist.")
            return

        vol_raw = volume.get().strip()
        vol = None
        if vol_raw:
            try:
                vol = int(vol_raw)
            except ValueError:
                messagebox.showerror("Invalid", "Volume must be a whole number 0–100, or blank.")
                return
            if not 0 <= vol <= 100:
                messagebox.showerror("Invalid", "Volume must be 0–100, or blank.")
                return
        try:
            fade = int(fade_in.get().strip() or "0")
            interval = int(poll.get().strip() or "30")
        except ValueError:
            messagebox.showerror("Invalid", "Fade-in and poll interval must be whole numbers.")
            return

        values = {
            "client_id": cid,
            "client_secret": secret,
            "redirect_uri": redirect,
            "playlists": playlists,
            "playlist_selection": selection.get(),
            "shuffle": shuffle.get(),
            "repeat": repeat.get(),
            "volume": vol,
            "fade_in_seconds": fade,
            "poll_interval": interval,
            "paused_counts_as_playing": not resume_on_pause.get(),
            "resume_paused_track": resume_track.get() if resume_on_pause.get() else False,
        }
        path.write_text(_render_config(values))
        try:
            load_config(env_path=path.parent / ".env", yaml_path=path)
        except Exception as exc:  # noqa: BLE001 - surface, do not crash
            messagebox.showerror("Config error", f"Config did not validate:\n{exc}")
            return

        result["code"] = 0
        root.destroy()

    buttons = ttk.Frame(root)
    buttons.grid(row=row, column=0, sticky="e", padx=12, pady=12)
    ttk.Button(buttons, text="Cancel", command=root.destroy).grid(row=0, column=0, padx=4)
    ttk.Button(buttons, text="Save and continue", command=on_save).grid(row=0, column=1, padx=4)

    root.mainloop()
    return result["code"]


def run_gui_auth(config, *, auth=run_auth_flow) -> bool:
    """Run the one-time Spotify login behind a small window. Return success.

    The button opens the browser; spotipy's local redirect server captures the
    callback automatically (no pasting). Auth runs on a worker thread so the UI
    stays responsive; stdout/stderr are swallowed so spotipy's prints cannot
    crash a windowed (console-less) process.
    """
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    _install_crash_handler(root, messagebox)
    root.title("Spotify Perpetual — Connect")
    root.minsize(420, 0)
    root.columnconfigure(0, weight=1)

    state = {"done": False, "ok": False, "error": None}

    ttk.Label(
        root,
        text="Connect your Spotify account.\nYour browser will open so you can log in.",
        justify="left",
    ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
    status = ttk.Label(root, text="")
    status.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 8))

    def worker() -> None:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                auth(config, open_browser=True)
            state["ok"] = True
        except Exception as exc:  # noqa: BLE001 - report in UI
            state["error"] = str(exc)
        finally:
            state["done"] = True

    def on_login() -> None:
        login_btn.config(state="disabled")
        status.config(text="Waiting for you to log in in the browser…")
        threading.Thread(target=worker, daemon=True).start()
        poll()

    def poll() -> None:
        if not state["done"]:
            root.after(150, poll)
            return
        if state["ok"]:
            status.config(text="Connected! Starting…")
            root.after(800, root.destroy)
        else:
            status.config(text=f"Login failed: {state['error']}")
            login_btn.config(state="normal")

    login_btn = ttk.Button(root, text="Log in with Spotify", command=on_login)
    login_btn.grid(row=1, column=0, sticky="w", padx=16)

    root.mainloop()
    return state["ok"]
