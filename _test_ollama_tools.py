"""Quick probe: does llama3.2 call shell-mcp-server_run_powershell?"""
import asyncio
import json
from pathlib import Path

import ollama

from core.ollama_backend import OllamaBackend

SHELL_DECL = {
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


async def test():
    prompt = (Path("core/prompt.txt").read_text(encoding="utf-8"))
    shell_only = OllamaBackend._convert_tools_for_ollama([SHELL_DECL])

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "corre en la terminal el comando ls"},
    ]

    client = ollama.AsyncClient(host="http://localhost:11434")
    model = "llama3.2:latest"

    print("Calling Ollama with shell tool only...")
    resp = await client.chat(model=model, messages=messages, tools=shell_only)
    msg = resp.get("message", {})
    print("content:", (msg.get("content") or "")[:300])
    print("tool_calls:", json.dumps(msg.get("tool_calls"), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(test())
