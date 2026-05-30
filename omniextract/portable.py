"""Cross-platform process helpers (macOS / Linux / Windows).

Same proven approach used elsewhere: give each child its own process group so
the whole tree can be killed on timeout (OCR engines and LibreOffice can hang),
and abstract the one-or-two OS differences in one place.
"""

import os
import signal
import subprocess


def popen_isolation_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(proc) -> None:
    """Kill `proc` and any descendants. Best-effort; never raises."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        pass
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5)
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except Exception:
        pass
