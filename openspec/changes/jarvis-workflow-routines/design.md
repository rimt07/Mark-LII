## Context

See `proposal.md` (Why) for motivation and the 12 capability specs under `specs/` for behavior contracts. This document covers *how* the routines plug into the existing runtime.

Relevant existing structure (verified in code):
- **Tool declarations**: `TOOL_DECLARATIONS` is a module-level list of Gemini function declarations in `main.py`. `_build_tools()` returns `TOOL_DECLARATIONS + plugin declarations + MCP declarations`.
- **Dispatch**: `MarkLII._execute_tool(fc)` is a single async method with an `if name == ... elif ...` chain. Actions run off the event loop via `loop.run_in_executor(None, lambda: action(parameters=..., player=None))`. The same method is passed to the Ollama backend as `tool_executor=self._execute_tool`, so **registering a tool once here covers both backends**.
- **Actions**: each `actions/*.py` exposes a function `fn(parameters: dict, player=None[, speak=...]) -> str` returning a spoken-language string. Errors are caught inside the action and returned as strings.
- **Agent planner**: `agent/planner.py` has a static `PLANNER_PROMPT` catalog of tools + an executor (`agent/executor.py`) with per-step retry/replan and a `_call_tool` dispatch of its own.
- **LLM access**: `core/local_llm.generate_text(prompt, system=..., model=...)` is backend-aware (Ollama or Gemini) with automatic fallback. Actions must use this, never a hard-coded client.
- **Memory**: `memory/memory_manager.py` provides `update_memory`, `search_memory`, `remember`, `forget`, `save_session_summary`, `load_memory` over `memory/long_term.json` with a threading `Lock`.
- **MCP**: `core/mcp_manager.MCPManager` connects stdio servers from `config/mcp_servers.json`, namespaces tools `{server_id}_{tool_name}`, and routes via `execute_tool()`. `fs` (filesystem) and `shell-mcp-server` (PowerShell) are already configured.
- **Confirmation gate**: `core/confirm.py` — irreversible actions return `[CONFIRMATION_PENDING]` and the UI issues the token.

## Goals / Non-Goals

**Goals:**
- Add each routine as a **native action module** (`actions/<name>.py`) registered once in `TOOL_DECLARATIONS` + `_execute_tool`, so both Gemini and Ollama expose it through existing voice activation.
- Keep every routine **self-degrading**: an absent external dependency yields a useful spoken partial result, never a crash.
- Reuse existing subsystems (agent executor for parallel diagnostics, memory manager for stores, `generate_text` for summarization/synthesis, MCP for filesystem/shell/Jira).
- Isolate external-tool concerns behind small adapter helpers so a missing binary/credential is detected once and reported consistently.

**Non-Goals:**
- No separate `jarvis` CLI entry point — routines are voice/chat intents only (user steer).
- No new always-on background services; routines run on demand.
- No new UI panels (the existing activity log and MCP status indicator suffice).
- No runtime reconfiguration UI for Jira/providers — config is edited in JSON (mirrors the plugin/MCP convention).

## Decisions

### Decision 1: Native actions over plugins or new MCP servers for the core logic

**Choice:** Implement each routine as `actions/<name>.py` with the standard `fn(parameters, player=None) -> str` signature, registered in `TOOL_DECLARATIONS` and `_execute_tool`. External systems (Jira) are reached *through* MCP; git/docker/tailscale are reached through subprocess adapters inside the action.

**Rationale:**
- The dispatch and both backends already flow through `_execute_tool`; one registration covers voice on Gemini and Ollama.
- Actions can compose multiple primitives (git + LLM, search + fetch + synthesize) which a single MCP tool cannot.
- Matches the documented "Adding a New Tool/Action" workflow in `CLAUDE.md`.

**Alternatives considered:**
- *Plugins* (`plugins/*.py`): auto-discovered, but they receive `session_memory` and are user-toggleable; these are first-class product routines, not optional add-ons.
- *Pure MCP servers*: right for Jira (external API with auth) but wrong for git-log-plus-LLM composition; would push orchestration into a server we would have to build.

### Decision 2: Jira via a config-gated MCP server; git/docker/tailscale via subprocess adapters

**Choice:**
- **Jira**: add a `jira` server entry to `config/mcp_servers.json`, `enabled: false` by default. The `todo_jira`/`engineering_report` actions check `mcp_manager.servers["jira"].is_connected()`; if not present/connected they return a **dry-run** result (proposed tickets / report without Jira data).
- **git**: subprocess `git log --since=... --pretty=...` in the repo containing CWD; parse, then summarize via `generate_text`.
- **docker**: subprocess `docker ps` / `docker stats --no-stream`.
- **tailscale**: subprocess `tailscale status --json`.

**Rationale:**
- Jira is an authenticated external API — a natural MCP boundary, and the official Atlassian MCP server exists. Gating on `enabled`/connection keeps startup clean when unused.
- git/docker/tailscale are local CLIs; a thin subprocess adapter with a "is it installed?" probe is simpler and testable than standing up MCP servers, and matches the existing `shell-mcp-server` philosophy without requiring it.

**Alternatives considered:**
- Routing git/docker/tailscale through `shell-mcp-server`: viable, but couples these routines to that server being enabled and to shell-string construction; a direct `subprocess.run(list_args)` avoids injection and is deterministic.

### Decision 3: Graceful degradation is a shared helper, not per-action ad hoc code

**Choice:** Add `actions/_deps.py` with small probes: `have_cmd(name) -> bool` (via `shutil.which`), `run_cmd(args, timeout) -> (rc, out, err)`, and `require(dep, human_name) -> str|None` returning a ready-to-speak "X no está disponible" message when missing. Each action calls the probe first and early-returns the friendly message.

**Rationale:**
- The specs require every routine to degrade gracefully with a spoken explanation; centralizing avoids 12 slightly-different failure messages and makes the behavior testable in one place.
- `shutil.which` + `subprocess.run(list, ...)` avoids shell injection and honors the existing global `CREATE_NO_WINDOW` Popen patch on Windows.

**Alternatives considered:** try/except inside each action — duplicative and inconsistent.

### Decision 4: Two dedicated persistent stores, guarded by the memory manager's lock discipline

**Choice:**
- `memory/runbooks.json` — `{ "<name>": { "steps": [ {"tool": ..., "parameters": {...}, "description": ...} ], "updated": "YYYY-MM-DD" } }`.
- `memory/conversations.jsonl` — append-only, one JSON object per line: `{ "date", "session_id", "topic", "text" }`.
- New module `memory/workflow_store.py` wraps both with the same `threading.Lock` pattern and read/append/search helpers. `recall_history` uses the existing lexical `_score` approach from `memory_manager` (no embeddings) for sub-millisecond search.

**Rationale:**
- Keeps `long_term.json` (identity/preferences, prompt-budgeted) separate from bulk operational data, so conversation history and runbooks never inflate the system prompt.
- JSONL for conversations is append-friendly and cheap to scan; JSON dict for runbooks is easy to edit by hand.
- Reusing the lexical scoring keeps recall local and fast per the `research-recall-history` privacy requirement.

**Alternatives considered:** storing both inside `long_term.json` — rejected: pollutes the prompt-budgeted store and risks the runaway-guard trim deleting operational data.

### Decision 5: Runbook execution reuses `_execute_tool` and the confirmation gate

**Choice:** A runbook step is `{tool, parameters, description}`. Executing a runbook loops its steps and dispatches each through the **same** `_execute_tool` path (constructing a minimal function-call shim), so any irreversible step (e.g. `computer_settings` restart) naturally hits `core/confirm.py`. Stop-vs-continue on failure is a per-runbook field (`on_failure: "stop"|"continue"`, default `stop`).

**Rationale:** guarantees the `ops-runbook` spec's "confirmation for irreversible steps" scenario without re-implementing the gate, and keeps step semantics identical to normal tool calls.

**Alternatives considered:** a bespoke step interpreter — would bypass the confirmation gate and duplicate dispatch.

### Decision 6: Parallel diagnostics via a bounded thread pool, not the audio/async loop

**Choice:** `ops-diagnostics` runs its independent checks with `concurrent.futures.ThreadPoolExecutor` (bounded, e.g. 4 workers) *inside* the action, which itself is already invoked via `loop.run_in_executor`. Each check has its own timeout; failures/timeouts are captured per-check and never propagate.

**Rationale:**
- The action already runs off the main event loop, so a small thread pool there parallelizes I/O-bound checks (subprocess, HTTP) without touching the audio streaming loop.
- Per-check timeouts satisfy the "one check fails → continue" scenario.

**Alternatives considered:** `asyncio.gather` — would require the action to be async and re-enter the running loop; the executor-thread + pool is simpler and isolated.

### Decision 7: Multi-model routing extends `local_llm`, gated on `config/llm_config.json`

**Choice:** Add an optional `"providers"` block to `config/llm_config.json`, e.g. `{ "anthropic": {"model": "...", "api_key_env": "ANTHROPIC_API_KEY"}, "openai": {"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"} }`. New `core/multi_model.py` exposes `route(prompt, providers) -> {provider: answer}`, reading keys from env/config, using the official SDKs when present. `multi_model_validate` calls it, always including the default backend (Gemini/Ollama via `generate_text`) as one voice, and skips any provider whose key/SDK is absent. Credential values are never included in responses.

**Rationale:**
- Keeps provider config beside existing LLM config; reuses `generate_text` for the built-in voice so there is always at least one answer.
- Env-var indirection for keys avoids storing secrets in the comparison output and matches the safety requirement in `research-multi-model`.

**Alternatives considered:** hard-wiring Anthropic/OpenAI — rejected: they become required deps and break the Gemini/Ollama-only default.

### Decision 8: Register routines in the agent planner catalog too

**Choice:** Add the new tool names + parameter summaries to `agent/planner.py`'s `PLANNER_PROMPT` and to `agent/executor.py::_call_tool`, so multi-step goals (e.g. "run diagnostics then message me") can compose them.

**Rationale:** the planner has its own tool catalog independent of `TOOL_DECLARATIONS`; without this, the routines are reachable directly but invisible to composed plans.

**Alternatives considered:** skip the planner — acceptable short-term but would make the routines second-class in multi-step goals; cheap to include now.

### Decision 9: Prompt routing hints in `core/prompt.txt`

**Choice:** Add concise routing lines mapping intents to tools (e.g. "commit summary / standup → `git_summary`", "503s / restart runbook → `runbook`"). Keep additions small to respect prompt budget.

**Rationale:** the assistant recognizes intents by voice through the system prompt; without hints, near-synonyms may not route to the new tools reliably.

## Data & Interface Shapes

Tool declarations (added to `TOOL_DECLARATIONS`, `type: OBJECT` params), one per capability:

| Tool | Key params |
|---|---|
| `git_summary` | `window` (str, default "24h"), `author_only` (bool) |
| `todo_scan_jira` | `path` (str, req), `create` (bool, default false→dry-run) |
| `debug_assist` | `error` (str, req), `hints` (str: files/areas) |
| `eod_summary` | `date` (str, default today) |
| `container_status` | `cpu_threshold` (number, default 80) |
| `network_status` | (none) |
| `run_diagnostics` | `target` (str, req), `checks` (str: comma list) |
| `runbook` | `action` ("save"/"list"/"run"), `name`, `steps` |
| `research_synthesize` | `query` (str, req), `count` (int, default 5) |
| `recall_history` | `query` (str, req) |
| `multi_model_validate` | `prompt` (str, req), `providers` (str: comma list) |
| `engineering_report` | `window` (str, default "1w") |

Each `_execute_tool` branch: `result = await loop.run_in_executor(None, lambda: <action>(parameters=args))`.

## Risks / Trade-offs

- **[Risk]** Subprocess adapters differ across OS (git/docker/tailscale output formats). → **Mitigation:** prefer machine-readable flags (`--json`, `--pretty=format:`); parse defensively and fall back to raw text summarized by `generate_text`.
- **[Risk]** Runbook steps executing arbitrary tools could perform destructive actions. → **Mitigation:** irreversible steps route through the existing confirmation gate (Decision 5); runbooks are user-authored/stored locally.
- **[Risk]** Multi-model routing leaking API keys or hanging on a slow provider. → **Mitigation:** keys via env only, never echoed; per-provider timeout; skip absent providers.
- **[Risk]** Parallel diagnostics oversubscribing the machine. → **Mitigation:** bounded pool (≤4) and per-check timeouts.
- **[Trade-off]** git/docker/tailscale as subprocess rather than MCP means no central capability discovery. → **Acceptable:** deterministic, no extra server lifecycle, matches local-CLI nature.
- **[Trade-off]** Config edited by hand (Jira/providers). → **Acceptable:** mirrors existing MCP/plugin config convention.

## Migration Plan

Phased per the proposal (Developer → Ops → Research), each batch independently shippable:
1. **Batch 1 (Developer):** add `_deps.py`, `git_summary`, `todo_scan_jira`, `debug_assist`, `eod_summary`; register in `TOOL_DECLARATIONS`, `_execute_tool`, planner catalog, prompt hints. Jira entry added to `mcp_servers.json` disabled.
2. **Batch 2 (Ops):** add `workflow_store.py`, `container_status`, `network_status`, `run_diagnostics`, `runbook`; register.
3. **Batch 3 (Research):** add `multi_model.py`, provider config block, `research_synthesize`, `recall_history`, `multi_model_validate`, `engineering_report`; register.

**Rollback:** remove the tool's declaration + dispatch branch (and, per batch, the new module/config entry). No existing behavior depends on the new tools, so removal is non-breaking.

## Open Questions

- **Q:** Exact Jira MCP server package/command and required env vars (URL, token) for the `jira` entry. **Defer:** does not change specs or approach; resolved at Batch-1 config time. Dry-run path is fully specified and testable without it.
- **Q:** Whether `recall_history` should auto-capture every session or only on explicit "remember this decision". **Defer:** the store/query interface is unchanged either way; default to capturing session summaries (reuse `save_session_summary`) plus explicit captures, tunable later.
