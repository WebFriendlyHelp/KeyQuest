"""Tests for the idle-gate, periodic-timer, and deferred-update logic
added to KeyQuestApp.

These tests do NOT import keyquest_app (which pulls in Pygame/wx and dozens
of modules that use pygame constants at module level).  Instead the
app-level constants are copied here — keeping them in sync is enforced by
test_update_constants_match_source below.
"""

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Constants — must match the values in keyquest_app.py.
# test_update_constants_match_source verifies this automatically.
# ---------------------------------------------------------------------------
_UPDATE_IDLE_INSTALL_S     = 30 * 60    # 1800 s
_UPDATE_PERIODIC_INTERVAL_S = 4 * 3600  # 14400 s
_UPDATE_MENU_RECHECK_MIN_S  = 3600      # 3600 s

_SOURCE_FILE = Path(__file__).parent.parent / "modules" / "keyquest_app.py"


# ---------------------------------------------------------------------------
# Minimal app stub — only the attributes/methods used by the update logic.
# ---------------------------------------------------------------------------

class _AppStub:
    """Carries only the update-related state and methods from KeyQuestApp."""

    class _State:
        mode = "MENU"

    def __init__(self):
        self.state = self._State()
        self._self_update_supported = True
        self._portable_update_mode = False
        self._pending_update_release: dict | None = None
        self._pending_update_manual = False
        self._update_lock = __import__("threading").Lock()
        self._update_check_result = None
        self._update_download_result = None
        self._update_check_thread = None
        self._update_download_thread = None
        self._update_status = ""
        self._update_error_message = ""
        self._update_downloaded_bytes = 0
        self._update_total_bytes = 0
        self._last_user_activity: float = 0.0
        self._update_periodic_last_check: float = 0.0
        # Record calls so tests can assert on them
        self._begin_update_download_calls: list = []
        self._start_update_check_calls: list = []

    def _record_update_event(self, msg: str) -> None:
        pass

    def _begin_update_download(self, payload: dict) -> None:
        self._begin_update_download_calls.append(payload)

    def start_update_check(self, manual: bool) -> None:
        self._start_update_check_calls.append(manual)
        self._update_periodic_last_check = __import__("time").monotonic()

    # --- copied logic from keyquest_app.py ---

    def _begin_pending_update_if_ready(self):
        import time
        if self.state.mode != "MENU":
            return
        if not self._pending_update_release:
            return
        if time.monotonic() - self._last_user_activity < _UPDATE_IDLE_INSTALL_S:
            return
        payload = self._pending_update_release
        self._pending_update_release = None
        self._record_update_event(f"idle install: {payload.get('version')}")
        self._begin_update_download(payload)

    def _handle_update_check_result(self, result: dict):
        import time
        status = result.get("status")
        manual = bool(result.get("manual"))
        if status == "up_to_date":
            return
        if status in ("missing_asset", "error"):
            return
        if status != "update_available":
            return
        idle_s = time.monotonic() - self._last_user_activity
        if self.state.mode == "MENU" and idle_s >= _UPDATE_IDLE_INSTALL_S:
            self._begin_update_download(result)
            return
        self._pending_update_release = result
        self._pending_update_manual = manual

    def _poll_update_work(self):
        import time
        check_result = None
        with self._update_lock:
            if self._update_check_result is not None:
                check_result = self._update_check_result
                self._update_check_result = None
            if self._update_download_result is not None:
                self._update_download_result = None
        if check_result is not None:
            self._handle_update_check_result(check_result)
        # Periodic check
        if (self._self_update_supported
                and self.state.mode != "UPDATING"
                and not (self._update_check_thread and self._update_check_thread.is_alive())
                and not (self._update_download_thread and self._update_download_thread.is_alive())
                and time.monotonic() - self._update_periodic_last_check >= _UPDATE_PERIODIC_INTERVAL_S):
            self.start_update_check(manual=False)
        # Poll deferred update
        if self._pending_update_release:
            self._begin_pending_update_if_ready()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_payload(version="2.0.0"):
    return {"status": "update_available", "version": version, "manual": False,
            "asset": {"name": "KeyQuestSetup.exe", "browser_download_url": "https://x/s.exe", "size": 1},
            "asset_kind": "installer"}


# ---------------------------------------------------------------------------
# Tests: idle gate in _begin_pending_update_if_ready
# ---------------------------------------------------------------------------

class TestBeginPendingUpdateIfReady(unittest.TestCase):

    def setUp(self):
        self.app = _AppStub()
        self.app._pending_update_release = _update_payload()

    def test_does_nothing_when_not_at_menu(self):
        self.app.state.mode = "GAME"
        with mock.patch("time.monotonic", return_value=9999.0):
            self.app._begin_pending_update_if_ready()
        self.assertEqual(self.app._begin_update_download_calls, [])
        self.assertIsNotNone(self.app._pending_update_release)

    def test_does_nothing_when_no_pending_release(self):
        self.app._pending_update_release = None
        with mock.patch("time.monotonic", return_value=9999.0):
            self.app._begin_pending_update_if_ready()
        self.assertEqual(self.app._begin_update_download_calls, [])

    def test_does_nothing_when_not_idle_long_enough(self):
        """User was active 5 minutes ago — too soon to interrupt."""
        now = 1000.0
        self.app._last_user_activity = now - (5 * 60)   # 5 min ago
        with mock.patch("time.monotonic", return_value=now):
            self.app._begin_pending_update_if_ready()
        self.assertEqual(self.app._begin_update_download_calls, [])
        self.assertIsNotNone(self.app._pending_update_release)

    def test_installs_when_idle_exactly_30_minutes(self):
        now = 1000.0
        self.app._last_user_activity = now - _UPDATE_IDLE_INSTALL_S
        with mock.patch("time.monotonic", return_value=now):
            self.app._begin_pending_update_if_ready()
        self.assertEqual(len(self.app._begin_update_download_calls), 1)
        self.assertIsNone(self.app._pending_update_release)

    def test_installs_when_idle_longer_than_30_minutes(self):
        now = 1000.0
        self.app._last_user_activity = now - (40 * 60)   # 40 min ago
        with mock.patch("time.monotonic", return_value=now):
            self.app._begin_pending_update_if_ready()
        self.assertEqual(len(self.app._begin_update_download_calls), 1)

    def test_clears_pending_release_after_install(self):
        now = 1000.0
        self.app._last_user_activity = now - _UPDATE_IDLE_INSTALL_S
        with mock.patch("time.monotonic", return_value=now):
            self.app._begin_pending_update_if_ready()
        self.assertIsNone(self.app._pending_update_release)


# ---------------------------------------------------------------------------
# Tests: _handle_update_check_result idle branching
# ---------------------------------------------------------------------------

class TestHandleUpdateCheckResultIdle(unittest.TestCase):

    def setUp(self):
        self.app = _AppStub()

    def test_installs_immediately_when_at_menu_and_idle(self):
        now = 1000.0
        self.app._last_user_activity = now - _UPDATE_IDLE_INSTALL_S
        with mock.patch("time.monotonic", return_value=now):
            self.app._handle_update_check_result(_update_payload())
        self.assertEqual(len(self.app._begin_update_download_calls), 1)
        self.assertIsNone(self.app._pending_update_release)

    def test_defers_when_at_menu_but_recently_active(self):
        now = 1000.0
        self.app._last_user_activity = now - 60   # only 1 min ago
        with mock.patch("time.monotonic", return_value=now):
            self.app._handle_update_check_result(_update_payload())
        self.assertEqual(self.app._begin_update_download_calls, [])
        self.assertIsNotNone(self.app._pending_update_release)

    def test_defers_when_mid_game_regardless_of_idle(self):
        self.app.state.mode = "GAME"
        now = 1000.0
        self.app._last_user_activity = now - 9999   # very idle, but mid-game
        with mock.patch("time.monotonic", return_value=now):
            self.app._handle_update_check_result(_update_payload())
        self.assertEqual(self.app._begin_update_download_calls, [])
        self.assertIsNotNone(self.app._pending_update_release)

    def test_ignores_up_to_date_result(self):
        with mock.patch("time.monotonic", return_value=9999.0):
            self.app._handle_update_check_result({"status": "up_to_date"})
        self.assertEqual(self.app._begin_update_download_calls, [])

    def test_ignores_error_result(self):
        with mock.patch("time.monotonic", return_value=9999.0):
            self.app._handle_update_check_result({"status": "error", "message": "boom"})
        self.assertEqual(self.app._begin_update_download_calls, [])


# ---------------------------------------------------------------------------
# Tests: periodic timer in _poll_update_work
# ---------------------------------------------------------------------------

class TestPollUpdateWorkPeriodicTimer(unittest.TestCase):

    def setUp(self):
        self.app = _AppStub()

    def test_fires_check_after_interval_elapsed(self):
        now = _UPDATE_PERIODIC_INTERVAL_S + 1
        self.app._update_periodic_last_check = 0.0
        with mock.patch("time.monotonic", return_value=now):
            self.app._poll_update_work()
        self.assertEqual(self.app._start_update_check_calls, [False])

    def test_does_not_fire_check_before_interval(self):
        now = _UPDATE_PERIODIC_INTERVAL_S - 60   # 1 min short
        self.app._update_periodic_last_check = 0.0
        with mock.patch("time.monotonic", return_value=now):
            self.app._poll_update_work()
        self.assertEqual(self.app._start_update_check_calls, [])

    def test_does_not_fire_while_updating(self):
        now = _UPDATE_PERIODIC_INTERVAL_S + 1
        self.app._update_periodic_last_check = 0.0
        self.app.state.mode = "UPDATING"
        with mock.patch("time.monotonic", return_value=now):
            self.app._poll_update_work()
        self.assertEqual(self.app._start_update_check_calls, [])

    def test_does_not_fire_while_check_thread_alive(self):
        now = _UPDATE_PERIODIC_INTERVAL_S + 1
        self.app._update_periodic_last_check = 0.0
        thread = mock.MagicMock()
        thread.is_alive.return_value = True
        self.app._update_check_thread = thread
        with mock.patch("time.monotonic", return_value=now):
            self.app._poll_update_work()
        self.assertEqual(self.app._start_update_check_calls, [])

    def test_poll_applies_deferred_update_when_idle(self):
        """_poll_update_work should call _begin_pending_update_if_ready each frame."""
        now = 1000.0
        self.app._pending_update_release = _update_payload()
        self.app._last_user_activity = now - _UPDATE_IDLE_INSTALL_S
        self.app._update_periodic_last_check = now  # suppress new check
        with mock.patch("time.monotonic", return_value=now):
            self.app._poll_update_work()
        self.assertEqual(len(self.app._begin_update_download_calls), 1)


class TestConstantsMatchSource(unittest.TestCase):
    """Ensure the constants copied into this test file stay in sync with keyquest_app.py."""

    def _extract_constant(self, name: str) -> object:
        tree = ast.parse(_SOURCE_FILE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        # ast.unparse handles BinOp like `4 * 3600`; eval it
                        # with no builtins so only arithmetic is allowed.
                        expr = ast.unparse(node.value)
                        return eval(expr, {"__builtins__": {}})  # noqa: S307
        raise KeyError(f"{name} not found in {_SOURCE_FILE}")

    def test_idle_install_seconds(self):
        self.assertEqual(_UPDATE_IDLE_INSTALL_S, self._extract_constant("_UPDATE_IDLE_INSTALL_S"))

    def test_periodic_interval_seconds(self):
        self.assertEqual(_UPDATE_PERIODIC_INTERVAL_S, self._extract_constant("_UPDATE_PERIODIC_INTERVAL_S"))

    def test_menu_recheck_min_seconds(self):
        self.assertEqual(_UPDATE_MENU_RECHECK_MIN_S, self._extract_constant("_UPDATE_MENU_RECHECK_MIN_S"))


if __name__ == "__main__":
    unittest.main()
