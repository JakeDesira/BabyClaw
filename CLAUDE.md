# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Baby Claw is a local multi-agent assistant built on Ollama. It exposes both a terminal REPL (`src/main.py`) and a Streamlit GUI (`src/gui_app.py`) and routes user prompts through a coordinator that decides whether to answer directly or hand off to a planner/executor pipeline.

## Running

```bash
python -m pip install -r requirements.txt   # ollama, pypdf, streamlit, python-dotenv
python src/main.py                           # terminal REPL
streamlit run src/gui_app.py                 # GUI (add --server.port=8502 if 8501 is busy)
```

Ollama must be running locally (or via `OLLAMA_HOST_URL`) and both configured models must be pulled. There is no test suite, lint config, or build step — `requirements.txt` is the entire toolchain.

## Configuration

Models and limits are read from env vars (or a `.env` at the project root) in `src/config.py`:

- `BABYCLAW_PLANNING_MODEL` (default `gemma4`) — planner / memory router / memory writer.
- `BABYCLAW_REASONING_MODEL` (default `gpt-oss:20b`) — response generator and reviewer.
- `BABYCLAW_PYTHON_RUN_TIMEOUT` (default 10s) — cap for `run_python_file`.
- `BABYCLAW_MAX_ITERATIVE_STEPS` (default 50) — iterative planning step cap.
- `OLLAMA_SUPPORTS_THINK` — only enable when the chosen Ollama model accepts a `think` field; otherwise requests will error.
- `OLLAMA_HOST_URL` — point at a remote Ollama instance.

`reasoning_settings.ReasoningSettings(mode=...)` (low/medium/high) maps the runtime mode onto per-agent `think` levels, the iteration cap, and whether the reviewer runs at all. In the terminal, switch with `reasoning low|medium|high`.

## Architecture

The object graph is wired in **`src/backend_factory.py`**. Both entry points call `build_backend(...)` to assemble the same shared graph; nothing is constructed ad-hoc in `main.py` or `gui_app.py`. When adding a new agent, register it there.

### Request lifecycle
1. The entry point (`main.py` or `gui_app.py`) sends a prompt to `CoordinatorAgent.handle`.
2. The coordinator saves short-term context, consults `MemoryRouter` for whether long-term memory is relevant, and decides simple-vs-complex routing.
3. Simple prompts go straight to `ResponseGenerator`. Complex prompts go to `PlannerAgent` → `PlanExecutor` → `ExecutorAgent` → `ReviewerAgent` (the reviewer only runs in medium/high modes).
4. After the response, `MemoryWriter` may extract durable facts into the SQLite store.

### Two-model split
Speed-sensitive routing/planning/memory uses `planning_model`; reasoning-heavy response generation and review use `reasoning_model`. Anything that picks/parses an action should be on the planning model; anything that writes prose for the user should be on the reasoning model.

### Filesystem safety
`FilesystemGuard` (`src/filesystem_guard.py`) is the **single gate** for all workspace path access. Every workspace tool (everything in `src/agents/executor/tools/`) takes a `filesystem_guard` argument and must resolve paths through `guard.safe_path(...)` or `guard.resolve_path(...)`. Never read or write workspace paths without going through the guard. `media_input/` is for uploaded files only and is read through a separate path.

Approved roots are persisted in the SQLite memory store and restored on startup in `build_backend`. Writes are recorded by `TransactionManager` so the GUI's undo button can roll back the last change set.

### Action constants
`src/action_constants.py` is the authoritative registry of which action names are write/inspect/iterative. When adding a new executor action:
1. Add the tool function under `src/agents/executor/tools/` and re-export it from `tools/__init__.py`.
2. Dispatch it in `ExecutorAgent.handle` (`src/agents/executor/executor.py`).
3. Add the name to the appropriate set(s) in `action_constants.py` — the planner and coordinator both gate behavior on these.
4. Document it in the planner prompt in `src/prompts.py` so the model knows it exists.

### Memory layer
`MemoryAgent` (`src/agents/memory/memory.py`) holds in-RAM short-term turns plus active/previous file context, and delegates durable storage to `SQLiteMemoryStore`. The DB lives at `src/agents/memory/babyclaw_memory.db` (gitignored). `MemoryRouter` decides retrieval; `MemoryWriter` decides storage — both run on the planning model.

### GUI specifics
`gui_app.py` runs agent work in a child `multiprocessing.Process` and pumps trace updates over a `Queue` so the live execution view stays responsive. State that must survive a Streamlit rerun lives in `st.session_state`. Recent chat messages are passed into the child process so follow-ups keep context.

### Prompts
All system prompts (router, planner, plan-executor, memory router/writer, response generator, reviewer) are in **`src/prompts.py`**. Behavior changes that affect what an agent decides usually belong there, not in the agent class.

## Conventions

- Imports inside `src/` use flat module names (`from config import ...`, `import agents`) because `src/` is the run root for both entry points. Don't introduce `src.` prefixes.
- Every agent has a `self._debug(label, value)` helper gated on a `debug` flag and a `[<AGENT> DEBUG]` prefix; `MemoryAgent.save_short_term` filters these prefixes out so debug lines never leak into stored context. Keep the prefix consistent if you add a new agent.
- Tool functions return human-readable strings; error strings start with `Error:`, `Warning:`, or `Access denied` and downstream code (e.g. `_remember_file_if_valid`) checks those prefixes — preserve them.
