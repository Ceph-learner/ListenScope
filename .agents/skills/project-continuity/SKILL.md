---
name: project-continuity
description: Recover development context from repository instructions, Git, and handoff notes before beginning or resuming software work.
---

1. Read root and applicable nested AGENTS.md. Check git status --short --branch, git rev-parse HEAD, and recent commits. Identify the caller's branch, local edits and their relation to the requested work.
2. Read the project overview, current state and latest handoff using the links in AGENTS.md. Follow architecture, requirements, decisions and development links when relevant.
3. Treat handoff claims as leads. Verify the recorded baseline, changed paths, tests and constraints against the current tree, history and available CI evidence. Inspect commits since the recorded baseline. Label checkout, remote and historical release state separately.
4. Identify implemented scope, unresolved work and known risks. Preserve existing edits and respect the current request when choosing the next action. Continue with the requested work.
