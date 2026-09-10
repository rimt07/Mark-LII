## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Create branch `feature/jarvis-workflow-routines` from the current default branch and verify with `git rev-parse --abbrev-ref HEAD` shows the new branch
- [ ] 0.2 Confirm working tree is clean before starting (`git status --porcelain` returns empty)

## 1. Shared Foundation (used by all three batches)

- [ ] 1.1 Create `actions/_deps.py` with `have_cmd(name)`, `run_cmd(args, timeout)`, and `require(dep, human_name)` helpers (use `shutil.which` + list-arg `subprocess.run`, no shell string). Verify by importing in a REPL and asserting `have_cmd("git")` returns a bool and `require("definitely_missing_bin_xyz","X")` returns a Spanish "no está disponible" string
- [ ] 1.2 Add a concise routing-hints block to `core/prompt.txt` mapping the new intents to their tools (standup/commit summary→git_summary, TODO→jira, debug→debug_assist, end of day→eod_summary, containers→container_status, tailscale→network_status, diagnostics→run_diagnostics, runbook→runbook, research→research_synthesize, recall→recall_history, ask both models→multi_model_validate, weekly report→engineering_report). Verify the file still loads (`_load_system_prompt()` returns without error at startup)

## 2. Batch 1 — Developer Daily Workflow: Actions

- [ ] 2.1 Implement `actions/git_summary.py` (`git_summary(parameters, player=None)`): resolve time window (default 24h), run `git log --since/--until --pretty` in the repo containing CWD, summarize key changes via `core.local_llm.generate_text`; handle "not a git repo" and "no commits" per `specs/dev-git-summary`. Verify by calling it directly against this repo for "yesterday" and confirming a natural-language summary (or the correct empty-window message)
- [ ] 2.2 Implement `actions/debug_assist.py` (`debug_assist(parameters, player=None)`): accept `error` + optional `hints`, read referenced files (via filesystem access / MCP `fs`), trace and propose a targeted fix via `generate_text`; handle missing files and insufficient context per `specs/dev-debug-assist`. Verify by passing a sample traceback that names a real file in this repo and confirming the response references that file and a concrete fix
- [ ] 2.3 Implement `actions/todo_jira.py` (`todo_scan_jira(parameters, player=None)`): scan `path` for TODO/FIXME with file+line, format one ticket each, dedupe within a run; if the `jira` MCP server is connected create tickets, else return a dry-run preview stating nothing was created, per `specs/dev-todo-jira`. Verify by scanning `actions/` and confirming a dry-run preview lists discovered markers with locations
- [ ] 2.4 Implement `actions/eod_summary.py` (`eod_summary(parameters, player=None)`): aggregate today's commits + open items (Jira if configured, else note unavailable), produce a readable summary, and persist via `memory.memory_manager.save_session_summary`, per `specs/dev-eod-summary`. Verify by running it and confirming a summary is returned AND a new entry appears in `memory/long_term.json['sessions']`
- [ ] 2.5 Add `jira` server entry to `config/mcp_servers.json` with `"enabled": false` (Atlassian MCP command + placeholder env for URL/token). Verify MCP still initializes on startup and reports the `jira` server as disabled (not connected), with no startup errors

## 3. Batch 1 — Developer Workflow: Registration

- [ ] 3.1 Add Gemini function declarations for `git_summary`, `debug_assist`, `todo_scan_jira`, `eod_summary` to `TOOL_DECLARATIONS` in `main.py` (params per design's interface table). Verify `_build_tools()` returns the four new tools (count increased by 4)
- [ ] 3.2 Add dispatch branches for the four tools in `MarkLII._execute_tool` using `loop.run_in_executor(None, lambda: <action>(parameters=args))`. Verify by triggering each tool through a simulated function call and confirming the action runs and returns a string
- [ ] 3.3 Register the four tools in the agent planner: add them (name + params) to `PLANNER_PROMPT` in `agent/planner.py` and add `_call_tool` branches in `agent/executor.py`. Verify a planned goal ("summarize my commits from yesterday") produces a plan step using `git_summary`
- [ ] 3.4 Batch 1 integration check (AGENT MUST EXECUTE): launch the app (or a headless dispatch harness) and invoke each Batch-1 routine by voice/text intent; confirm both Gemini and Ollama backends reach the tool via `_execute_tool`. Record results in `openspec/changes/jarvis-workflow-routines/reports/YYYY-MM-DD-batch1-integration.md`

## 4. Batch 2 — Infrastructure & Ops: Store + Actions

- [ ] 4.1 Create `memory/workflow_store.py`: lock-guarded read/write for `memory/runbooks.json` (dict of named step-lists) and append/scan for `memory/conversations.jsonl`, plus a lexical `search(query)` reusing the scoring approach from `memory_manager`. Verify by round-tripping a sample runbook and a sample conversation line and reading them back
- [ ] 4.2 Implement `actions/container_status.py` (`container_status(parameters, player=None)`): if `docker` absent return the friendly unavailable message; else list running containers and flag those over `cpu_threshold` (default 80, state the threshold); handle "none running", per `specs/ops-container-status`. Verify on this machine (Docker present or absent) that the correct branch runs
- [ ] 4.3 Implement `actions/network_status.py` (`network_status(parameters, player=None)`): if `tailscale` absent return friendly message; else parse `tailscale status --json`, list online/offline nodes with last-seen when available, and explain anomalies, per `specs/ops-network-status`. Verify the correct branch runs given local Tailscale presence/absence
- [ ] 4.4 Implement `actions/diagnostics.py` (`run_diagnostics(parameters, player=None)`): run requested checks for `target` concurrently via a bounded `ThreadPoolExecutor` (≤4) with per-check timeouts; aggregate into one report; a failed/timed-out check is recorded and does not abort others, per `specs/ops-diagnostics`. Verify by running with a mix of one passing and one intentionally-failing check and confirming both appear in the aggregate
- [ ] 4.5 Implement `actions/runbook.py` (`runbook(parameters, player=None)`) supporting `save`/`list`/`run`: persist/list via `workflow_store`; on `run`, recall by name (tolerant match) and dispatch each step through `_execute_tool` so irreversible steps hit `core/confirm.py`; honor `on_failure: stop|continue`; report unknown runbook, per `specs/ops-runbook`. Verify by saving a 2-step runbook, listing it, and running it (with one step being a confirmation-gated action to confirm the gate fires)

## 5. Batch 2 — Ops Workflow: Registration

- [ ] 5.1 Add Gemini declarations for `container_status`, `network_status`, `run_diagnostics`, `runbook` to `TOOL_DECLARATIONS`. Verify `_build_tools()` count increases by 4
- [ ] 5.2 Add `_execute_tool` dispatch branches for the four Ops tools. Verify each runs via simulated function call
- [ ] 5.3 Register the four Ops tools in `agent/planner.py` (`PLANNER_PROMPT`) and `agent/executor.py` (`_call_tool`). Verify a planned goal ("run full diagnostics on the API") yields a `run_diagnostics` step
- [ ] 5.4 Batch 2 integration check (AGENT MUST EXECUTE): invoke each Ops routine by intent on both backends; confirm graceful degradation messages when Docker/Tailscale are absent and the confirmation gate fires for an irreversible runbook step. Record in `reports/YYYY-MM-DD-batch2-integration.md`

## 6. Batch 3 — Research & Analysis: Provider Router + Actions

- [ ] 6.1 Add an optional `"providers"` block to `config/llm_config.json` (anthropic/openai with `model` + `api_key_env`) and create `core/multi_model.py` exposing `route(prompt, providers) -> {provider: answer}` that reads keys from env, uses official SDKs when present, applies per-provider timeouts, and never returns credential values. Verify `route()` with no configured providers returns only the default backend's answer and skips absent ones without error
- [ ] 6.2 Implement `actions/research_synthesize.py` (`research_synthesize(parameters, player=None)`): use existing `web_search`/browser control to search + fetch top `count` (default 5) pages, synthesize a compared answer with source attribution; handle per-source fetch failure and "no usable results", per `specs/research-web-synthesis`. Verify with a real query and confirm a synthesized comparison with cited sources (not just links)
- [ ] 6.3 Implement `actions/recall_history.py` (`recall_history(parameters, player=None)`): query `workflow_store` conversation history locally, return the relevant past decision or a "nothing found" message; ensure no data leaves the machine, per `specs/research-recall-history`. Verify by appending a known decision line, then recalling it by keyword
- [ ] 6.4 Implement `actions/multi_model_validate.py` (`multi_model_validate(parameters, player=None)`): route `prompt` to named providers via `core/multi_model.route`, always include the default backend, present each answer and summarize agreement/disagreement; skip unavailable providers with a note; never echo secrets, per `specs/research-multi-model`. Verify a prompt returns at least the default backend answer and, when keys are absent, states multi-model comparison was unavailable
- [ ] 6.5 Implement `actions/engineering_report.py` (`engineering_report(parameters, player=None)`): aggregate git history (window default 1w), open Jira tickets (if configured), and conversation history into a sectioned structured report stating the window; note unavailable sources, per `specs/research-engineering-report`. Verify a weekly report is produced from git+history with a clear section layout even when Jira is absent

## 7. Batch 3 — Research Workflow: Registration

- [ ] 7.1 Add Gemini declarations for `research_synthesize`, `recall_history`, `multi_model_validate`, `engineering_report` to `TOOL_DECLARATIONS`. Verify `_build_tools()` count increases by 4
- [ ] 7.2 Add `_execute_tool` dispatch branches for the four Research tools. Verify each runs via simulated function call
- [ ] 7.3 Register the four Research tools in `agent/planner.py` and `agent/executor.py`. Verify a planned goal ("generate a weekly engineering report") yields an `engineering_report` step
- [ ] 7.4 Batch 3 integration check (AGENT MUST EXECUTE): invoke each Research routine by intent on both backends; confirm local-only recall and secret-free multi-model output. Record in `reports/YYYY-MM-DD-batch3-integration.md`

## 8. Cross-Cutting Verification (MANDATORY - AGENT MUST EXECUTE)

- [ ] 8.1 Import smoke test: run `python -c "import main"` (and import each new `actions/*.py`, `core/multi_model.py`, `memory/workflow_store.py`) and confirm no import/syntax errors
- [ ] 8.2 Startup test: launch `python main.py` on both `backend: ollama` and `backend: gemini` configs; confirm the app boots, all 12 new tools appear in `_build_tools()`, and no MCP/init errors for the disabled `jira` server. Record tool count and any warnings
- [ ] 8.3 Graceful-degradation matrix: verify each externally-dependent routine (todo_jira, container_status, network_status, multi_model_validate, engineering_report) returns a useful spoken partial result when its dependency is absent. Record outcomes in `reports/YYYY-MM-DD-degradation-matrix.md`
- [ ] 8.4 Confirm no secret values (API keys/tokens) appear in any routine's returned text, especially `multi_model_validate` and Jira paths

## 9. Update Documentation (MANDATORY - FINAL STEP)

- [ ] 9.1 Update `CLAUDE.md`: add the 12 new tools under "Third-Party Integrations"/tool list, document the new `memory/runbooks.json` + `memory/conversations.jsonl` stores and the optional `providers` block in `llm_config.json`, and the disabled-by-default `jira` MCP entry. Verify the doc reflects the shipped tools and config
- [ ] 9.2 Update `docs/` (or add a short `docs/WORKFLOW_ROUTINES.md`) describing each routine, its voice intent examples, and its external-dependency/config requirements. Verify each of the 12 routines is documented with an example utterance
