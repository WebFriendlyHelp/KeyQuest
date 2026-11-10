"""release.ps1's Invoke-Step must stop on a failing native command.

Fable review 2026-11-10, ui finding 7. Invoke-Step ran its script block and
never looked at $LASTEXITCODE, and $ErrorActionPreference = "Stop" does not turn
a native command's non-zero exit into an error. A red pytest run inside "Run
test suite" was followed by the release commit and `git push origin main`.

These tests lift the real Invoke-Step function out of tools/release.ps1 with
the PowerShell parser and run it against `cmd /c exit N`. They never run the
release script itself. What they would still pass on: a step whose LAST native
command succeeds after an earlier one failed (Invoke-Step can only see the
final exit code), which is why steps check their own codes where it matters.
"""

import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, "tools", "release.ps1")
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _run_step(action: str, extra: str = "", prelude: str = "") -> subprocess.CompletedProcess:
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$ast = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{RELEASE}', [ref]$null, [ref]$null)\n"
        "$fn = $ast.FindAll({ param($n) $n -is "
        "[System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$n.Name -eq 'Invoke-Step' }, $true) | Select-Object -First 1\n"
        "if (-not $fn) { Write-Output 'NO-FUNCTION'; exit 9 }\n"
        "Invoke-Expression $fn.Extent.Text\n"
        f"{prelude}\n"
        "try {\n"
        f"    Invoke-Step 'probe' {{ {action} }} {extra}\n"
        "    Write-Output 'STEP-RETURNED'\n"
        "} catch {\n"
        "    Write-Output ('STEP-THREW: ' + $_.Exception.Message)\n"
        "}\n"
    )
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )


@unittest.skipUnless(POWERSHELL and os.name == "nt", "needs Windows PowerShell")
class TestInvokeStepChecksExitCodes(unittest.TestCase):
    def test_a_failing_native_command_stops_the_release(self):
        result = _run_step("cmd /c exit 3")
        self.assertNotIn("NO-FUNCTION", result.stdout)
        self.assertIn("STEP-THREW", result.stdout, result.stdout + result.stderr)
        self.assertIn("3", result.stdout)

    def test_a_passing_native_command_does_not(self):
        """Negative twin: a green step must still return normally."""
        result = _run_step("cmd /c exit 0")
        self.assertIn("STEP-RETURNED", result.stdout, result.stdout + result.stderr)

    def test_a_stale_exit_code_from_before_the_step_is_ignored(self):
        """A pure PowerShell step must not fail on an earlier command's code."""
        result = _run_step("Write-Host 'pure PowerShell step'", prelude="cmd /c exit 5")
        self.assertIn("STEP-RETURNED", result.stdout, result.stdout + result.stderr)

    def test_a_step_may_opt_out_when_non_zero_is_an_answer(self):
        result = _run_step("cmd /c exit 2", extra="-AllowNonZeroExit")
        self.assertIn("STEP-RETURNED", result.stdout, result.stdout + result.stderr)

    def test_the_tag_probe_step_opts_out(self):
        """`git ls-remote --exit-code` exits 2 when the tag is new, the normal
        case, so the tag availability step must say non-zero is expected."""
        with open(RELEASE, "r", encoding="utf-8") as handle:
            text = handle.read()
        start = text.index('Invoke-Step "Check release tag availability"')
        header = text[start:text.index("{", start)]
        self.assertIn("-AllowNonZeroExit", header)


if __name__ == "__main__":
    unittest.main()
