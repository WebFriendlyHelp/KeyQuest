"""The guard must never block the copy an update just relaunched.

This is the interaction that matters most and was untested: the updater kills
the running KeyQuest and starts the new one, and those two briefly overlap. If
the guard refuses during that handoff, the user is left with nothing running
immediately after an update, which is the exact stranding this project spent
months eliminating. A guard that causes that is worse than the bug it prevents.

The integration harness cannot cover this, because its fixture app does not
carry the guard, so it is tested directly here against real processes.
"""

import os
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]

_HOLDER = textwrap.dedent(
    f"""
    import sys, time
    sys.path.insert(0, r"{REPO}")
    from modules.single_instance import InstanceLock
    lock = InstanceLock()
    print("HELD" if lock.acquire(wait_seconds=0.5) else "REFUSED", flush=True)
    time.sleep(float(sys.argv[1]))
    """
)

_CLAIMANT = textwrap.dedent(
    f"""
    import sys
    sys.path.insert(0, r"{REPO}")
    from modules.single_instance import InstanceLock
    lock = InstanceLock()
    print("ACQUIRED" if lock.acquire(wait_seconds=float(sys.argv[1])) else "REFUSED", flush=True)
    """
)


@unittest.skipUnless(os.name == "nt", "named mutex is Windows-only")
class TestUpdateHandoff(unittest.TestCase):
    def _run(self, script, *args, timeout=60):
        return subprocess.run(
            [sys.executable, "-c", script, *[str(a) for a in args]],
            capture_output=True, text=True, timeout=timeout,
        )

    def test_the_relaunched_copy_waits_out_the_departing_one(self) -> None:
        # The shape of an update: the old copy is still alive when the new one
        # starts, and goes away a moment later. The new copy must get in.
        holder = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, "3"],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "HELD")
            claimant = self._run(_CLAIMANT, 15)
            self.assertEqual(
                claimant.stdout.strip(), "ACQUIRED",
                "a copy relaunched by the updater must not be refused just because "
                "the old one had not finished exiting",
            )
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_a_force_killed_copy_does_not_leave_the_lock_stuck(self) -> None:
        # Chosen over a lock file precisely for this: a crash or taskkill must
        # not block every future launch. The updater force-kills the app after
        # 30 seconds, so this is a real path, not a hypothetical.
        holder = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, "60"],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "HELD")
            holder.kill()
            holder.wait(timeout=10)
            time.sleep(0.5)

            after = self._run(_CLAIMANT, 2)
            self.assertEqual(
                after.stdout.strip(), "ACQUIRED",
                "the kernel must release the mutex on process death; if this fails, "
                "a force-killed KeyQuest would never start again",
            )
        finally:
            if holder.poll() is None:
                holder.kill()

    def test_a_genuine_duplicate_is_still_refused(self) -> None:
        # The retry window must not be so forgiving that it defeats the point.
        holder = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, "30"],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "HELD")
            duplicate = self._run(_CLAIMANT, 2)
            self.assertEqual(
                duplicate.stdout.strip(), "REFUSED",
                "a second copy started while the first is genuinely running must be "
                "refused, or it will overwrite the first copy's progress",
            )
        finally:
            holder.kill()
            holder.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
