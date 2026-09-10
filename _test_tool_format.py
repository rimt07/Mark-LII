"""Compare Ollama tool result message: tool_name vs name."""
import asyncio
import ollama
from main import TOOL_DECLARATIONS
from core.ollama_backend import OllamaBackend


async def roundtrip(use_tool_name: bool) -> None:
    tools = OllamaBackend._convert_tools_for_ollama(
        [t for t in TOOL_DECLARATIONS if t["name"] == "save_memory"]
    )
    messages = [
        {
            "role": "system",
            "content": "You are JARVIS. After saving memory, confirm briefly in Spanish.",
        },
        {"role": "user", "content": "Me llamo Carlos. Recuérdalo."},
    ]
    client = ollama.AsyncClient()
    r1 = await client.chat(model="llama3.2:latest", messages=messages, tools=tools)
    msg = r1["message"]
    print("round1 tool_calls:", bool(msg.get("tool_calls")))
    messages.append({
        "role": "assistant",
        "content": msg.get("content") or "",
        "tool_calls": msg.get("tool_calls"),
    })
    tc = msg["tool_calls"][0]
    fn = tc["function"] if isinstance(tc, dict) else tc.function
    name = fn["name"] if isinstance(fn, dict) else fn.name
    tool_msg = {"role": "tool", "content": "ok"}
    if use_tool_name:
        tool_msg["tool_name"] = name
    else:
        tool_msg["name"] = name
    messages.append(tool_msg)
    r2 = await client.chat(model="llama3.2:latest", messages=messages, tools=tools)
    m2 = r2["message"]
    label = "tool_name" if use_tool_name else "name"
    print(f"format={label}: content={m2.get('content', '')[:120]!r}")


async def main():
    print("=== With tool_name (Ollama spec) ===")
    await roundtrip(True)
    print("=== With name (current app code) ===")
    await roundtrip(False)


if __name__ == "__main__":
    asyncio.run(main())
