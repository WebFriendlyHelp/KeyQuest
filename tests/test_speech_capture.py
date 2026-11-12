"""Tests for the speech ring, the mute switch, and the loopback dev server.

What these prove and what they do not. They prove the ring keeps indices
straight, that mute stops the backend call while still recording, and that the
server routes answer as documented and are off unless asked for. ``/key`` here
is checked by reading the pygame queue it posts to: that is KeyQuest's own
dispatch path, not Windows keyboard routing or focus.
"""

import http.client
import json
import os
import socket
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from modules import dev_server  # noqa: E402
from modules.speech_capture import MUTE_ENV, SpeechRing  # noqa: E402


def _make_speech(muted: bool):
    with (
        patch("modules.speech_manager.Speech._init_tts_engine", return_value=False),
        patch("modules.speech_manager.TOLK_AVAILABLE", False),
        patch.dict(os.environ, {MUTE_ENV: "1" if muted else ""}),
    ):
        from modules.speech_manager import Speech
        speech = Speech()
    speech.backend = "tolk"
    return speech


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class TestSpeechRing(unittest.TestCase):
    def test_indices_are_monotonic_from_zero(self):
        ring = SpeechRing()
        self.assertEqual([ring.record(t) for t in "abc"], [0, 1, 2])
        self.assertEqual(ring.next_index, 3)
        self.assertEqual([e["text"] for e in ring.since(1)], ["b", "c"])
        self.assertEqual(ring.since(3), [])

    def test_ring_is_bounded_and_keeps_newest(self):
        ring = SpeechRing(capacity=3)
        for n in range(5):
            ring.record(f"line {n}")
        entries = ring.since(0)
        self.assertEqual([e["i"] for e in entries], [2, 3, 4])
        # The first index returned being above the one asked for is how a
        # caller detects that lines fell off the end.
        self.assertGreater(entries[0]["i"], 0)
        self.assertEqual(ring.next_index, 5)

    def test_entry_has_text_index_timestamp_and_interrupt(self):
        ring = SpeechRing()
        before = time.time()
        ring.record("hi", interrupt=False, priority=True)
        entry = ring.since(0)[0]
        self.assertEqual(entry["text"], "hi")
        self.assertEqual(entry["i"], 0)
        self.assertFalse(entry["interrupt"])
        self.assertTrue(entry["priority"])
        self.assertGreaterEqual(entry["t"], round(before, 3) - 0.001)

    def test_wait_since_wakes_on_new_speech(self):
        ring = SpeechRing()
        threading.Timer(0.1, ring.record, args=("late",)).start()
        started = time.monotonic()
        entries = ring.wait_since(0, timeout=5.0)
        self.assertEqual([e["text"] for e in entries], ["late"])
        self.assertLess(time.monotonic() - started, 2.0, "should wake, not run out the clock")

    def test_wait_since_times_out_empty(self):
        ring = SpeechRing()
        ring.record("old")
        started = time.monotonic()
        self.assertEqual(ring.wait_since(1, timeout=0.2), [])
        self.assertGreaterEqual(time.monotonic() - started, 0.15)


class TestMute(unittest.TestCase):
    def test_muted_records_but_never_reaches_the_backend(self):
        speech = _make_speech(muted=True)
        self.assertTrue(speech.muted)
        with patch("modules.speech_manager.tolk") as tolk:
            speech.say("quiet please")
        tolk.output.assert_not_called()
        self.assertEqual([e["text"] for e in speech.ring.since(0)], ["quiet please"])

    def test_unmuted_still_records_and_does_reach_the_backend(self):
        # Negative twin: the same call without mute must voice AND record.
        speech = _make_speech(muted=False)
        self.assertFalse(speech.muted)
        with patch("modules.speech_manager.tolk") as tolk:
            speech.say("out loud")
        tolk.output.assert_called_once_with("out loud", interrupt=True)
        self.assertEqual([e["text"] for e in speech.ring.since(0)], ["out loud"])

    def test_dropped_duplicates_are_not_recorded(self):
        speech = _make_speech(muted=True)
        speech.say("twice")
        speech.say("twice")  # inside the debounce window
        self.assertEqual(speech.ring.next_index, 1)


class TestServerOptIn(unittest.TestCase):
    def test_requested_port_parsing(self):
        self.assertIsNone(dev_server.requested_port([], {}))
        self.assertIsNone(dev_server.requested_port([], {dev_server.ENV_FLAG: "0"}))
        self.assertEqual(dev_server.requested_port([], {dev_server.ENV_FLAG: "1"}), dev_server.DEFAULT_PORT)
        self.assertEqual(dev_server.requested_port([], {dev_server.ENV_FLAG: "50001"}), 50001)
        self.assertEqual(dev_server.requested_port(["--dev-server"], {}), dev_server.DEFAULT_PORT)
        self.assertEqual(dev_server.requested_port(["--dev-server=50002"], {}), 50002)

    def test_off_by_default_the_port_is_not_listening(self):
        port = _free_port()
        app = SimpleNamespace(speech=_make_speech(muted=True), state=SimpleNamespace(mode="MENU"))
        self.assertIsNone(dev_server.start_if_requested(app, [], {}))
        self.assertFalse(_listening(port))
        # Twin: the same port does listen once asked for, so the check above
        # is capable of failing.
        server = dev_server.start_if_requested(app, [], {dev_server.ENV_FLAG: str(port)})
        try:
            self.assertIsNotNone(server)
            self.assertTrue(_listening(port))
        finally:
            server.stop()


class TestServerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pygame
        pygame.init()
        cls.pygame = pygame
        cls.port = _free_port()
        cls.speech = _make_speech(muted=True)
        cls.app = SimpleNamespace(speech=cls.speech, state=SimpleNamespace(mode="MENU"))
        cls.server = dev_server.DevServer(cls.app, cls.port).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Host": f"127.0.0.1:{self.port}"}
        hdrs.update(headers or {})
        data = json.dumps(body) if body is not None else None
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8")
        conn.close()
        return resp.status, text

    def test_speech_since_returns_json_lines(self):
        start = self.speech.ring.next_index
        self.speech.say("first route line")
        self.speech.say("second route line")
        status, text = self._call("GET", f"/speech?since={start + 1}")
        self.assertEqual(status, 200)
        entries = [json.loads(line) for line in text.splitlines()]
        self.assertEqual([e["text"] for e in entries], ["second route line"])
        self.assertEqual(entries[0]["i"], start + 1)

    def test_speech_wait_holds_until_something_is_said(self):
        start = self.speech.ring.next_index
        threading.Timer(0.2, self.speech.say, args=("waited for",)).start()
        status, text = self._call("GET", f"/speech?since={start}&wait=5")
        self.assertEqual(status, 200)
        self.assertIn("waited for", text)

    def test_status(self):
        status, text = self._call("GET", "/status")
        self.assertEqual(status, 200)
        data = json.loads(text)
        self.assertEqual(data["pid"], os.getpid())
        self.assertEqual(data["mode"], "MENU")
        self.assertTrue(data["muted"])
        self.assertEqual(data["next_index"], self.speech.ring.next_index)
        self.assertIn("loop_age", data)

    def test_key_posts_keydown_through_the_pygame_queue(self):
        pg = self.pygame
        pg.event.clear()
        status, _ = self._call("POST", "/key", {"key": "down"}, {"X-KeyQuest-Dev": "1"})
        self.assertEqual(status, 200)
        status, _ = self._call("POST", "/key", {"key": "A"}, {"X-KeyQuest-Dev": "1"})
        self.assertEqual(status, 200)
        downs = pg.event.get(pg.KEYDOWN)
        self.assertEqual([(e.key, e.unicode) for e in downs], [(pg.K_DOWN, ""), (pg.K_a, "A")])

    def test_key_without_dev_header_is_refused_and_posts_nothing(self):
        pg = self.pygame
        pg.event.clear()
        status, _ = self._call("POST", "/key", {"key": "down"})
        self.assertEqual(status, 403)
        self.assertEqual(pg.event.get(pg.KEYDOWN), [])

    def _post_body_late(self, path, headers=None, delay=0.05):
        """POST whose body reaches the server after its headers.

        A refusal sent before the body is read, followed by close, leaves the
        late body unread; Windows then resets the connection and the client
        sees ConnectionAbortedError 10053 instead of the reply. That raced in
        about 1 run in 20 of the plain test above; sending the body late makes
        it happen every time.
        """
        body = json.dumps({"key": "down"}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("POST", path, skip_host=True)
            hdrs = {"Host": f"127.0.0.1:{self.port}", "Content-Length": str(len(body))}
            hdrs.update(headers or {})
            for name, value in hdrs.items():
                conn.putheader(name, value)
            conn.endheaders()
            time.sleep(delay)
            conn.send(body)
            resp = conn.getresponse()
            resp.read()
            return resp.status
        finally:
            conn.close()

    def test_refusals_with_a_late_body_still_reach_the_client(self):
        pg = self.pygame
        cases = [
            ("/key", {}, 403),
            ("/key", {"Host": "evil.example:80"}, 403),
            ("/nope", {"X-KeyQuest-Dev": "1"}, 404),
        ]
        for path, headers, expected in cases:
            with self.subTest(path=path, headers=headers):
                pg.event.clear()
                self.assertEqual(self._post_body_late(path, headers), expected)
                self.assertEqual(pg.event.get(pg.KEYDOWN), [])

    def test_allowed_post_with_a_late_body_still_posts(self):
        # Twin: the late-body client itself works, so the refusal test above
        # fails only when the server drops the body.
        pg = self.pygame
        pg.event.clear()
        self.assertEqual(self._post_body_late("/key", {"X-KeyQuest-Dev": "1"}), 200)
        downs = pg.event.get(pg.KEYDOWN)
        self.assertEqual([e.key for e in downs], [pg.K_DOWN])

    def _raw_post_late(self, header_lines, body, delay=0.05):
        """Send raw request headers, then the body late; return the status line.

        For requests http.client will not build: a bad or oversize
        Content-Length, or a chunked body. Without draining, the 400 is sent
        and the connection closed with the late body unread, which Windows
        turns into a reset (ConnectionAbortedError or ConnectionResetError)
        instead of the reply.
        """
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            head = "POST /key HTTP/1.1\r\n" + f"Host: 127.0.0.1:{self.port}\r\n"
            head += "".join(line + "\r\n" for line in header_lines) + "\r\n"
            s.sendall(head.encode("ascii"))
            time.sleep(delay)
            try:
                s.sendall(body)
            except OSError:
                pass  # the server may already have closed; the reply is what matters
            data = b""
            while b"\r\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            return data.split(b"\r\n", 1)[0].decode("ascii", "replace")

    def test_bad_content_length_400_reaches_the_client(self):
        pg = self.pygame
        cases = [
            (["Content-Length: 5000", "X-KeyQuest-Dev: 1"], b"x" * 5000),
            (["Content-Length: abc", "X-KeyQuest-Dev: 1"], b"x" * 300),
            (["Transfer-Encoding: chunked", "X-KeyQuest-Dev: 1"], b'10\r\n{"key": "down"}\r\n0\r\n\r\n'),
        ]
        for headers, body in cases:
            with self.subTest(headers=headers):
                pg.event.clear()
                self.assertIn(" 400 ", self._raw_post_late(headers, body))
                self.assertEqual(pg.event.get(pg.KEYDOWN), [])

    def test_good_raw_post_still_posts(self):
        # Twin: the raw client works when the request is fine.
        pg = self.pygame
        pg.event.clear()
        body = json.dumps({"key": "down"}).encode("utf-8")
        status = self._raw_post_late([f"Content-Length: {len(body)}", "X-KeyQuest-Dev: 1"], body)
        self.assertIn(" 200 ", status)
        self.assertEqual([e.key for e in pg.event.get(pg.KEYDOWN)], [pg.K_DOWN])

    def test_foreign_host_is_refused(self):
        status, _ = self._call("GET", "/status", headers={"Host": "evil.example:80"})
        self.assertEqual(status, 403)

    def test_unknown_key_is_a_400(self):
        status, _ = self._call("POST", "/key", {"key": "nosuchkey"}, {"X-KeyQuest-Dev": "1"})
        self.assertEqual(status, 400)

    def test_unknown_route_is_a_404(self):
        status, _ = self._call("GET", "/nope")
        self.assertEqual(status, 404)


class TestStuckConnectionEnds(unittest.TestCase):
    """A client that declares a body and never sends it must not hold a thread forever."""

    def _server(self, timeout):
        port = _free_port()
        app = SimpleNamespace(speech=_make_speech(muted=True), state=SimpleNamespace(mode="MENU"))
        with patch.object(dev_server, "_HANDLER_TIMEOUT_SECONDS", timeout, create=True):
            server = dev_server.DevServer(app, port).start()
        self.addCleanup(server.stop)
        return port

    def test_short_body_connection_is_closed_by_the_server(self):
        port = self._server(0.5)
        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
            s.sendall(
                f"POST /key HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                "Content-Length: 100\r\nX-KeyQuest-Dev: 1\r\n\r\n{".encode("ascii")
            )
            started = time.monotonic()
            try:
                leftover = s.recv(4096)
            except (ConnectionResetError, ConnectionAbortedError):
                leftover = b""
            self.assertLess(time.monotonic() - started, 5)
            self.assertNotIn(b" 200 ", leftover)

    def test_long_poll_outlives_the_socket_timeout(self):
        # Twin: /speech?wait= waits in the handler, not on the socket, so a
        # wait longer than the timeout still answers.
        port = self._server(0.3)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/speech?since=999999&wait=1", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
