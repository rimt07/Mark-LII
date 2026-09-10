"""Probe Ollama tool routing for memory and file creation."""
import asyncio
from pathlib import Path

import ollama

from core.ollama_backend import OllamaBackend
from main import TOOL_DECLARATIONS


async def probe(label: str, tools_raw: list, user_msg: str) -> None:
    tools = OllamaBackend._convert_tools_for_ollama(tools_raw)
    prompt = Path("core/prompt.txt").read_text(encoding="utf-8")[:5000]
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]
    resp = await ollama.AsyncClient().chat(
        model="llama3.2:latest", messages=messages, tools=tools
    )
    msg = resp.get("message", {})
    tcs = msg.get("tool_calls") or []
    names = []
    for tc in tcs:
        fn = tc.get("function") if isinstance(tc, dict) else tc.function
        names.append(fn.get("name") if isinstance(fn, dict) else fn.name)
    content = (msg.get("content") or "")[:100]
    print(f"[{label}] tools={len(tools)} called={names or 'NONE'} content={content!r}")


async def main() -> None:
    fc = [t for t in TOOL_DECLARATIONS if t["name"] == "file_controller"]
    mem = [t for t in TOOL_DECLARATIONS if t["name"] in ("save_memory", "recall_memory")]
    await probe(
        "create_file",
        fc,
        "Crea un archivo de texto llamado prueba.txt en el escritorio con el contenido hola mundo",
    )
    await probe(
        "save_memory",
        mem,
        "Me llamo Ana y me gusta el café. Recuérdalo.",
    )
    await probe(
        "all_core_memory",
        TOOL_DECLARATIONS,
        "Me llamo Ana y me gusta el café. Recuérdalo.",
    )


if __name__ == "__main__":
    asyncio.run(main())
