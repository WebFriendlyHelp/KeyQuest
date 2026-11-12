"""release.ps1's tag-first resume path still checks the What's New heading.

Fable release review, 2026-11-11, low 1. The safe release path creates the tag
first, so release.ps1 takes its resume path (the one that never runs
git add -A). That path skipped every What's New check, including the one that
the heading's day name matches its date, so a release date moved after the
VM checks could ship with the wrong weekday.

These parse the real tools/release.ps1 with the PowerShell parser and report
whether each named step sits inside the "if (-not $resumeExistingTag)" block.
They never run the release script. What they would still pass on: a step that
is reached but does the wrong thing (test_release_invoke_step.py and
release_bump's own tests cover what the steps do).
"""

import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, "tools", "release.ps1")
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _placement(step_name: str) -> str:
    step_name = step_name.replace("'", "''")   # inside a single-quoted PowerShell string
    script = (
        "$ast = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{RELEASE}', [ref]$null, [ref]$null)\n"
        "$cmd = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and "
        "$n.GetCommandName() -eq 'Invoke-Step' -and $n.CommandElements.Count -gt 1 -and "
        f"$n.CommandElements[1].Extent.Text.Trim('\"') -eq '{step_name}' }}, $true) | Select-Object -First 1\n"
        "if (-not $cmd) { 'MISSING'; exit 0 }\n"
        "$p = $cmd.Parent\n"
        "while ($p) {\n"
        "  if ($p -is [System.Management.Automation.Language.IfStatementAst]) {\n"
        "    foreach ($clause in $p.Clauses) {\n"
        "      if ($clause.Item1.Extent.Text -match 'resumeExistingTag' -and "
        "$clause.Item2.Extent.StartOffset -le $cmd.Extent.StartOffset -and "
        "$clause.Item2.Extent.EndOffset -ge $cmd.Extent.EndOffset) { 'SKIPPED-ON-RESUME'; exit 0 }\n"
        "    }\n"
        "  }\n"
        "  $p = $p.Parent\n"
        "}\n"
        "'ALWAYS'\n"
    )
    out = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
    )
    return out.stdout.strip() or "PROBE-ERROR: " + out.stderr.strip()[:400]


@unittest.skipUnless(POWERSHELL, "PowerShell is needed to parse release.ps1")
class ResumePathChecks(unittest.TestCase):
    def test_day_name_check_runs_on_the_resume_path(self):
        self.assertEqual(_placement("Validate day name in What's New heading"), "ALWAYS")

    def test_release_date_is_today_check_runs_on_the_resume_path(self):
        # 1.28.1 review, finding 1: written on the 11th, reviewed on the 12th.
        # The tag is usually made first, so this must run on the resume path.
        self.assertEqual(_placement("Require the release date to be today"), "ALWAYS")

    def test_version_match_check_runs_on_the_resume_path(self):
        self.assertEqual(_placement("Require matching version and What's New entry"), "ALWAYS")

    def test_changed_file_check_is_still_skipped_on_resume(self):
        # Negative twin: on the resume path the tree is clean (the release
        # commit is already made), so "WHATS_NEW.md was edited" cannot hold
        # there and must stay inside the block. It also shows the probe can
        # report SKIPPED-ON-RESUME at all.
        self.assertEqual(_placement("Require plain-language What's New update"), "SKIPPED-ON-RESUME")


if __name__ == "__main__":
    unittest.main()
