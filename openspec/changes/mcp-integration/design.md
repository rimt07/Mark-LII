## Context

MARK LII has a mature plugin system (`core/plugin_loader.py`) and action dispatch (`main.py::_execute_tool`). The MCP SDK requires async context managers for client connections. Current tool execution uses `asyncio.run_in_executor` for blocking operations. The UI already displays state indicators (LISTENING, THINKING) and has plugin enable/disable in config. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Reusable MCP integration that works for any MCP server (not just PyMCP-FS)
- Persistent connections throughout session with automatic reconnection
- Schema conversion that handles all JSON Schema → Gemini mappings
- Minimal UI changes (status indicator only, no full panel)

**Non-Goals:**
- Dynamic server addition at runtime (config changes require restart)
- MCP resource subscriptions (tools only for now)
- UI for browsing available tools (tooltip shows count only)
- Server configuration through UI (edit JSON manually)

## Decisions

### Decision 1: MCPManager Architecture

**Choice:** Single `MCPManager` class managing multiple `MCPServerConnection` instances.

**Rationale:**
- Mirrors existing `PluginRegistry` pattern (familiar to codebase)
- Centralized lifecycle management and error handling
- Easy to add health checks and reconnection logic per-server

**Alternatives Considered:**
- One manager per server → More classes, harder to coordinate shutdown
- Inline in main.py → Would bloat main.py with MCP-specific code

**Implementation:**
```python
class MCPServerConnection:
    """Wraps one MCP client + subprocess"""
    async def connect()      # Launch subprocess, enter context manager
    async def disconnect()   # Exit context manager, kill subprocess
    async def call_tool()    # Route to self._client.call_tool()

class MCPManager:
    """Manages all MCP servers"""
    self.servers = {}  # server_id → MCPServerConnection
    async def initialize()   # Load config, start enabled servers
    async def get_all_tools()  # Merge tools from all servers
    async def execute_tool()   # Parse namespace, route to server
    async def shutdown()     # Disconnect all servers
```

### Decision 2: Async Context Manager Workaround

**Choice:** Store context manager reference in `MCPServerConnection` and manually call `__aenter__`/`__aexit__`.

**Rationale:**
- MCP SDK requires `async with Client(...) as client:` but we need persistent connections
- Context manager lifecycle matches our session lifecycle (connect at startup, disconnect at exit)
- Manual control allows reconnection on failure

**Alternatives Considered:**
- Nest entire session in `async with` → Requires restructuring main.py event loop
- Use `asyncio.create_task` with context manager → Loses reference to client

**Implementation:**
```python
self._context = Client(stdio_server=...)
self._client = await self._context.__aenter__()
# ... use self._client for entire session ...
await self._context.__aexit__(None, None, None)
```

### Decision 3: Namespace Pattern `{server_id}_{tool_name}`

**Choice:** No "mcp_" prefix, just `fs_read_file` (server ID from config key).

**Rationale:**
- Shorter names for Gemini function calls
- Server ID already identifies origin (fs, db, gh, etc.)
- Matches user preference (decision 2 in exploration)

**Alternatives Considered:**
- `mcp_fs_read_file` → Redundant, longer names
- `read_file_fs` → Awkward, suffix doesn't scan naturally
- No namespace at all → Would collide with file_controller

### Decision 4: Schema Conversion Strategy

**Choice:** Recursive type mapping function with 1:1 field preservation.

**Rationale:**
- JSON Schema and Gemini function declarations are structurally similar
- Only type names differ (string vs STRING)
- Preserve all metadata (descriptions, required fields, nested objects)

**Implementation:**
```python
def convert_mcp_schema_to_gemini(mcp_schema: dict) -> dict:
    TYPE_MAP = {
        "string": "STRING", "integer": "INTEGER",
        "number": "NUMBER", "boolean": "BOOLEAN",
        "array": "ARRAY", "object": "OBJECT"
    }
    gemini_schema = {"type": TYPE_MAP[mcp_schema["type"]]}
    if "properties" in mcp_schema:
        gemini_schema["properties"] = {
            k: convert_mcp_schema_to_gemini(v)
            for k, v in mcp_schema["properties"].items()
        }
    if "required" in mcp_schema:
        gemini_schema["required"] = mcp_schema["required"]
    if "description" in mcp_schema:
        gemini_schema["description"] = mcp_schema["description"]
    return gemini_schema
```

### Decision 5: Path Resolution for PyMCP-FS

**Choice:** Let PyMCP-FS handle all path validation. Pass paths from Gemini unchanged.

**Rationale:**
- PyMCP-FS already enforces allowed directory boundaries
- Relative paths ("main.py") resolve against server's root automatically
- Absolute paths outside allowed directory are rejected by server
- No need to duplicate security logic in MARK LII

**Alternatives Considered:**
- Prepend `D:/Programacion/ia/Mark-LII/` to all paths → Breaks relative path handling
- Validate in MCPManager → Duplicates server logic, harder to maintain

### Decision 6: UI Status Indicator Placement

**Choice:** Bottom-right corner, inline text format: `MCP: ● fs [Status: OK]`

**Rationale:**
- Non-intrusive (doesn't overlap activity log or waveform)
- Consistent with existing state display pattern
- Simple to implement (QLabel in bottom layout)

**Implementation:**
```python
# In ui.py
self.mcp_status_label = QLabel("MCP: ○")
self.mcp_status_label.setStyleSheet("color: #666;")
# ... add to bottom layout ...

def update_mcp_status(self, server_id: str, state: str):
    icon = {"connected": "●", "connecting": "◐", 
            "disconnected": "○", "error": "✗"}[state]
    color = {"connected": "#0f0", "connecting": "#ff0",
             "disconnected": "#666", "error": "#f00"}[state]
    self.mcp_status_label.setText(f"MCP: {icon} {server_id}")
    self.mcp_status_label.setStyleSheet(f"color: {color};")
```

### Decision 7: Subprocess CREATE_NO_WINDOW on Windows

**Choice:** Rely on existing `main.py` global Popen patch.

**Rationale:**
- MCP SDK uses `subprocess.Popen` to launch stdio servers
- MARK LII already patches `subprocess.Popen` to add `CREATE_NO_WINDOW` globally
- No changes needed to MCP SDK or MCPManager

**Verification:** Test that PyMCP-FS subprocess does not open console window.

### Decision 8: Tool Execution in Executor

**Choice:** Run `mcp_manager.execute_tool()` in executor like other actions.

**Rationale:**
- Consistent with existing action pattern in `_execute_tool()`
- Avoids blocking event loop during MCP call
- MCP SDK methods are already async-safe

**Implementation:**
```python
elif name.startswith(tuple(self._mcp_manager.get_server_prefixes())):
    r = await loop.run_in_executor(
        None,
        lambda: asyncio.run(self._mcp_manager.execute_tool(name, args))
    )
    result = r or "Done."
```

**Note:** Executor wraps async call with `asyncio.run` since executor expects sync callables.

## Risks / Trade-offs

**[Risk]** MCP server crashes repeatedly → **Mitigation:** Exponential backoff on reconnection attempts, max 3 retries before marking as failed

**[Risk]** Schema conversion fails on edge case types (e.g., `anyOf`, `allOf`) → **Mitigation:** Log warning, skip that tool, continue with others. Document unsupported schemas.

**[Risk]** Large file reads block UI → **Mitigation:** Already handled by run_in_executor. Consider adding size limit warning in tool description.

**[Trade-off]** Config changes require restart → **Acceptable:** Mirrors plugin system, infrequent operation

**[Trade-off]** Single process per server (no pooling) → **Acceptable:** Stdio transport is 1:1, MCP servers are lightweight

**[Trade-off]** No server discovery UI → **Acceptable:** Expert users edit JSON, future enhancement possible

## Migration Plan

**Phase 1: Setup**
1. User clones PyMCP-FS repo locally
2. User creates `config/mcp_servers.json` with PyMCP-FS entry (path to `main.py`)
3. Add `mcp>=1.0.0` to `requirements.txt` and install

**Phase 2: Implementation**
1. Implement `core/mcp_manager.py` (MCPManager + MCPServerConnection)
2. Modify `main.py` to integrate MCPManager
3. Modify `ui.py` to add status indicator
4. Test with PyMCP-FS operations

**Phase 3: Validation**
1. Verify all 10 PyMCP-FS tools are callable
2. Test error handling (invalid paths, disconnection)
3. Test UI status updates
4. Test coexistence with file_controller

**Rollback:** Remove MCPManager initialization from main.py, tools disappear but no breaking changes.

## Open Questions

**Q:** Should we add a `/mcp` command to list available tools and server status?
**Defer:** Not in MVP scope. Can be added after validating core integration works.

**Q:** How to handle MCP servers that require authentication or environment variables?
**Defer:** PyMCP-FS doesn't need auth. Address when adding first authenticated server (e.g., GitHub).

**Q:** Should failed server connection block MARK LII startup?
**Defer:** Current design logs error and continues. Can make configurable later if needed.
