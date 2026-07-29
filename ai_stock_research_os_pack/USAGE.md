# How to use this pack

## Option 1: ChatGPT / Codex / Antigravity
1. Extract the zip.
2. Open `MASTER_PROMPT.md`.
3. Also load `PROJECT_STATE.json`, `PROJECT_CHECKPOINT.md`, and `DECISION_LOG.md`.
4. Paste the master prompt into the AI tool.
5. Ask it to continue from the current phase.
6. After every major step, update the checkpoint files.

## Option 2: Use the prompts one by one
- `MASTER_PROMPT.md` = overall behaviour
- `product_prompt.md` = PRD and roadmap work
- `architecture_prompt.md` = system design
- `backend_prompt.md` = backend implementation
- `frontend_prompt.md` = UI work
- `ai_ml_prompt.md` = model work
- `devops_prompt.md` = deployment and infrastructure
- `testing_prompt.md` = validation
- `documentation_prompt.md` = docs
- `checkpoint_prompt.md` = save and resume state

## Recommended workflow
1. Start with `MASTER_PROMPT.md`
2. Ask for Phase 1 only
3. Save the outputs into the checkpoint files
4. Move to Phase 2
5. Repeat phase by phase

## Resume rule
When switching to another AI tool, always provide:
- `PROJECT_STATE.json`
- `PROJECT_CHECKPOINT.md`
- `DECISION_LOG.md`
- `AI_MEMORY.md`
- any files changed in the current phase

That lets the next AI continue without repeating old work.
