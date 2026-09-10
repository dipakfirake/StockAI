# Universal AI Agent Operating Rules

This file is the canonical, tool-neutral rule set for this repository. Claude, Codex/ChatGPT, Gemini/Antigravity, and any other AI agent must read it before planning, searching, editing, or running commands.

## Continuity across AI tools

1. Read `docs/AI_HANDOFF.md` and `git status --short` at the start of every implementation, debugging, testing, or review task.
2. Treat the handoff as the shared external memory. Do not assume a previous chat, model, or IDE retained private context.
3. Before making a change, preserve relevant existing work and identify unfinished work, known failures, running services, and test results.
4. Before ending work, update `docs/AI_HANDOFF.md` with: task status, files changed, commands run and results, running services/URLs, known failures, and the exact next safe step.
5. If context is missing, inspect the repository, service status, logs, and test history before changing code. Never invent previous work.

## Required engineering workflow

For every task that uses tools or changes code:

1. Establish the baseline: inspect the handoff, working tree, relevant logs, and running services.
2. Analyze the full affected path (UI, API, data, background jobs, database, and authentication where applicable) before editing.
3. Fix the root cause, not only the visible symptom. Preserve existing working features.
4. Add or update focused automated tests for every bug fix or new business rule.
5. Run proportionate verification. For product changes, run all applicable checks:
   - backend unit tests;
   - Python syntax/static checks;
   - frontend type check and production build;
   - API smoke tests against the running stack;
   - browser/manual UI verification for user-facing changes;
   - performance timing when a data, search, chart, or dashboard path changes.
6. Report failures honestly. Do not claim a system is running, live, accurate, or tested without evidence.

For prose-only requests, do not run unrelated destructive or expensive checks. Still read the handoff when the answer depends on project state.

## Product-quality requirements

- Keep market values dynamic and label data source, time, exchange, and delayed/realtime status. Never fabricate live prices, percentage changes, or predictions.
- Use transparent, explainable formulas for signals, risk, holding periods, and indicators. Predictions must state their timeframe and uncertainty; they are not financial advice.
- Prefer one consolidated API request over duplicated client-side requests. Cache safely, parallelize independent I/O, and measure cold and cached latency.
- All alerts are in-app by default; SMTP is reserved for explicitly configured HIGH-priority alerts only.
- Treat account data, tokens, `.env` values, and personal data as secrets. Never print, commit, or send them externally.
- Build original UI and indicator implementations. Do not copy proprietary code, design assets, branding, or licensed indicators from brokers or charting vendors.
- Preserve accessibility, responsive behavior, loading/error/empty states, and keyboard-friendly interaction.

## Safety and repository discipline

- **STRICT CONFIDENTIALITY RULE:** You are strictly forbidden from scanning, viewing, reading, or analyzing the `.env` file under any circumstances, as it contains highly confidential keys and tokens. If you need a new environment variable added, instruct the user to add it manually or append it to `.env.example`, but NEVER read the actual `.env` file.
- Use the smallest safe change; do not overwrite unrelated user edits.
- Never use destructive git commands or delete data without explicit user approval.
- Validate external inputs, enforce authorization on every protected route, and prevent cross-user data or alert leakage.
- Use migrations for schema changes and document configuration changes in `.env.example`.
- Do not declare completion until the required verification has passed or any remaining blocker is explicit.

## Tool-specific entry points

- Antigravity/Gemini: also reads `.agents/rules/universal-agent-rules.md` and `GEMINI.md`.
- Claude Code: read `CLAUDE.md` and this file.
- Codex/ChatGPT coding agents: read this file and the handoff.
- Chat-based tools without workspace file access: paste the contents of `docs/AI_START_PROMPT.md` and attach `docs/AI_HANDOFF.md` at the first message.
