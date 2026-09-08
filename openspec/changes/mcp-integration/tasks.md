## 1. Setup and Configuration

- [x] 1.1 Add `mcp>=1.0.0` to requirements.txt
- [x] 1.2 Create `config/mcp_servers.json` with PyMCP-FS configuration
- [x] 1.3 Document PyMCP-FS setup instructions in README or setup comments

## 2. Core MCP Manager Implementation

- [x] 2.1 Create `core/mcp_manager.py` module file
- [x] 2.2 Implement `MCPServerConnection` class with connect/disconnect/call_tool methods
- [x] 2.3 Implement async context manager workaround for persistent connections
- [x] 2.4 Implement `MCPManager` class with initialize/get_all_tools/execute_tool/shutdown methods
- [x] 2.5 Implement schema conversion function `convert_mcp_schema_to_gemini()`
- [x] 2.6 Implement tool namespace generation `{server_id}_{tool_name}`
- [x] 2.7 Add error handling for MCP tool calls (check `result.is_error`)
- [x] 2.8 Add logging for server connection lifecycle events

## 3. Configuration Loading

- [x] 3.1 Implement config file loader in `MCPManager.initialize()`
- [x] 3.2 Parse server definitions (id, name, command, args, enabled)
- [x] 3.3 Handle missing config file gracefully (log and continue without MCP)
- [x] 3.4 Validate configuration schema before attempting connections

## 4. Server Lifecycle Management

- [x] 4.1 Implement subprocess launch with stdio transport
- [x] 4.2 Verify CREATE_NO_WINDOW flag is applied on Windows
- [x] 4.3 Implement tool discovery via `client.list_tools()`
- [x] 4.4 Store tool schemas for runtime access
- [x] 4.5 Implement reconnection logic with exponential backoff (max 3 retries)
- [x] 4.6 Implement clean shutdown in `MCPManager.shutdown()`

## 5. Integration with main.py

- [x] 5.1 Import `MCPManager` in main.py
- [x] 5.2 Initialize `self._mcp_manager` in `JarvisLive.__init__()`
- [x] 5.3 Call `await self._mcp_manager.initialize()` during startup
- [x] 5.4 Add MCP tools to `_build_tools()` via `mcp_manager.get_all_tools()`
- [x] 5.5 Add routing in `_execute_tool()` for tools with server namespace prefix
- [x] 5.6 Wrap MCP execution in `run_in_executor` with `asyncio.run()`
- [x] 5.7 Call `await self._mcp_manager.shutdown()` in cleanup

## 6. UI Status Indicator

- [x] 6.1 Add `QLabel` for MCP status in `ui.py` bottom layout
- [x] 6.2 Implement `update_mcp_status(server_id, state)` method
- [x] 6.3 Apply color styling for each state (green/yellow/gray/red)
- [x] 6.4 Set tooltip with detailed server information on hover
- [x] 6.5 Trigger status updates from MCPManager connection events
- [x] 6.6 Handle multiple servers display (e.g., "● fs ○ db")

## 7. PyMCP-FS Integration

- [x] 7.1 Configure PyMCP-FS with allowed directory `D:/Programacion/ia/Mark-LII`
- [ ] 7.2 Verify all 10 tools are discovered and registered (read_file, write_file, edit_file, etc.)
- [ ] 7.3 Test tool namespace generation (fs_read_file, fs_write_file, etc.)
- [ ] 7.4 Verify path resolution works for relative paths ("main.py")
- [ ] 7.5 Verify security boundary enforcement (paths outside allowed directory rejected)

## 8. Testing and Validation

- [ ] 8.1 Test reading a file: "JARVIS, read main.py"
- [ ] 8.2 Test writing a file: "JARVIS, create test.txt with content 'hello'"
- [ ] 8.3 Test listing directory: "JARVIS, list files in plugins/"
- [ ] 8.4 Test searching files: "JARVIS, find all Python files mentioning memory_manager"
- [ ] 8.5 Test directory tree: "JARVIS, show me the structure of plugins directory"
- [ ] 8.6 Test error handling: request file outside allowed directory
- [ ] 8.7 Test error handling: request non-existent file
- [ ] 8.8 Test coexistence: verify file_controller still works independently
- [ ] 8.9 Test UI indicator shows correct state (connected/error/disconnected)
- [ ] 8.10 Test server reconnection after simulated connection loss

## 9. Documentation and Cleanup

- [ ] 9.1 Add inline code comments explaining MCP integration points
- [ ] 9.2 Document config file format in comments or README
- [ ] 9.3 Add error messages that help users debug connection issues
- [ ] 9.4 Verify no console windows appear on Windows during server launch
- [ ] 9.5 Clean up any debug logging before final commit
