"""Full OllamaBackend turn: save_memory + follow-up speech."""
import asyncio
from pathlib import Path

from core.ollama_backend import OllamaBackend
from main import TOOL_DECLARATIONS
from memory.memory_manager import load_memory, update_memory


class FakeFC:
    def __init__(self, name, args, id):
        self.name = name
        self.args = args
        self.id = id


async def real_executor(fc):
    from google.genai import types

    name = fc.name
    args = dict(fc.args or {})
    print(f"EXECUTE: {name} {args}")
    if name == "save_memory":
        key = args.get("key", "")
        value = args.get("value", "")
        category = args.get("category", "notes")
        if key and value:
            update_memory({category: {key: {"value": value}}})
        return types.FunctionResponse(id=fc.id, name=name, response={"result": "ok", "silent": True})
    return types.FunctionResponse(id=fc.id, name=name, response={"result": "done"})


async def main() -> None:
    mem_before = load_memory()
    print("memory before keys:", list(mem_before.get("identity", {}).keys()))

    logs = []

    def log(m):
        logs.append(m)
        print(m)

    b = OllamaBackend(
        config={
            "base_url": "http://localhost:11434",
            "model": "llama3.2:latest",
            "stream": True,
            "stt": {"debug": True},
            "tts": {"engine": "none"},
        },
        ui_logger=log,
        speak_callback=lambda t: log(f"SPEAK: {t[:120]}"),
    )
    prompt = Path("core/prompt.txt").read_text(encoding="utf-8")
    tools = [t for t in TOOL_DECLARATIONS if t["name"] in ("save_memory", "recall_memory")]
    await b.initialize(system_prompt=prompt, tools=tools, tool_executor=real_executor)
    b.stream_enabled = True
    b.tts_engine = None
    b.messages.append({
        "role": "user",
        "content": "Me llamo Pedro y prefiero español. Recuérdalo para siempre.",
    })
    await b._generate_response()

    mem_after = load_memory()
    print("memory after identity:", mem_after.get("identity", {}))
    print("memory after preferences:", mem_after.get("preferences", {}))
    print("final messages count:", len(b.messages))


if __name__ == "__main__":
    asyncio.run(main())
