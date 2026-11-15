---
name: project-handoff
description: Leave a concise, verifiable handoff after a development task so another AI can resume from the repository alone.
---

Replace the latest task summary in docs/HANDOFF.md. Record the goal, outcome, key changed paths, branch and full evidence commit, working tree state, exact test commands and observed results, failed attempts, known issues, unfinished work and a concrete next step. Keep stable facts in docs/CURRENT_STATE.md and update the relevant architecture or requirements source when durable decisions change.

Use the code or pre-handoff commit as the evidence baseline to avoid self-reference. Mark tests as skipped, blocked or historical when appropriate. State local vs remote status from observed Git state only. Verify the remote ref before claiming GitHub synchronization. Preserve unrelated edits and keep credentials, personal machine paths and chat transcripts out of project memory.
