"""The re-download fallback saves to the real Downloads folder.

Fable review 2026-11-10, modules finding 17. The fallback said "your Downloads
folder" but wrote to Path.home() / "Downloads", the guess CLAUDE.md rules out:
with OneDrive folder backup the real Downloads folder is elsewhere, so the
spoken location was wrong. It now asks Windows, as Report a Problem does.

Does not touch the network: every update_manager call is stubbed and the
download stub stops the worker after recording where it would write.
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from modules import diagnostics, update_manager
from modules.update_controller import AppUpdateController


class TestFallbackUsesKnownDownloads(unittest.TestCase):
    def test_the_fallback_writes_where_windows_says_downloads_is(self):
        with tempfile.TemporaryDirectory() as real_downloads:
            controller = AppUpdateController.__new__(AppUpdateController)
            controller.app = mock.MagicMock()
            controller._portable_update_mode = False
            controller._update_lock = threading.Lock()
            seen = {}

            def _stop(url, dest, progress_callback=None):
                seen["dest"] = Path(dest)
                raise RuntimeError("stop here")

            with mock.patch.object(diagnostics, "_known_folder_downloads", return_value=Path(real_downloads)), \
                    mock.patch.object(update_manager, "fetch_latest_release", return_value={"assets": []}), \
                    mock.patch.object(update_manager, "get_configured_release_url", return_value="x"), \
                    mock.patch.object(update_manager, "select_installer_asset",
                                      return_value={"browser_download_url": "https://example.invalid/a.exe",
                                                    "name": "KeyQuestSetup.exe"}), \
                    mock.patch.object(update_manager, "download_file", side_effect=_stop):
                try:
                    controller._fallback_download_worker("9.9.9")
                except RuntimeError:
                    pass
        self.assertIn("dest", seen, "the worker must reach the download step")
        self.assertEqual(seen["dest"].parent, Path(real_downloads))


if __name__ == "__main__":
    unittest.main()
