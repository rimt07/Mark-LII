## Why

MARK LII can already run multi-step goals (agent planner/executor), reach external tools over MCP (filesystem + PowerShell), search the web, and remember facts across sessions. But three high-value day-to-day developer/ops/research workflows are not first-class: they require the user to phrase generic goals and hope the planner strings the right primitives together. This change turns twelve concrete routines — spanning a developer's daily loop, infrastructure operations, and research/analysis — into reliable, named intents that the assistant recognizes by voice and executes end-to-end, reusing the existing dispatch, agent, MCP, and memory layers rather than inventing a new engine.

These routines are triggered through the **existing voice activation and tool-dispatch pipeline** (Gemini `_build_tools`/`_execute_tool` and the Ollama backend). The `jarvis "..."` phrasings in the workflow brief are examples of spoken/typed requests, not a new CLI.

## What Changes

Three workflow suites, phased into three implementation batches. All additions are new tools/actions routed through the existing dispatch; no existing behavior is removed.

**Suite 1 — Developer Daily Workflow (Batch 1)**
- `git_summary`: summarize commits over a time window (e.g. "yesterday") with key changes, via a native `git` action + LLM summarization.
- `todo_scan` + Jira ticket creation: scan a path for TODO/FIXME comments and create formatted tickets. Jira access via a **config-gated** Atlassian MCP server that degrades gracefully (returns a dry-run list of proposed tickets) when not configured.
- `debug_assist`: given an error/stack trace and hint files, read the relevant files over the filesystem MCP, trace the stack, and propose a targeted fix.
- `eod_summary`: aggregate the day's commits + open items into a readable end-of-day summary, persisted to session memory for the next briefing.

**Suite 2 — Infrastructure & Ops Workflow (Batch 2)**
- `container_status`: list running containers and flag high CPU/mem, via shell/`docker` with graceful degradation when Docker is absent.
- `network_status`: report Tailscale mesh status and offline nodes via `tailscale status --json`, with graceful degradation when Tailscale is absent.
- `diagnostics`: run a suite of checks (logs, health, db connections, latency) in parallel and aggregate findings, reusing the agent executor.
- `runbook`: store, recall, and execute named remediation runbooks from a dedicated persistent store.

**Suite 3 — Research & Analysis Workflow (Batch 3)**
- `research_synthesize`: search the web, fetch/scrape top results, and synthesize a compared answer (reusing `web_search` + browser control).
- `recall_history`: query prior conversation history to recall past decisions, backed by a dedicated conversation-history store indexed by the memory manager.
- `multi_model_validate`: route the same prompt to multiple LLM providers (e.g. Claude + GPT-4o) and compare answers. **Config-gated** on Anthropic/OpenAI keys; falls back to available backends (Gemini/Ollama) when keys are absent.
- `engineering_report`: combine git history, Jira tickets, and conversation history into a structured weekly report.

**Cross-cutting**
- New persistent stores: `memory/runbooks.json` and `memory/conversations.jsonl`, indexed via the existing memory manager.
- New optional MCP server entries (Jira) added to `config/mcp_servers.json`, disabled by default.
- New optional provider configuration for multi-model routing in `config/llm_config.json`.
- Every routine degrades gracefully: when an external dependency (Jira, Docker, Tailscale, extra LLM providers) is unavailable, the routine returns a useful partial result and a spoken explanation instead of failing.

## Capabilities

### New Capabilities
- `dev-git-summary`: summarize git commit activity over a time window with LLM-generated key-change highlights.
- `dev-todo-jira`: scan source for TODO/FIXME markers and create (or dry-run) formatted Jira tickets.
- `dev-debug-assist`: read referenced files, trace an error/stack, and propose a targeted fix.
- `dev-eod-summary`: aggregate a day's shipped work and open items into a persisted summary.
- `ops-container-status`: report container health and flag resource hogs.
- `ops-network-status`: report Tailscale mesh status and offline nodes.
- `ops-diagnostics`: run and aggregate a parallel diagnostic suite.
- `ops-runbook`: store, recall, and execute named remediation runbooks.
- `research-web-synthesis`: search, scrape, and synthesize a compared web-research answer.
- `research-recall-history`: query and recall decisions from prior conversation history.
- `research-multi-model`: route a prompt across multiple LLM providers and compare.
- `research-engineering-report`: generate a structured report from git, Jira, and history.

### Modified Capabilities
<!-- No existing capabilities change their requirements; this is additive. The mcp-integration change owns mcp-core/mcp-filesystem and is not modified here. -->

## Impact

**New Files:**
- `actions/git_summary.py`, `actions/todo_jira.py`, `actions/debug_assist.py`, `actions/eod_summary.py` (Batch 1)
- `actions/container_status.py`, `actions/network_status.py`, `actions/diagnostics.py`, `actions/runbook.py` (Batch 2)
- `actions/research_synthesize.py`, `actions/recall_history.py`, `actions/multi_model_validate.py`, `actions/engineering_report.py` (Batch 3)
- `memory/runbooks.json`, `memory/conversations.jsonl` (persistent stores)

**Modified Files:**
- `main.py`: add function declarations in `_build_tools()` and dispatch cases in `_execute_tool()` for each new tool.
- `core/ollama_backend.py`: register the same tools for the local backend.
- `agent/planner.py`: add the new tools to the planner's available-tools catalog so multi-step goals can compose them.
- `config/mcp_servers.json`: add a disabled-by-default Jira MCP server entry.
- `config/llm_config.json`: add optional multi-provider routing config.
- `core/prompt.txt`: add routing hints so the assistant recognizes the new intents.
- `requirements.txt`: add optional dependencies only if needed (e.g. Anthropic/OpenAI SDKs), pinned and guarded by config.

**External Dependencies (all optional, config-gated, graceful degradation):**
- Jira (Atlassian MCP server) — needs Jira URL + API token.
- Docker CLI — for container status.
- Tailscale CLI — for network status.
- Anthropic + OpenAI API keys — for multi-model validation.

**No Breaking Changes** — all routines are additive tools. Existing actions, plugins, MCP servers, and memory remain intact.

## Risks & Open Questions
- Phasing "A": this proposal assumes one change covering all three suites, implemented in three sequential batches (Developer → Ops → Research). If the intended "A-3" meant starting with the third (Research) suite instead, the batch order can be reordered without changing scope.
- External-dependency availability (Jira/Docker/Tailscale/extra LLM keys) is unknown; the graceful-degradation requirement makes each routine testable and useful even when the dependency is absent.
- Parallel diagnostics concurrency model (threads vs. async) must fit the existing executor without destabilizing the audio/event loop.
