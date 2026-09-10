"""How often does llama3.2 call save_memory vs just talking?"""
import asyncio
from pathlib import Path

import ollama

from core.ollama_backend import OllamaBackend
from main import TOOL_DECLARATIONS


async def once(i: int) -> str:
    tools = OllamaBackend._convert_tools_for_ollama(
        [t for t in TOOL_DECLARATIONS if t["name"] == "save_memory"]
    )
    prompt = Path("core/prompt.txt").read_text(encoding="utf-8")[:3000]
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Me llamo Laura, tengo 28 años y vivo en Madrid. Recuerda todo eso."},
    ]
    resp = await ollama.AsyncClient().chat(
        model="llama3.2:latest", messages=messages, tools=tools
    )
    msg = resp.get("message", {})
    tcs = msg.get("tool_calls") or []
    if tcs:
        names = []
        for tc in tcs:
            fn = tc.get("function") if isinstance(tc, dict) else tc.function
            names.append(fn.get("name") if isinstance(fn, dict) else fn.name)
        return f"call:{','.join(names)}"
    return f"text:{(msg.get('content') or '')[:60]!r}"


async def main() -> None:
    results = []
    for i in range(3):
        r = await once(i)
        results.append(r)
        print(i, r)
    print("summary:", results)


if __name__ == "__main__":
    asyncio.run(main())
