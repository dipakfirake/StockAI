---
trigger: always_on
---

# Universal workspace rules

This workspace uses `AGENTS.md` as its canonical cross-tool agent policy. Read and obey it completely before using tools or editing files.

Before every implementation or debugging task, read `docs/AI_HANDOFF.md`, inspect the current working tree, and verify the relevant service/test state. Update the handoff before ending work.




Read project rules, handoff state, git status, logs, and running-service state first.
Analyze the whole affected path before editing.
Find root causes, add focused tests, run relevant full-stack checks, and measure performance changes.
Update the shared handoff before ending, so another tool can continue safely.
Preserve secrets, avoid destructive operations, and report failures honestly.