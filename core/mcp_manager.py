"""
MCP (Model Context Protocol) Server Manager

Manages lifecycle of MCP servers, tool discovery, schema conversion, and routing.
Connects to external MCP servers via stdio transport to expose their tools to Gemini.
"""
import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Optional, Dict, List, Any
import time


class MCPServerConnection:
    """
    Wraps a single MCP server connection with subprocess management.
    Handles connect/disconnect lifecycle and tool execution.
    """

    def __init__(self, server_id: str, config: dict, logger=print):
        self.server_id = server_id
        self.config = config
        self.logger = logger

        self._client = None
        self._context = None
        self._tools = []
        self._connected = False
        self._retry_count = 0
        self._max_retries = 3

    async def connect(self) -> bool:
        """
        Launch MCP server subprocess and establish client connection.
        Returns True if successful, False otherwise.
        """
        try:
            # Lazy import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            self.logger(f"[MCP] Connecting to server '{self.server_id}'...")

            # CRITICAL FIX: Get REAL system streams before subprocess launch
            # Even if sys.stdout/stderr were temporarily restored, subprocess might
            # have already inherited redirected descriptors. We must get the
            # ORIGINAL file descriptors before any redirection happened.
            import os
            original_stdout = None
            original_stderr = None

            # Try to get original streams from ConsoleRedirector if present
            if hasattr(sys.stdout, 'original') and sys.stdout.original:
                original_stdout = sys.stdout.original
            else:
                original_stdout = sys.stdout

            if hasattr(sys.stderr, 'original') and sys.stderr.original:
                original_stderr = sys.stderr.original
            else:
                original_stderr = sys.stderr

            # Build server parameters from config
            server_params = StdioServerParameters(
                command=self.config["command"],
                args=self.config.get("args", []),
                env=self.config.get("env", None)
            )

            # Temporarily set sys streams to originals during subprocess creation
            saved_stdout = sys.stdout
            saved_stderr = sys.stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr

            try:
                # Create stdio client context (subprocess + MCP client)
                self._context = stdio_client(server_params)

                # Enter context manager to get read/write streams
                # This launches the subprocess which NOW inherits correct stdout/stderr
                read_stream, write_stream = await asyncio.wait_for(
                    self._context.__aenter__(),
                    timeout=10.0  # 10 second timeout for subprocess launch
                )
            finally:
                # Restore redirected streams immediately
                sys.stdout = saved_stdout
                sys.stderr = saved_stderr

            # Create MCP client session with the streams
            self._client = ClientSession(read_stream, write_stream)

            # Initialize the session (handshake with server) with timeout
            await asyncio.wait_for(
                self._client.__aenter__(),
                timeout=5.0  # 5 second timeout for handshake
            )

            # Discover available tools
            await self._discover_tools()

            self._connected = True
            self._retry_count = 0
            self.logger(f"[MCP] Connected to '{self.server_id}' - {len(self._tools)} tools available")
            return True

        except asyncio.TimeoutError:
            self.logger(f"[MCP] Connection to '{self.server_id}' timed out")
            self._connected = False
            return False
        except Exception as e:
            self.logger(f"[MCP] Failed to connect to '{self.server_id}': {e}")
            self.logger(f"[MCP] Exception type: {type(e).__name__}")
            traceback.print_exc()
            self._connected = False
            return False

    async def _discover_tools(self):
        """Discover tools from connected server via list_tools()"""
        if not self._client:
            self.logger(f"[MCP] No client available for tool discovery")
            return

        try:
            self.logger(f"[MCP] Requesting tools from '{self.server_id}'...")
            # Add timeout to prevent hanging indefinitely
            result = await asyncio.wait_for(
                self._client.list_tools(),
                timeout=5.0  # 5 second timeout
            )
            self._tools = result.tools if result else []
            self.logger(f"[MCP] Discovered {len(self._tools)} tools from '{self.server_id}'")
        except asyncio.TimeoutError:
            self.logger(f"[MCP] Tool discovery timed out for '{self.server_id}' - server not responding")
            self._tools = []
        except Exception as e:
            self.logger(f"[MCP] Tool discovery failed for '{self.server_id}': {e}")
            self.logger(f"[MCP] Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            self._tools = []

    async def disconnect(self):
        """Clean shutdown of MCP client and subprocess"""
        if not self._connected:
            return

        try:
            self.logger(f"[MCP] Disconnecting from '{self.server_id}'...")

            # Exit client session
            if self._client:
                await self._client.__aexit__(None, None, None)
                self._client = None

            # Exit stdio context (kills subprocess)
            if self._context:
                await self._context.__aexit__(None, None, None)
                self._context = None

            self._connected = False
            self.logger(f"[MCP] Disconnected from '{self.server_id}'")
        except Exception as e:
            self.logger(f"[MCP] Error during disconnect from '{self.server_id}': {e}")

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect with exponential backoff.
        Returns True if reconnection succeeded, False if max retries exceeded.
        """
        if self._retry_count >= self._max_retries:
            self.logger(f"[MCP] Max retries ({self._max_retries}) exceeded for '{self.server_id}'")
            return False

        self._retry_count += 1
        wait_time = min(2 ** self._retry_count, 30)  # Exponential backoff, max 30s

        self.logger(f"[MCP] Reconnecting to '{self.server_id}' (attempt {self._retry_count}/{self._max_retries}) in {wait_time}s...")
        await asyncio.sleep(wait_time)

        await self.disconnect()  # Clean up any partial state
        return await self.connect()

    async def call_tool(self, tool_name: str, parameters: dict) -> dict:
        """
        Call a tool on this MCP server.
        Returns dict with 'success', 'result', and optional 'error' keys.
        """
        if not self._connected or not self._client:
            return {
                "success": False,
                "error": f"Server '{self.server_id}' is not connected"
            }

        try:
            self.logger(f"[MCP] Calling {self.server_id}::{tool_name} with {parameters}")

            result = await self._client.call_tool(tool_name, parameters)

            # Check if tool call returned an error
            if result.isError:
                return {
                    "success": False,
                    "error": f"Tool error: {getattr(result, 'error', 'Unknown error')}"
                }

            # Extract text content from result
            content_text = ""
            if hasattr(result, 'content') and result.content:
                for block in result.content:
                    if hasattr(block, 'text'):
                        content_text += block.text

            return {
                "success": True,
                "result": content_text or str(result)
            }

        except Exception as e:
            self.logger(f"[MCP] Tool call failed on '{self.server_id}': {e}")
            traceback.print_exc()
            return {
                "success": False,
                "error": f"Tool call exception: {e}"
            }

    def get_tools(self) -> List[Any]:
        """Return list of discovered tool objects"""
        return self._tools if self._connected else []

    def is_connected(self) -> bool:
        """Check if server is currently connected"""
        return self._connected


class MCPManager:
    """
    Manages multiple MCP server connections and provides unified tool interface.
    Handles configuration loading, tool discovery, schema conversion, and routing.
    """

    def __init__(self, config_path: Path, logger=print, status_callback=None):
        self.config_path = config_path
        self.logger = logger
        self.status_callback = status_callback  # callable: (dict[server_id->status]) -> None
        self.servers: Dict[str, MCPServerConnection] = {}
        self._initialized = False

    async def initialize(self):
        """
        Load configuration and connect to enabled MCP servers.
        Gracefully handles missing config file (logs and continues).
        """
        if self._initialized:
            return

        self.logger("[MCP] Initializing MCP Manager...")

        # Load configuration
        if not self.config_path.exists():
            self.logger("[MCP] No mcp_servers.json found - MCP integration disabled")
            self._initialized = True
            return

        try:
            config_data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.logger(f"[MCP] Failed to parse mcp_servers.json: {e}")
            self._initialized = True
            return

        # Validate configuration schema
        if not self._validate_config(config_data):
            self.logger("[MCP] Invalid configuration schema - skipping MCP initialization")
            self._initialized = True
            return

        # Connect to enabled servers
        servers_config = config_data.get("servers", {})
        for server_id, server_config in servers_config.items():
            if not server_config.get("enabled", True):
                self.logger(f"[MCP] Server '{server_id}' is disabled in config")
                continue

            # Create server connection
            conn = MCPServerConnection(server_id, server_config, logger=self.logger)
            self.servers[server_id] = conn

            # Attempt initial connection
            success = await conn.connect()
            if not success and server_config.get("restart_on_failure", False):
                # Try reconnection with backoff
                await conn.reconnect()

        self._initialized = True
        self.logger(f"[MCP] Initialization complete - {len(self.servers)} server(s) configured")

        # Notify UI of initial status
        self._update_status()

    def _validate_config(self, config: dict) -> bool:
        """Basic validation of configuration schema"""
        if not isinstance(config, dict):
            return False

        servers = config.get("servers", {})
        if not isinstance(servers, dict):
            return False

        # Validate each server config
        for server_id, server_config in servers.items():
            if not isinstance(server_config, dict):
                return False
            if "command" not in server_config:
                self.logger(f"[MCP] Server '{server_id}' missing required 'command' field")
                return False

        return True

    async def get_all_tools(self) -> List[dict]:
        """
        Get Gemini function declarations for all tools from all connected servers.
        Applies namespace pattern {server_id}_{tool_name} to avoid collisions.
        """
        all_tools = []

        for server_id, conn in self.servers.items():
            if not conn.is_connected():
                continue

            for tool in conn.get_tools():
                # Convert MCP tool to Gemini function declaration
                gemini_tool = self._convert_tool_to_gemini(server_id, tool)
                all_tools.append(gemini_tool)

        self.logger(f"[MCP] Providing {len(all_tools)} tools to Gemini")
        return all_tools

    def _convert_tool_to_gemini(self, server_id: str, mcp_tool) -> dict:
        """
        Convert MCP tool definition to Gemini function declaration.
        Applies namespace pattern and converts JSON Schema types.
        """
        # Tool name with namespace: {server_id}_{tool_name}
        namespaced_name = f"{server_id}_{mcp_tool.name}"

        # Convert input schema from JSON Schema to Gemini format
        gemini_params = self._convert_schema_to_gemini(mcp_tool.inputSchema)

        return {
            "name": namespaced_name,
            "description": mcp_tool.description or f"Tool from {server_id} server",
            "parameters": gemini_params
        }

    def _convert_schema_to_gemini(self, mcp_schema: dict) -> dict:
        """
        Recursively convert JSON Schema format to Gemini function parameter format.
        Maps type names: string→STRING, integer→INTEGER, etc.
        """
        TYPE_MAP = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT"
        }

        if not isinstance(mcp_schema, dict):
            return {"type": "OBJECT", "properties": {}}

        schema_type = mcp_schema.get("type", "object")
        gemini_schema = {"type": TYPE_MAP.get(schema_type, "OBJECT")}

        # Preserve properties (recursive conversion)
        if "properties" in mcp_schema:
            gemini_schema["properties"] = {}
            for prop_name, prop_schema in mcp_schema["properties"].items():
                gemini_schema["properties"][prop_name] = self._convert_schema_to_gemini(prop_schema)

        # Preserve required fields
        if "required" in mcp_schema:
            gemini_schema["required"] = mcp_schema["required"]

        # Preserve description
        if "description" in mcp_schema:
            gemini_schema["description"] = mcp_schema["description"]

        # Handle array items
        if "items" in mcp_schema:
            gemini_schema["items"] = self._convert_schema_to_gemini(mcp_schema["items"])

        return gemini_schema

    async def execute_tool(self, namespaced_name: str, parameters: dict) -> str:
        """
        Route tool call to appropriate server based on namespace.
        Parses {server_id}_{tool_name} and routes to that server's MCP client.
        Returns natural language result or error message.
        """
        # Parse namespace: fs_read_file → server_id="fs", tool_name="read_file"
        parts = namespaced_name.split("_", 1)
        if len(parts) != 2:
            return f"Invalid tool name format: {namespaced_name}"

        server_id, tool_name = parts

        # Get server connection
        conn = self.servers.get(server_id)
        if not conn:
            return f"Unknown MCP server: {server_id}"

        if not conn.is_connected():
            # Attempt reconnection
            self.logger(f"[MCP] Server '{server_id}' disconnected, attempting reconnect...")
            success = await conn.reconnect()
            if not success:
                return f"Sir, the {server_id} server is not connected and reconnection failed."

        # Call tool via MCP
        result = await conn.call_tool(tool_name, parameters)

        if result["success"]:
            return result["result"]
        else:
            return f"Sir, the tool failed: {result['error']}"

    async def shutdown(self):
        """Cleanly disconnect from all MCP servers"""
        self.logger("[MCP] Shutting down MCP Manager...")

        for server_id, conn in self.servers.items():
            await conn.disconnect()

        self.servers.clear()
        self.logger("[MCP] MCP Manager shutdown complete")

    def get_server_prefixes(self) -> List[str]:
        """Return list of server ID prefixes for routing detection"""
        return [f"{sid}_" for sid in self.servers.keys()]

    def get_server_status(self) -> Dict[str, str]:
        """
        Get connection status for all servers.
        Returns dict of server_id → status ("connected", "disconnected", "error")
        """
        status = {}
        for server_id, conn in self.servers.items():
            if conn.is_connected():
                status[server_id] = "connected"
            else:
                status[server_id] = "disconnected"
        return status

    def _update_status(self):
        """Notify UI of current server status"""
        if self.status_callback:
            try:
                status = self.get_server_status()
                self.status_callback(status)
            except Exception as e:
                self.logger(f"[MCP] Status callback failed: {e}")
