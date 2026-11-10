"""build_installer.bat never stamps an installer as version 1.0 by accident.

Fable review 2026-11-10, ui finding 13. When `python` could not read the
version, the findstr fallback set APP_VERSION and then "cleaned" it inside the
same parenthesised block, where %APP_VERSION% had already been expanded at
parse time, and the script then fell through to set "APP_VERSION=1.0" with no
warning.

This runs the REAL version-reading lines of build_installer.bat through real
cmd.exe, in a scratch folder with a fake modules\\version.py and a PATH that
has no python, so the fallback is what runs. It never runs Inno Setup or any
other part of the build.
"""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAT = os.path.join(ROOT, "tools", "build", "build_installer.bat")


def _version_block():
    with open(BAT, "r", encoding="ascii") as handle:
        lines = handle.read().splitlines()
    start = lines.index('set "APP_VERSION="')
    end = next(i for i, line in enumerate(lines) if line.startswith('echo Building installer version'))
    return lines[start:end]


def _run(version_py_text, with_python=False):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "modules"))
        if version_py_text is not None:
            with open(os.path.join(tmp, "modules", "version.py"), "w", encoding="ascii") as handle:
                handle.write(version_py_text)
        script = ["@echo off", "setlocal EnableExtensions", *_version_block(),
                  "echo VERSION=[%APP_VERSION%] NUMERIC=[%APP_VERSION_NUMERIC%]", "exit /b 0",
                  ":fail", "echo FAILED", "exit /b 1"]
        path = os.path.join(tmp, "probe.bat")
        with open(path, "w", encoding="ascii", newline="\r\n") as handle:
            handle.write("\n".join(script) + "\n")
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        path_dirs = [system32]
        if with_python:
            path_dirs.insert(0, os.path.dirname(sys.executable))
        env = dict(os.environ, PATH=os.pathsep.join(path_dirs))
        return subprocess.run(["cmd.exe", "/d", "/c", path], cwd=tmp, env=env,
                              capture_output=True, text=True, timeout=60)


@unittest.skipUnless(os.name == "nt", "cmd.exe only")
class TestInstallerVersion(unittest.TestCase):
    def test_the_probe_reaches_the_version_block(self):
        self.assertGreater(len(_version_block()), 5)

    def test_findstr_fallback_reads_the_real_version(self):
        result = _run('__version__ = "1.42.7"\n')
        self.assertIn("VERSION=[1.42.7]", result.stdout, result.stdout + result.stderr)

    def test_the_normal_python_path_still_works(self):
        """Negative twin: with python on PATH, both values come from python."""
        result = _run('__version__ = "1.42.7"\n', with_python=True)
        self.assertIn("VERSION=[1.42.7] NUMERIC=[1.42.7.0]", result.stdout, result.stdout + result.stderr)

    def test_an_unreadable_version_fails_the_build(self):
        result = _run(None)
        self.assertNotIn("VERSION=[1.0]", result.stdout, result.stdout)
        self.assertIn("FAILED", result.stdout, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
