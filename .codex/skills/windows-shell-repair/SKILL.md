---
name: windows-shell-repair
description: Use when KeyQuest commands run in a broken or stripped-down Windows shell, especially if PATH, git, gh, Python 3.11, PowerShell host selection, or core environment variables appear missing. Restores the repo's expected shell environment and runs diagnostics.
---

# Windows Shell Repair

Use this skill when Codex or PowerShell on Windows is missing expected tools or env vars.

## Workflow
1. Dot-source or invoke `tools/env_bootstrap.ps1` before external tool calls.
2. Run `powershell -ExecutionPolicy Bypass -File tools/codex_exec_diagnostics.ps1`.
3. Check:
   - active PowerShell executable
   - `PATH`
   - `SystemRoot`, `ComSpec`, `USERPROFILE`, `LOCALAPPDATA`, `HOME`
   - `git`, `gh`, `py -3.11`, `codex`
   - UTF-8 / output encoding state
   - whether `rg` is available
4. If a command still fails after bootstrap, report the exact missing tool or variable instead of assuming a repo bug.

## Notes
- This repo already has a Windows-specific bootstrap. Prefer using it over ad hoc fixes.
- If `rg` is missing, note the slowdown and fall back to PowerShell search commands.

