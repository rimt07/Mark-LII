## Why

MARK LII currently has a fixed set of built-in actions and plugins. To enable extensibility and access to external data sources, we need a standard way to connect to external servers that provide tools and resources. Model Context Protocol (MCP) is the emerging standard for this, allowing AI assistants to connect to filesystem servers, databases, APIs, and more. This change enables JARVIS to leverage MCP servers, starting with filesystem access.

## What Changes

- Add MCP client integration to connect to external MCP servers via stdio transport
- Implement `MCPManager` to handle server lifecycle, tool discovery, and execution
- Convert MCP tool schemas (JSON Schema) to Gemini function declarations
- Register PyMCP-FS as the first MCP server, providing 10 filesystem tools
- Add configuration file `config/mcp_servers.json` for server management
- Implement namespace pattern `{server_id}_{tool_name}` (e.g., `fs_read_file`) to avoid collisions
- Add simple UI status indicator showing MCP server connection state
- Scope PyMCP-FS access to `D:/Programacion/ia/Mark-LII` directory only
- Coexist with existing `file_controller` action - both remain available to Gemini

## Capabilities

### New Capabilities
- `mcp-core`: Core MCP client integration - server lifecycle management, tool discovery, schema conversion, and routing
- `mcp-filesystem`: PyMCP-FS integration - 10 filesystem tools (read, write, edit, list, search, tree, move, info, create_directory, read_multiple_files)
- `mcp-ui-status`: UI status indicator showing connection state of MCP servers

### Modified Capabilities
<!-- No existing capabilities are being modified - this is purely additive -->

## Impact

**New Files:**
- `config/mcp_servers.json` - MCP server configuration
- `core/mcp_manager.py` - MCP lifecycle and routing logic

**Modified Files:**
- `main.py` - Import MCPManager, initialize in `__init__`, add MCP tools to `_build_tools()`, route in `_execute_tool()`
- `ui.py` - Add MCP status indicator (bottom corner), update methods for status display
- `requirements.txt` - Add `mcp>=1.0.0` dependency

**External Dependencies:**
- Python MCP SDK (`mcp` package)
- PyMCP-FS server (separate repo, launched as subprocess)

**No Breaking Changes** - All existing functionality remains intact. MCP tools are additive.
