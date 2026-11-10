"""Pet happiness decay is applied once per day away, not once per launch.

Fable review 2026-11-10, modules finding 8. Load subtracted 5 points per day
since pet_last_fed, the startup save wrote the reduced value back, and
pet_last_fed did not move, so the same days were subtracted again at every
launch: happiness 80, fed four days ago, went 60, 40, 20 over three launches
on one day.

Real ProgressManager save and load against a scratch file.
"""

import datetime
import os
import tempfile
import unittest

from modules.state_manager import AppState, ProgressManager


def _launch(path):
    state = AppState()
    ProgressManager(path).load(state, 33)
    ProgressManager(path).save(state)
    return state


class TestPetDecayOnce(unittest.TestCase):
    def _seed(self, path, happiness, days_ago):
        state = AppState()
        state.settings.pet_type = "dragon"
        state.settings.pet_name = "Blaze"
        state.settings.pet_happiness = happiness
        state.settings.pet_last_fed = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).isoformat()
        ProgressManager(path).save(state)

    def test_three_launches_on_one_day_decay_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            self._seed(path, 80, 4)
            values = [_launch(path).settings.pet_happiness for _ in range(3)]
        self.assertEqual(values, [60, 60, 60])

    def test_a_pet_fed_today_does_not_decay(self):
        """Negative twin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "progress.json")
            self._seed(path, 80, 0)
            self.assertEqual(_launch(path).settings.pet_happiness, 80)


if __name__ == "__main__":
    unittest.main()
