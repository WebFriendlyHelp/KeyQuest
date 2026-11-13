"""Optional loopback HTTP server that lets an agent hear and drive KeyQuest.

Source runs only, and OFF unless asked for. Turn it on with the environment
variable KEYQUEST_DEV_SERVER (``1`` for the default port, or a port number), or
the command-line flag ``--dev-server`` / ``--dev-server=PORT``.
``tools/kq_drive.py`` does both for you and launches KeyQuest muted. A shipped
(frozen) build ignores both, as it ignores KEYQUEST_NO_SPEECH and
KEYQUEST_PROGRESS_PATH (Fable release review, 2026-11-11).

Routes, all on 127.0.0.1 only:

- ``GET /speech?since=N&wait=S`` - JSON lines, one per utterance with index N or
  later, from ``Speech.ring``. With ``wait``, holds the request up to S seconds
  (capped at 30) until something new is said.
- ``GET /status`` - JSON: pid, version, mode, backend, muted, the next speech
  index, and ``loop_age`` (seconds since the main loop last ran; a large value
  means hung or blocked in a modal wx dialog).
- ``POST /key`` with JSON ``{"key": "down"}`` or ``{"key": "a"}`` - posts a
  KEYDOWN and KEYUP onto the pygame queue, so the key goes through KeyQuest's own
  ``handle_event`` dispatch.

Limits worth stating. ``/key`` is SYNTHETIC input: it proves KeyQuest's dispatch,
not how Windows routes a keystroke or whether the window has focus. Modifiers
are not injected, because ``handle_event`` reads them from
``pygame.key.get_mods()``, which a posted event cannot change. Keys never reach
a wx dialog, which runs its own modal loop.

Browser guard. Any web page can send a simple POST to 127.0.0.1, so ``/key``
requires an ``X-KeyQuest-Dev: 1`` header (a custom header forces a CORS
preflight this server never answers), and every route checks the Host header
against the loopback address to refuse DNS rebinding.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ENV_FLAG = "KEYQUEST_DEV_SERVER"
ARG_FLAG = "--dev-server"
DEFAULT_PORT = 47615
HOST = "127.0.0.1"
_MAX_WAIT_SECONDS = 30.0
# A /key body is a few bytes; anything past this is refused.
_MAX_BODY_BYTES = 4096
# Before a 400 for a body the server will not read, it still swallows what
# the client sends, up to these limits, so the reply is not lost to a reset.
_DRAIN_MAX_BYTES = 65536
_DRAIN_SECONDS = 1.0
_DRAIN_QUIET_SECONDS = 0.25
# Socket timeout per connection, so a client that stops halfway through a
# request ends its connection instead of holding a thread until exit.
# /speech?wait= waits in the handler, not on the socket, so it is unaffected.
_HANDLER_TIMEOUT_SECONDS = 5.0

_KEY_ALIASES = {
    "enter": "return",
    "esc": "escape",
    "pageup": "page up",
    "pagedown": "page down",
    "del": "delete",
}
_KEY_UNICODE = {"space": " ", "return": "\r", "tab": "\t", "backspace": "\b"}


def _parse_port(value: str) -> int | None:
    value = value.strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return None
    if value in {"1", "true", "yes", "on"}:
        return DEFAULT_PORT
    port = int(value)
    if not 1024 <= port <= 65535:
        raise ValueError(f"dev server port out of range: {port}")
    return port


def requested_port(argv: list[str], environ) -> int | None:
    """The port asked for by flag or environment, or None when not asked.
    Always None in a shipped (frozen) build."""
    if getattr(sys, "frozen", False):
        return None
    for arg in argv:
        if arg == ARG_FLAG:
            return DEFAULT_PORT
        if arg.startswith(ARG_FLAG + "="):
            return _parse_port(arg.split("=", 1)[1])
    return _parse_port(environ.get(ENV_FLAG, ""))


def key_event_fields(name: str) -> tuple[int, str]:
    """pygame key code and unicode for a key name or a single character."""
    import pygame

    if len(name) == 1:
        return pygame.key.key_code(name.lower()), name
    key = _KEY_ALIASES.get(name.lower(), name.lower())
    return pygame.key.key_code(key), _KEY_UNICODE.get(key, "")


class DevServer:
    """Background loopback server bound to one running app."""

    def __init__(self, app, port: int) -> None:
        self.app = app
        self.port = port
        self._last_beat = time.monotonic()
        self._httpd = ThreadingHTTPServer((HOST, port), _make_handler(self))
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="KeyQuestDevServer", daemon=True
        )

    def start(self) -> "DevServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def beat(self) -> None:
        """Called once per main-loop pass, so /status can tell hung from busy."""
        self._last_beat = time.monotonic()

    def status(self) -> dict:
        from modules.version import __version__

        speech = self.app.speech
        return {
            "pid": os.getpid(),
            "version": __version__,
            "mode": getattr(self.app.state, "mode", None),
            "backend": speech.backend,
            "muted": bool(speech.muted),
            "next_index": speech.ring.next_index,
            "loop_age": round(time.monotonic() - self._last_beat, 3),
        }

    def post_key(self, name: str) -> None:
        import pygame

        key, char = key_event_fields(name)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=char, mod=0, scancode=0))
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, unicode=char, mod=0, scancode=0))


def start_if_requested(app, argv: list[str], environ) -> DevServer | None:
    """Start the server when asked for, else return None. Never raises."""
    try:
        port = requested_port(argv, environ)
        if port is None:
            return None
        server = DevServer(app, port).start()
        print(f"Dev server listening on http://{HOST}:{port}")
        return server
    except Exception as e:
        print(f"Dev server not started: {e}")
        return None


def _make_handler(server: DevServer):
    allowed_hosts = {f"{HOST}:{server.port}", f"localhost:{server.port}"}

    class Handler(BaseHTTPRequestHandler):
        timeout = None if os.environ.get("KQ_DEBUG_NO_HANDLER_TIMEOUT") else _HANDLER_TIMEOUT_SECONDS  # debug branch only

        def log_message(self, *_args):  # pythonw has no console to write to
            pass

        def _drain_and_refuse(self, message: str) -> None:
            """400 for a body we will not read, after swallowing what arrives.

            Closing with the body unread makes Windows reset the connection,
            and the client sees ConnectionAbortedError instead of the 400.
            Bounded in bytes and in time so a client cannot keep us reading.
            """
            self.close_connection = True
            deadline = time.monotonic() + _DRAIN_SECONDS
            total = 0
            try:
                while total < _DRAIN_MAX_BYTES:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.connection.settimeout(min(remaining, _DRAIN_QUIET_SECONDS))
                    chunk = self.rfile.read1(_DRAIN_MAX_BYTES - total)
                    if not chunk:
                        break
                    total += len(chunk)
            except OSError:  # TimeoutError included: the client went quiet
                pass
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                return
            self._error(400, message)

        def _send(self, code: int, body: str, content_type: str = "application/json") -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, code: int, message: str) -> None:
            self._send(code, json.dumps({"error": message}))

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") in allowed_hosts:
                return True
            self._error(403, "host not allowed")
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            if url.path == "/status":
                self._send(200, json.dumps(server.status()))
            elif url.path == "/speech":
                try:
                    since = int(query.get("since", ["0"])[0])
                    wait = min(float(query.get("wait", ["0"])[0]), _MAX_WAIT_SECONDS)
                except ValueError:
                    self._error(400, "since must be an integer and wait a number")
                    return
                ring = server.app.speech.ring
                entries = ring.wait_since(since, wait) if wait > 0 else ring.since(since)
                lines = "".join(json.dumps(e) + "\n" for e in entries)
                self._send(200, lines, "application/x-ndjson")
            else:
                self._error(404, "unknown route")

        def do_POST(self):
            # Read the body before any refusal. Answering and closing with the
            # body still unread makes Windows reset the connection, so the
            # client gets ConnectionAbortedError instead of the 403 or 404.
            if self.headers.get("Transfer-Encoding"):
                self._drain_and_refuse("send a Content-Length, not Transfer-Encoding")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 <= length <= _MAX_BODY_BYTES:
                self._drain_and_refuse("bad Content-Length")
                return
            body = self.rfile.read(length)
            if not self._host_ok():
                return
            if urlsplit(self.path).path != "/key":
                self._error(404, "unknown route")
                return
            if self.headers.get("X-KeyQuest-Dev") != "1":
                self._error(403, "missing X-KeyQuest-Dev header")
                return
            try:
                name = json.loads(body or b"{}")["key"]
                server.post_key(str(name))
            except (ValueError, KeyError, TypeError) as e:
                self._error(400, f"bad key request: {e}")
                return
            self._send(200, json.dumps({"posted": name}))

    return Handler
