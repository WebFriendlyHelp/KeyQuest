"""Launch KeyQuest muted with its dev server, then hear and drive it.

Lets an agent (or a test) find out what KeyQuest said without a person
listening. Stdlib only. See modules/dev_server.py for the routes.

    py -3.11 tools/kq_drive.py launch            # headless, muted, server on
    py -3.11 tools/kq_drive.py speech --since 0 --wait 5
    py -3.11 tools/kq_drive.py key down return
    py -3.11 tools/kq_drive.py status
    py -3.11 tools/kq_drive.py kill

``launch`` is headless by default: SDL's dummy video and audio drivers, so there
is no window to take focus and no sound, and KEYQUEST_NO_SPEECH=1 so nothing is
voiced. ``--window`` opts into a real window, which can take the foreground.
A wx dialog (Options, results, confirmations) is a real window even headless;
while one is open the main loop is blocked and ``status`` reports a growing
``loop_age``.

``launch`` points KEYQUEST_PROGRESS_PATH at a fresh temp folder, so the run
starts as a first run and never reads or writes the real progress.json beside
keyquest.pyw. A fresh progress file also has the Speech Log setting off, so
keyquest_speech.log is only written when ``--speech-log`` asks for it (and that
file is NOT redirected: it always goes beside keyquest.pyw). ``kill``
terminates the process outright and deletes the temp folder.

``key`` is synthetic: it posts a pygame event, which proves KeyQuest's own
dispatch, not how Windows routes a real keystroke or which window has focus.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from modules import dev_server  # noqa: E402

STATE_FILE = Path(tempfile.gettempdir()) / "kq_drive.json"
OUTPUT_LOG = Path(tempfile.gettempdir()) / "kq_drive_output.log"
HUNG_AFTER_SECONDS = 5.0


def _load_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _instance_running() -> bool:
    """True when a KeyQuest from this folder already holds its single-instance lock.

    Checked before launching because a second copy shows a native "already
    open" message box, which is a real window that takes focus.
    """
    if os.name != "nt":
        return False
    from modules.single_instance import mutex_name

    handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, mutex_name())  # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def _request(port: int, method: str, path: str, body: dict | None = None, timeout: float = 5.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"http://{dev_server.HOST}:{port}{path}", data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("X-KeyQuest-Dev", "1")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _require_state() -> dict:
    state = _load_state()
    if state is None:
        sys.exit("not running: no launch recorded (run 'launch' first)")
    return state


def cmd_launch(args) -> int:
    state = _load_state()
    if state and _pid_alive(state["pid"]):
        print(f"already launched: pid {state['pid']} port {state['port']}")
        return 1
    if _instance_running():
        print("refused: a KeyQuest from this folder is already running (not one this tool launched)")
        return 1

    progress_dir = tempfile.mkdtemp(prefix="kq_drive_")
    env = dict(os.environ)
    env["KEYQUEST_NO_SPEECH"] = "1"
    env["KEYQUEST_PROGRESS_PATH"] = os.path.join(progress_dir, "progress.json")
    env[dev_server.ENV_FLAG] = str(args.port)
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    if not args.window:
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
    if args.speech_log:
        env["KEYQUEST_SPEECH_LOG"] = "1"

    if sys.version_info[:2] == (3, 11):
        command = [sys.executable, str(REPO_ROOT / "keyquest.pyw")]
    else:
        command = ["py", "-3.11", str(REPO_ROOT / "keyquest.pyw")]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(OUTPUT_LOG, "w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            command, cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=out, stderr=subprocess.STDOUT, creationflags=creationflags,
        )
    STATE_FILE.write_text(
        json.dumps({"pid": proc.pid, "port": args.port, "progress_dir": progress_dir}), encoding="utf-8"
    )

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(f"crashed during startup: exit code {proc.returncode}; output in {OUTPUT_LOG}")
            STATE_FILE.unlink(missing_ok=True)
            shutil.rmtree(progress_dir, ignore_errors=True)
            return 1
        try:
            status = json.loads(_request(args.port, "GET", "/status", timeout=1.0))
            print(f"ready: pid {status['pid']} port {args.port} mode {status['mode']} next_index {status['next_index']}")
            return 0
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    print(f"not ready after {args.timeout} s; output in {OUTPUT_LOG}")
    return 1


def cmd_speech(args) -> int:
    state = _require_state()
    path = f"/speech?since={args.since}&wait={args.wait}"
    text = _request(state["port"], "GET", path, timeout=args.wait + 5)
    next_index = args.since
    for line in text.splitlines():
        entry = json.loads(line)
        print(f"{entry['i']}: {entry['text']}")
        next_index = entry["i"] + 1
    print(f"next {next_index}")
    return 0


def cmd_key(args) -> int:
    state = _require_state()
    for name in args.keys:
        try:
            _request(state["port"], "POST", "/key", {"key": name})
        except urllib.error.HTTPError as e:
            print(f"key {name} refused: {e.read().decode('utf-8', 'replace')}")
            return 1
        time.sleep(args.gap)
    print(f"sent {len(args.keys)} key(s)")
    return 0


def cmd_status(_args) -> int:
    state = _load_state()
    if state is None:
        print("not running")
        return 1
    if not _pid_alive(state["pid"]):
        print(f"crashed or exited: pid {state['pid']} is gone; output in {OUTPUT_LOG}")
        return 1
    try:
        status = json.loads(_request(state["port"], "GET", "/status"))
    except (urllib.error.URLError, OSError):
        print(f"hung: pid {state['pid']} is alive but the server does not answer")
        return 1
    verdict = "hung or in a dialog" if status["loop_age"] > HUNG_AFTER_SECONDS else "running"
    print(f"{verdict}: {json.dumps(status)}")
    return 0


def _forget(state: dict | None) -> None:
    STATE_FILE.unlink(missing_ok=True)
    if state and state.get("progress_dir"):
        shutil.rmtree(state["progress_dir"], ignore_errors=True)


def cmd_kill(_args) -> int:
    state = _load_state()
    if state is None or not _pid_alive(state["pid"]):
        _forget(state)
        print("not running")
        return 0
    pid = state["pid"]
    os.kill(pid, 9)  # TerminateProcess on Windows
    for _ in range(40):
        if not _pid_alive(pid):
            break
        time.sleep(0.25)
    _forget(state)
    print(f"killed pid {pid}" if not _pid_alive(pid) else f"pid {pid} did not exit")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hear and drive KeyQuest through its dev server.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("launch", help="start KeyQuest muted with the dev server on")
    p.add_argument("--port", type=int, default=dev_server.DEFAULT_PORT)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--window", action="store_true", help="real window (may take focus)")
    p.add_argument("--speech-log", action="store_true", help="also write keyquest_speech.log")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("speech", help="print utterances from index N on")
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--wait", type=float, default=0.0, help="seconds to wait for something new")
    p.set_defaults(func=cmd_speech)

    p = sub.add_parser("key", help="post keys through KeyQuest's dispatch (synthetic)")
    p.add_argument("keys", nargs="+", help="key names such as down, return, escape, or a character")
    p.add_argument("--gap", type=float, default=0.1, help="seconds between keys")
    p.set_defaults(func=cmd_key)

    sub.add_parser("status", help="running, hung, or crashed").set_defaults(func=cmd_status)
    sub.add_parser("kill", help="terminate without saving").set_defaults(func=cmd_kill)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
