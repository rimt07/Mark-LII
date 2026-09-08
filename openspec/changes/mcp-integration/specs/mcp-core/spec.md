## Purpose

Provides core MCP (Model Context Protocol) client integration allowing MARK LII to connect to external MCP servers, discover their tools, convert schemas, and route tool calls.

## ADDED Requirements

### Requirement: Server Connection Management
The system SHALL connect to configured MCP servers via stdio transport and maintain persistent connections throughout the session.

#### Scenario: Server startup connection
- **WHEN** MARK LII starts and an MCP server is enabled in configuration
- **THEN** the system launches the server subprocess and establishes an MCP client connection

#### Scenario: Server reconnection on failure
- **WHEN** an MCP server connection is lost during operation
- **THEN** the system attempts to reconnect automatically without user intervention

#### Scenario: Clean shutdown
- **WHEN** MARK LII exits
- **THEN** the system closes all MCP server connections cleanly before terminating

### Requirement: Tool Discovery
The system SHALL discover all available tools from connected MCP servers at connection time.

#### Scenario: List tools from server
- **WHEN** an MCP server connection is established
- **THEN** the system calls `list_tools()` to retrieve all available tool definitions

#### Scenario: Tool metadata extraction
- **WHEN** tools are discovered from an MCP server
- **THEN** the system SHALL capture each tool's name, description, and input schema

### Requirement: Schema Conversion
The system SHALL convert MCP tool schemas (JSON Schema format) to Gemini function declarations.

#### Scenario: Type mapping conversion
- **WHEN** converting an MCP tool schema with JSON Schema types
- **THEN** the system maps `"string"` → `"STRING"`, `"integer"` → `"INTEGER"`, `"number"` → `"NUMBER"`, `"boolean"` → `"BOOLEAN"`, `"array"` → `"ARRAY"`, `"object"` → `"OBJECT"`

#### Scenario: Required fields preservation
- **WHEN** an MCP tool schema specifies required parameters
- **THEN** the converted Gemini function declaration includes the same required fields

#### Scenario: Description preservation
- **WHEN** an MCP tool schema includes parameter descriptions
- **THEN** the converted Gemini function declaration preserves all descriptions verbatim

### Requirement: Tool Namespace
The system SHALL prefix all MCP tools with a namespace pattern `{server_id}_{tool_name}` to avoid collisions with built-in actions.

#### Scenario: Namespace application
- **WHEN** registering tool "read_file" from server "fs"
- **THEN** the Gemini function name is "fs_read_file"

#### Scenario: No collision with built-in actions
- **WHEN** an MCP tool name would collide with an existing action or plugin
- **THEN** the namespaced version prevents the collision automatically

### Requirement: Tool Execution Routing
The system SHALL route tool calls with server namespace prefixes to the appropriate MCP server.

#### Scenario: Route to correct server
- **WHEN** Gemini calls tool "fs_read_file" with parameters
- **THEN** the system extracts server_id "fs", strips prefix, and calls "read_file" on that server's MCP client

#### Scenario: Pass parameters unchanged
- **WHEN** routing a tool call to an MCP server
- **THEN** the system passes the parameter dictionary to the MCP SDK's `call_tool()` method without modification

#### Scenario: Handle MCP errors
- **WHEN** an MCP tool call returns with `is_error=True`
- **THEN** the system extracts the error message and returns it as a natural language response to Gemini

#### Scenario: Extract result content
- **WHEN** an MCP tool call succeeds
- **THEN** the system extracts text content from result blocks and returns it as the function response

### Requirement: Server Configuration
The system SHALL load MCP server configurations from `config/mcp_servers.json` at startup.

#### Scenario: Load server definitions
- **WHEN** reading configuration file
- **THEN** the system parses server ID, name, command, arguments, and enabled state for each server

#### Scenario: Respect enabled flag
- **WHEN** a server's `enabled` field is `false` in configuration
- **THEN** the system does not launch or connect to that server

#### Scenario: Missing configuration file
- **WHEN** `config/mcp_servers.json` does not exist
- **THEN** the system operates normally without MCP servers and logs the absence

### Requirement: Async Execution
The system SHALL execute all MCP operations asynchronously to avoid blocking the main event loop.

#### Scenario: Non-blocking tool calls
- **WHEN** executing an MCP tool call
- **THEN** the system uses `await` and does not block the audio streaming or UI updates

#### Scenario: Concurrent tool calls
- **WHEN** multiple MCP tool calls are queued
- **THEN** the system processes them asynchronously without serialization bottlenecks
