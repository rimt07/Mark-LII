"""
Backend-aware text/vision generation for JARVIS tools.

When config/llm_config.json has backend "ollama", generation goes to the local
Ollama model. Otherwise (or on Ollama failure when a Gemini key exists) it uses
Gemini. Action modules should call get_model() / generate_text() /
generate_vision() instead of hard-coding genai.Client.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from typing import Any


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
LLM_CONFIG_PATH = BASE_DIR / "config" / "llm_config.json"
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_ollama_backend() -> bool:
    return (_load_json(LLM_CONFIG_PATH).get("backend") or "gemini").strip().lower() == "ollama"


def _ollama_settings() -> tuple[str, str, float, str | None]:
    cfg = _load_json(LLM_CONFIG_PATH).get("ollama", {}) or {}
    base = (cfg.get("base_url") or "http://localhost:11434").rstrip("/")
    model = cfg.get("model") or "llama3.2:latest"
    temp = float(cfg.get("temperature", 0.7))
    vision = (cfg.get("vision_model") or "").strip() or None
    return base, model, temp, vision


def _gemini_api_key() -> str:
    return (_load_json(API_CONFIG_PATH).get("gemini_api_key") or "").strip()


class _TextResponse:
    """Minimal stand-in for google-genai GenerateContentResponse."""

    def __init__(self, text: str):
        self.text = text or ""
        self.candidates = []


def _contents_to_prompt(contents: Any) -> tuple[str, bytes | None, str]:
    """
    Flatten Gemini-style contents (str | list of str/PIL/bytes/Parts) into
    (prompt_text, image_bytes|None, mime).
    """
    if contents is None:
        return "", None, "image/png"
    if isinstance(contents, str):
        return contents, None, "image/png"

    texts: list[str] = []
    image_bytes: bytes | None = None
    mime = "image/png"

    items = contents if isinstance(contents, (list, tuple)) else [contents]
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            texts.append(item)
            continue
        if isinstance(item, (bytes, bytearray)):
            image_bytes = bytes(item)
            continue
        # PIL Image
        if hasattr(item, "save") and hasattr(item, "size"):
            buf = io.BytesIO()
            fmt = "PNG"
            try:
                item.save(buf, format=fmt)
            except Exception:
                item.convert("RGB").save(buf, format="JPEG")
                fmt = "JPEG"
            image_bytes = buf.getvalue()
            mime = "image/png" if fmt == "PNG" else "image/jpeg"
            continue
        # google.genai types.Part-like
        data = getattr(item, "inline_data", None) or getattr(item, "data", None)
        if data is not None:
            raw = getattr(data, "data", data)
            if isinstance(raw, str):
                try:
                    raw = base64.b64decode(raw)
                except Exception:
                    raw = raw.encode("utf-8", errors="ignore")
            if isinstance(raw, (bytes, bytearray)):
                image_bytes = bytes(raw)
            mt = getattr(data, "mime_type", None) or getattr(item, "mime_type", None)
            if mt:
                mime = mt
            continue
        texts.append(str(item))

    return "\n".join(texts).strip(), image_bytes, mime


def _ollama_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float | None = None,
    timeout: int = 180,
) -> str:
    import requests

    base, default_model, default_temp, _ = _ollama_settings()
    m = model or default_model
    temp = default_temp if temperature is None else temperature
    endpoint = f"{base}/api/chat"
    payload = {
        "model": m,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temp},
    }
    resp = requests.post(endpoint, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("message") or {}
    return (msg.get("content") or "").strip()


def _gemini_generate(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    image_bytes: bytes | None = None,
    mime: str = "image/png",
) -> str:
    from google import genai
    from google.genai import types

    key = _gemini_api_key()
    if not key:
        raise RuntimeError("gemini_api_key not found in config/api_keys.json")

    client = genai.Client(api_key=key)
    model_name = model or "gemini-flash-latest"
    parts: list[Any] = []
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    parts.append(prompt)

    kwargs: dict[str, Any] = {"model": model_name, "contents": parts}
    if system:
        kwargs["config"] = types.GenerateContentConfig(system_instruction=system)

    response = client.models.generate_content(**kwargs)
    return (getattr(response, "text", None) or "").strip()


def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    timeout: int = 180,
) -> str:
    """Plain text generation routed to Ollama or Gemini."""
    if is_ollama_backend():
        try:
            messages: list[dict] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            # Ignore Gemini model names when on Ollama — use configured local model.
            local_model = None if (model and "gemini" in model.lower()) else model
            return _ollama_chat(messages, model=local_model, timeout=timeout)
        except Exception as e:
            print(f"[local_llm] Ollama text gen failed ({e}); trying Gemini fallback")
            if not _gemini_api_key():
                raise
    return _gemini_generate(prompt, model=model, system=system)


def generate_vision(
    prompt: str,
    image_bytes: bytes,
    *,
    mime: str = "image/png",
    model: str | None = None,
    timeout: int = 180,
) -> str:
    """Image + text generation. Ollama uses vision_model (or chat model)."""
    if is_ollama_backend():
        try:
            _, chat_model, _, vision_model = _ollama_settings()
            m = model or vision_model or chat_model
            if m and "gemini" in m.lower():
                m = vision_model or chat_model
            b64 = base64.b64encode(image_bytes).decode("ascii")
            messages = [{
                "role": "user",
                "content": prompt,
                "images": [b64],
            }]
            return _ollama_chat(messages, model=m, timeout=timeout)
        except Exception as e:
            print(f"[local_llm] Ollama vision failed ({e}); trying Gemini fallback")
            if not _gemini_api_key():
                raise
    return _gemini_generate(prompt, model=model, image_bytes=image_bytes, mime=mime)


class LocalModel:
    """Drop-in for the old `_get_gemini()` / `_gemini_client()` wrappers."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name

    def generate_content(self, contents: Any) -> _TextResponse:
        prompt, image_bytes, mime = _contents_to_prompt(contents)
        if image_bytes:
            text = generate_vision(
                prompt or "Describe this image.",
                image_bytes,
                mime=mime,
                model=self.model_name,
            )
        else:
            text = generate_text(prompt, model=self.model_name)
        return _TextResponse(text)


def get_model(model_name: str | None = None) -> LocalModel:
    """Preferred entry point for action modules."""
    return LocalModel(model_name)
