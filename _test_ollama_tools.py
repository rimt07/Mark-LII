"""Quick probe: does llama3.2 call shell-mcp-server_run_powershell?"""
import asyncio
import json
from pathlib import Path

import ollama

from core.ollama_backend import OllamaBackend
from main import TOOL_DECLARATIONS, _load_system_prompt


async def test():
    # Minimal MCP shell tool (same shape as mcp_manager produces)
    shell_decl = {
        "name": "shell-mcp-server_run_powershell",
        "description": (
            "Executes PowerShell commands. Use when user asks to run terminal/shell commands. "
            "Parameter json is a JSON string, e.g. "
            '[{"command": "Get-ChildItem", "parameters": ["."]}] for ls/dir.'
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "json": {
                    "type": "STRING",
                    "description": "JSON string defining PowerShell command(s)",
                }
            },
            "required": ["json"],
        },
    }

    all_tools = TOOL_DECLARATIONS + [shell_decl]
    ollama_tools = OllamaBackend._convert_tools_for_ollama(all_tools)
    shell_only = OllamaBackend._convert_tools_for_ollama([shell_decl])

    print(f"Total converted tools: {len(ollama_tools)}")

    system = _load_system_prompt()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "corre en la terminal el comando ls"},
    ]

    client = ollama.AsyncClient(host="http://localhost:11434")
    model = "llama3.2:latest"

    resp = await client.chat(model=model, messages=messages, tools=ollama_tools)
    msg = resp.get("message", {})
    print("\n=== ALL TOOLS ===")
    print("content:", (msg.get("content") or "")[:300])
    print("tool_calls:", json.dumps(msg.get("tool_calls"), indent=2, default=str))

    resp2 = await client.chat(model=model, messages=messages, tools=shell_only)
    msg2 = resp2.get("message", {})
    print("\n=== SHELL TOOL ONLY ===")
    print("content:", (msg2.get("content") or "")[:300])
    print("tool_calls:", json.dumps(msg2.get("tool_calls"), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(test())
