---
name: maintainer-inbox
description: Use when starting or ending a GitHub-heavy KeyQuest maintainer session. Reviews open PRs, open issues, CI state, and recent contributor activity, then summarizes what needs follow-up. Pairs well with GitHub agents such as github-hub, pr-review, issue-tracker, and daily-briefing.
---

# Maintainer Inbox

Use this skill at the start or end of GitHub-focused maintainer work.

## Workflow
1. Check for:
   - open PRs
   - open issues
   - recent contributor comments
   - CI or release failures
2. Prefer GitHub-side agents for remote state:
   - `github-hub`
   - `pr-review`
   - `issue-tracker`
   - `daily-briefing`
3. Prefer local repo skills for local execution:
   - `session-start`
   - `docs-sync`
   - `release-ship`
   - `updater-harness`
4. Summarize:
   - what needs maintainer action now
   - what can wait
   - whether local testing is warranted

## Notes
- This repo's local-only workflow note lives at `local/agent/LOCAL_AGENT_WORKFLOW.md`.
- Prefer temp-folder PR testing unless branch-level editing is actually needed.
