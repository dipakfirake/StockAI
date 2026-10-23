---
trigger: always_on
---

# Universal workspace rules

This workspace uses `AGENTS.md` as its canonical cross-tool agent policy. Read and obey it completely before using tools or editing files.

Before every implementation or debugging task, read `docs/AI_HANDOFF.md`, `docs/SESSION_INTERACTION_AUDIT.md`, `docs/ENTERPRISE_MODULES_AND_ROLES_MATRIX.md`, `docs/CYBERSECURITY_AUDIT_AND_DEFENSES.md`, `docs/SYSTEM_DESIGN_ARCHITECTURE.md`, inspect the current working tree, and verify the relevant service/test state. Analyze `docs/SESSION_INTERACTION_AUDIT.md` before responding to eliminate hallucinations. Update the handoff and session audit before ending work.

Read project rules, architecture specifications, cybersecurity defenses, session interaction audit, handoff state, git status, logs, and running-service state first.
Analyze the whole affected path before editing.
Find root causes, add focused tests, run relevant full-stack checks, and measure performance changes.
Update the shared handoff before ending, so another tool can continue safely.
Preserve secrets, avoid destructive operations, and report failures honestly.
**STRICT CONFIDENTIALITY RULE:** You are strictly forbidden from scanning, viewing, reading, or analyzing the `.env` file at any time. It contains highly confidential keys. Never read it or request the user to reveal its contents.
**STRICT LIVE SERVER ISOLATION RULE:** You are strictly forbidden from executing commands directly on the live/remote production server (via SSH, SCP, paramiko, rsync, or remote shell execution). All development, building, testing, linting, and Docker container verification must be performed exclusively on **localhost** / local Docker. Always instruct the user by providing the exact, tested, copy-pasteable commands for them to run on the live server manually.