# Codex and GitHub Workflow Guide

Use this guide for maintainer sessions that involve Codex setup choices, OpenAI-product questions, or GitHub-side triage.

## Codex Release Policy

- Prefer the latest stable Codex release over alpha or prerelease builds.
- Only move to an alpha build when a known stable-blocking issue is confirmed and the alpha explicitly fixes it.
- When checking for an update, verify the current release source before changing local guidance:
  - Codex CLI release channel: `openai/codex` releases
  - OpenAI product/model guidance: official OpenAI docs on `developers.openai.com` or `openai.com`
- Keep the machine-specific installed version note in `docs/dev/HANDOFF.md`; do not treat it as a permanent repo-wide pinned version.

## OpenAI Docs Policy

- For OpenAI API, Codex product, model-selection, or TTS questions, use the `openai-docs` skill first.
- Prefer current official OpenAI docs over memory or old repo notes.
- Use official OpenAI docs for product/model guidance and use the `openai/codex` release page only for Codex CLI version verification.
- If current docs differ from older local notes, update the local notes instead of repeating stale guidance.

## Model Selection Guidance

- Use the strongest coding model available for:
  - cross-file refactors
  - release work
  - updater logic
  - architecture changes
  - long-horizon debugging
- Use a faster/smaller coding model or lower reasoning effort for:
  - short grep/edit/test loops
  - single-file docs updates
  - narrow bug fixes with a clear local cause
  - read-heavy repo exploration
- If the task starts small and grows into cross-file coordination, step up the model before the risk rises.

## Default GitHub Agent Pair

- Default PR-side agent: `pr-review`
- Default issue-side agent: `issue-tracker`
- Use `github-hub` first only when the user request is vague and the GitHub task type is not clear yet.
- Use `daily-briefing` for start-of-day or inbox-wide snapshots.

## Task Routing

- Maintainer inbox pass:
  - start with `daily-briefing` or `github-hub`
  - use `pr-review` for open PR follow-up
  - use `issue-tracker` for issue/comment follow-up
- PR review:
  - start with `pr-review`
  - if local validation is needed, keep the main repo stable and prefer temp-folder testing
- Issue triage:
  - start with `issue-tracker`
- Release readiness:
  - use `pr-review` for pending code-review state
  - use `daily-briefing` for repo-wide status if needed
  - pair with local `release-ship` and `docs-sync`
- Updater regression work:
  - pair local code changes with `updater-harness`
  - use GitHub agents only for linked PR/issue context, not as the primary verifier
- Docs consistency pass:
  - use local `docs-sync`
  - only involve GitHub agents when the task is tied to a PR, issue, or release note on GitHub

## Formalized Roles

- PR review role:
  - owns diff review, CI/readiness checks, and review comments
  - preferred GitHub agent: `pr-review`
- Updater regression role:
  - owns local fake-feed harness runs, result review, and updater evidence capture
  - preferred local skill: `updater-harness`
- Release verification role:
  - owns versioning, packaging, artifact presence, release doc sync, and ship checks
  - preferred local skills: `release-ship`, `docs-sync`
- Docs consistency role:
  - owns README/developer-doc/user-doc alignment after behavior or workflow changes
  - preferred local skill: `docs-sync`

## Parallel Use

- Split GitHub-side triage from local implementation when they do not share a write set.
- Split docs sync from code changes when the docs work does not depend on unresolved code design.
- Keep the blocking lane local when the next action depends on it immediately.

## Skill Source Priorities

- Review official sources first:
  - `openai/skills` for Codex skill patterns and packaging examples
  - `openai/codex` for current CLI docs, behavior, and release notes
  - `github/github-mcp-server` for official GitHub MCP capability changes
- Current global MCP setup for this machine:
  - Context7 runs through `npx -y @upstash/context7-mcp@latest`
  - GitHub uses the official remote MCP endpoint `https://api.githubcopilot.com/mcp/`
  - GitHub authentication is read from `GITHUB_PAT_TOKEN`; keep the token out of repo files
- Treat community catalogs as idea sources, not automatic install lists.
- Before adopting a third-party skill or MCP source, check:
  - whether the workflow is narrow and repeatable
  - whether it fits Windows safely
  - whether it hides network or destructive assumptions
  - whether the repo is maintained and understandable

## Skill Organization

- Keep global skills focused on general Windows/Codex workflows.
- Keep repo-local skills focused on KeyQuest-specific behavior and release routines.
- Do not reference a skill as required unless it is installed globally or tracked in this repo.
- Keep personal preferences and one-off helper notes in local-only files, not tracked repo docs.
- Prefer reusing a stable tracked guide or skill over duplicating the same workflow note in ad hoc text files.

## Suggested Global Skill Themes

- `windows-core`:
  - shell repair, encoding checks, tool discovery, host diagnostics
- `repo-intake`:
  - repo recon, handoff intake, issue-to-plan workflows
- `docs-and-research`:
  - OpenAI docs, vendor docs, release-note verification
- `browser-work`:
  - browser checks, admin-surface checks, accessibility snapshots
- `maintenance`:
  - regression triage, release-note audit, maintainer inbox
