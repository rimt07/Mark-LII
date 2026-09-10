"""
Audit MARK LII tools with Ollama backend.

Layers:
  1. Schema  — every declaration converts to Ollama format
  2. Execute — safe/read-only tools run through main._execute_tool
  3. Route   — hermes3 picks the right tool for typical user prompts
"""
from __future__ import annotations

import asyncio
import json
import sys
import types as pytypes
from dataclasses import dataclass, field
from pathlib import Path

import ollama

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.ollama_backend import OllamaBackend
from main import TOOL_DECLARATIONS, JarvisLive, _load_llm_config


# ── Minimal UI mock (avoids launching PyQt) ──────────────────────────────────

class _MockUI:
    muted = True
    current_file = None

    def set_state(self, state: str) -> None:
        pass

    def write_log(self, text: str) -> None:
        pass

    def show_content(self, label: str, body: str) -> None:
        pass

    def start_camera_stream(self) -> None:
        pass

    def stop_camera_stream(self) -> None:
        pass

    def update_mcp_status(self, *a, **k) -> None:
        pass


# ── Safe direct-execution probes ───────────────────────────────────────────

@dataclass
class ExecProbe:
    tool: str
    args: dict
    note: str = ""


EXEC_PROBES: list[ExecProbe] = [
    ExecProbe("save_memory", {"category": "identity", "key": "audit_test", "value": "ok"}),
    ExecProbe("recall_memory", {"query": "audit_test"}),
    ExecProbe("recall_memory", {"query": ""}, note="list all"),
    ExecProbe("undo", {"action": "list"}),
    ExecProbe("system_status", {}),
    ExecProbe("manage_monitor", {"action": "list"}),
    ExecProbe("file_controller", {"action": "list", "path": "desktop"}),
    ExecProbe("file_controller", {"action": "disk_usage", "path": "home"}),
    ExecProbe("close_camera", {}),
    ExecProbe("weather_report", {"city": "Madrid"}),
]


# ── LLM routing probes (one prompt per core tool) ────────────────────────────

@dataclass
class RouteProbe:
    label: str
    expected_tool: str
    user_msg: str
    tools_subset: list[str] | None = None  # None = single tool only


ROUTE_PROBES: list[RouteProbe] = [
    RouteProbe("open_app", "open_app", "Abre el bloc de notas"),
    RouteProbe("web_search", "web_search", "Busca en internet quién ganó el mundial 2022"),
    RouteProbe("system_status", "system_status", "¿Cómo va el rendimiento de mi PC? CPU y RAM"),
    RouteProbe("weather_report", "weather_report", "¿Qué tiempo hace en Barcelona?"),
    RouteProbe("send_message", "send_message", "Envía un WhatsApp a Juan diciendo que llego tarde"),
    RouteProbe("reminder", "reminder", "Recuérdame mañana a las 9 que tengo reunión"),
    RouteProbe("youtube_video", "youtube_video", "Pon un video de lo-fi en YouTube"),
    RouteProbe("screen_process", "screen_process", "Mira mi pantalla y dime qué aplicaciones tengo abiertas"),
    RouteProbe("close_camera", "close_camera", "Cierra la cámara"),
    RouteProbe("computer_settings", "computer_settings", "Sube el volumen del sistema"),
    RouteProbe("browser_control", "browser_control", "Abre google.com en Chrome"),
    RouteProbe("file_controller", "file_controller", "Lista los archivos de mi escritorio"),
    RouteProbe("desktop_control", "desktop_control", "Muéstrame estadísticas de mi escritorio"),
    RouteProbe("code_helper", "code_helper", "Escribe un script Python que imprima hola"),
    RouteProbe("dev_agent", "dev_agent", "Crea un proyecto Flask mínimo con una ruta /health"),
    RouteProbe("computer_control", "computer_control", "Haz una captura de pantalla"),
    RouteProbe("game_updater", "game_updater", "Lista mis juegos instalados en Steam"),
    RouteProbe("flight_finder", "flight_finder", "Busca vuelos de Madrid a París el 15 de octubre"),
    RouteProbe("manage_monitor", "manage_monitor", "Empieza a vigilar noticias de inteligencia artificial"),
    RouteProbe("file_processor", "file_processor", "Resume el archivo que subí"),
    RouteProbe("save_memory", "save_memory", "Me llamo Ana, recuerda mi nombre"),
    RouteProbe("recall_memory", "recall_memory", "¿Qué recuerdas sobre mí?"),
    RouteProbe("undo", "undo", "Deshaz el último cambio que hiciste"),
    RouteProbe("shutdown_jarvis", "shutdown_jarvis", "Cierra JARVIS, adiós"),
]


@dataclass
class AuditReport:
    schema_ok: list[str] = field(default_factory=list)
    schema_fail: list[str] = field(default_factory=list)
    exec_ok: list[str] = field(default_factory=list)
    exec_fail: dict[str, str] = field(default_factory=dict)
    route_ok: list[str] = field(default_factory=list)
    route_miss: dict[str, str] = field(default_factory=dict)
    route_error: dict[str, str] = field(default_factory=dict)


def audit_schema(tools: list[dict]) -> tuple[list[str], list[str]]:
    converted = OllamaBackend._convert_tools_for_ollama(tools)
    conv_names = {c["function"]["name"] for c in converted}
    src_names = {t["name"] for t in tools}
    ok = sorted(conv_names)
    fail = sorted(src_names - conv_names)
    return ok, fail


async def audit_execute(jarvis: JarvisLive) -> tuple[list[str], dict[str, str]]:
    ok: list[str] = []
    fail: dict[str, str] = {}

    for probe in EXEC_PROBES:
        key = probe.tool + (f" ({probe.note})" if probe.note else "")
        try:
            fc = OllamaBackend._FnCall(probe.tool, probe.args, f"audit-{probe.tool}")
            resp = await jarvis._execute_tool(fc)
            text = OllamaBackend._extract_result_text(resp)
            if not text or text.startswith("Herramienta desconocida"):
                fail[key] = text or "empty result"
            elif text.startswith("La herramienta"):
                fail[key] = text[:200]
            else:
                ok.append(key)
        except Exception as e:
            fail[key] = str(e)
    return ok, fail


async def _ollama_route(
    model: str,
    user_msg: str,
    tools_raw: list[dict],
) -> tuple[list[str], str]:
    tools = OllamaBackend._convert_tools_for_ollama(tools_raw)
    prompt = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")[:4000]
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]
    resp = await ollama.AsyncClient().chat(model=model, messages=messages, tools=tools)
    msg = resp.get("message", {})
    names: list[str] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") if isinstance(tc, dict) else tc.function
        name = fn.get("name") if isinstance(fn, dict) else fn.name
        names.append(name)
    content = (msg.get("content") or "")[:120]
    return names, content


async def audit_routes(model: str) -> tuple[list[str], dict[str, str], dict[str, str]]:
    ok: list[str] = []
    miss: dict[str, str] = {}
    err: dict[str, str] = {}

    for probe in ROUTE_PROBES:
        if probe.tools_subset:
            subset = [t for t in TOOL_DECLARATIONS if t["name"] in probe.tools_subset]
        else:
            subset = [t for t in TOOL_DECLARATIONS if t["name"] == probe.expected_tool]
        try:
            names, content = await _ollama_route(model, probe.user_msg, subset)
            if probe.expected_tool in names:
                ok.append(probe.label)
            elif names:
                miss[probe.label] = f"got {names}, expected {probe.expected_tool}"
            else:
                miss[probe.label] = f"no tool call; text={content!r}"
        except Exception as e:
            err[probe.label] = str(e)
    return ok, miss, err


def print_report(report: AuditReport, total_tools: int) -> None:
    print("\n" + "=" * 60)
    print("OLLAMA TOOL AUDIT SUMMARY")
    print("=" * 60)

    print(f"\n[1] SCHEMA ({len(report.schema_ok)}/{total_tools} converted)")
    if report.schema_fail:
        print("  FAIL:", ", ".join(report.schema_fail))
    else:
        print("  All declarations converted OK")

    print(f"\n[2] DIRECT EXECUTION ({len(report.exec_ok)}/{len(EXEC_PROBES)} passed)")
    for name in report.exec_ok:
        print(f"  OK  {name}")
    for name, reason in report.exec_fail.items():
        print(f"  FAIL {name}: {reason[:160]}")

    print(f"\n[3] LLM ROUTING hermes3 ({len(report.route_ok)}/{len(ROUTE_PROBES)} matched)")
    for name in report.route_ok:
        print(f"  OK  {name}")
    for name, reason in report.route_miss.items():
        print(f"  MISS {name}: {reason}")
    for name, reason in report.route_error.items():
        print(f"  ERR  {name}: {reason}")


async def main() -> None:
    cfg = _load_llm_config()
    model = cfg.get("ollama", {}).get("model", "hermes3:8b")
    print(f"Model: {model}")
    print(f"Core tools: {len(TOOL_DECLARATIONS)}")

    report = AuditReport()
    report.schema_ok, report.schema_fail = audit_schema(TOOL_DECLARATIONS)
    print(f"Schema: {len(report.schema_ok)} OK, {len(report.schema_fail)} failed")

    print("\nDirect execution probes...")
    ui = _MockUI()
    jarvis = JarvisLive(ui)
    jarvis._backend_type = "ollama"
    report.exec_ok, report.exec_fail = await audit_execute(jarvis)

    print(f"\nLLM routing probes ({len(ROUTE_PROBES)} prompts, may take several minutes)...")
    report.route_ok, report.route_miss, report.route_error = await audit_routes(model)

    print_report(report, len(TOOL_DECLARATIONS))

    out = ROOT / "_audit_ollama_results.json"
    out.write_text(
        json.dumps(
            {
                "model": model,
                "schema_ok": report.schema_ok,
                "schema_fail": report.schema_fail,
                "exec_ok": report.exec_ok,
                "exec_fail": report.exec_fail,
                "route_ok": report.route_ok,
                "route_miss": report.route_miss,
                "route_error": report.route_error,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nFull results → {out.name}")


if __name__ == "__main__":
    asyncio.run(main())
