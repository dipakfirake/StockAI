# Gemini / Antigravity project entry point

Read and follow `AGENTS.md` first. Then read `docs/AI_HANDOFF.md`, `docs/SESSION_INTERACTION_AUDIT.md`, `docs/ENTERPRISE_MODULES_AND_ROLES_MATRIX.md`, `docs/CYBERSECURITY_AUDIT_AND_DEFENSES.md`, and `docs/SYSTEM_DESIGN_ARCHITECTURE.md` before taking any action. Always analyze the session interaction audit before responding to eliminate hallucinations.

**STRICT LIVE SERVER ISOLATION RULE:** Never execute commands directly on the remote production server (no SSH, SCP, or remote shell). All development, building, testing, and container management must be done on localhost / local Docker only. Always provide the user with the exact commands for them to run on the live server.

The detailed Antigravity workspace rule is at `.agents/rules/universal-agent-rules.md`.
