"""Quick JARVIS tool probe with hermes3:8b."""
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
    t0 = asyncio.get_event_loop().time()
    resp = await ollama.AsyncClient().chat(
        model="hermes3:8b", messages=messages, tools=tools
    )
    elapsed = asyncio.get_event_loop().time() - t0
    msg = resp.get("message", {})
    tcs = msg.get("tool_calls") or []
    names = []
    args_list = []
    for tc in tcs:
        fn = tc.get("function") if isinstance(tc, dict) else tc.function
        name = fn.get("name") if isinstance(fn, dict) else fn.name
        args = fn.get("arguments") if isinstance(fn, dict) else fn.arguments
        names.append(name)
        args_list.append(args)
    content = (msg.get("content") or "")[:80]
    print(f"[{label}] {elapsed:.1f}s tools={len(tools)} called={names or 'NONE'}")
    for n, a in zip(names, args_list):
        print(f"  -> {n}: {a}")
    if not names:
        print(f"  text: {content!r}")


async def main() -> None:
    mem = [t for t in TOOL_DECLARATIONS if t["name"] in ("save_memory", "recall_memory")]
    fc = [t for t in TOOL_DECLARATIONS if t["name"] == "file_controller"]
    await probe(
        "memoria",
        mem,
        "Me llamo Pedro, tengo 30 años y vivo en Madrid. Recuerda todo eso.",
    )
    await probe(
        "crear archivo",
        fc,
        "Crea un archivo de texto llamado prueba_hermes.txt en el escritorio con el contenido hola desde hermes",
    )
    await probe(
        "memoria+24 tools",
        TOOL_DECLARATIONS,
        "Me llamo Pedro, tengo 30 años y vivo en Madrid. Recuerda todo eso.",
    )


if __name__ == "__main__":
    asyncio.run(main())
