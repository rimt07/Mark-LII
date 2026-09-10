#web_search.py
import json
import sys
import threading
import time
from pathlib import Path

# ── Gemini grounding quota circuit breaker ────────────────────────────────────
# The google_search grounding tool has its own small quota, separate from plain
# generation.  Once it is spent every call returns 429 — so retrying it at the
# top of every search only adds a dead round-trip before the DDG fallback runs.
# After a quota error, skip Gemini entirely for a cooldown period.
_QUOTA_COOLDOWN_SEC  = 900          # 15 minutes
_quota_blocked_until = 0.0
_quota_lock          = threading.Lock()


def _gemini_available() -> bool:
    with _quota_lock:
        return time.monotonic() >= _quota_blocked_until


def _note_gemini_error(exc: Exception) -> None:
    """Trip the breaker when the error is a quota / rate-limit rejection."""
    global _quota_blocked_until
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        with _quota_lock:
            already = time.monotonic() < _quota_blocked_until
            _quota_blocked_until = time.monotonic() + _QUOTA_COOLDOWN_SEC
        if not already:
            print(
                "[WebSearch] Gemini grounding quota exhausted — skipping it for "
                f"{_QUOTA_COOLDOWN_SEC // 60} min and serving results from DDG."
            )


class _QuotaCooldown(RuntimeError):
    """Raised instead of calling Gemini while the quota breaker is open."""


def _log_gemini_failure(context: str, exc: Exception) -> None:
    """Log a Gemini failure — silently when it is just the expected cooldown."""
    if isinstance(exc, _QuotaCooldown):
        return          # announced once when the breaker tripped; not a warning
    print(f"[WebSearch] \u26a0\ufe0f {context} failed ({exc}) — using DDG instead")


def _run_bounded(fn, timeout: float, label: str = "task"):
    """Run fn() in a daemon thread; return its result, or None if it overruns."""
    box = [None]

    def _run():
        try:
            box[0] = fn()
        except Exception as e:
            _log_gemini_failure(label, e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print(f"[WebSearch] {label} exceeded {timeout:.0f}s — moving on")
    return box[0]

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# All search/news output is requested and formatted in Spanish.
_GEMINI_ES_SUFFIX = " Responde siempre en español."
_DDG_REGION       = "mx-es"   # DuckDuckGo region — Spanish / Mexico

# Startup briefing — (section label, DDG query). Edit here to change topics.
DEFAULT_NEWS_DIGEST_TOPICS: list[tuple[str, str]] = [
    ("México",                  "noticias Mexico hoy"),
    ("Tecnología",              "noticias tecnologia hoy"),
    ("Programación",            "noticias programacion desarrollo software"),
    ("Inteligencia artificial", "noticias inteligencia artificial"),
    (".NET y arquitectura",     "noticias Microsoft .NET"),
    ("Nube / Cloud",            "noticias computacion en la nube Azure AWS"),
]

_ENGLISH_HINTS = (
    " the ", " and ", " with ", " for ", " of ", " says ", " after ",
    " stock ", " today ", " why ", " how ", " what ", " amid ", " over ",
)
_SPANISH_HINTS = (
    " de ", " en ", " el ", " la ", " los ", " las ", " que ", " con ",
    " para ", " hoy ", " noticias ", " méxico", " mexico", " del ", " una ",
)


def _is_likely_spanish(text: str) -> bool:
    t = f" {text.lower()} "
    es = sum(1 for h in _SPANISH_HINTS if h in t)
    en = sum(1 for h in _ENGLISH_HINTS if h in t)
    if any(c in text for c in "áéíóúñ¿¡"):
        es += 2
    return es > en or (es >= en and es > 0)


def _prefer_spanish(results: list[dict], max_results: int) -> list[dict]:
    if not results:
        return []
    es = [
        r for r in results
        if _is_likely_spanish(f"{r.get('title', '')} {r.get('snippet', '')}")
    ]
    if es:
        return es[:max_results]
    return results[:max_results]


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_search(query: str) -> str:
    from core.local_llm import is_ollama_backend
    if is_ollama_backend():
        raise RuntimeError("Gemini grounding skipped — Ollama backend active")

    if not _gemini_available():
        raise _QuotaCooldown("Gemini grounding is in quota cooldown")

    from google import genai

    client = genai.Client(api_key=_get_api_key())
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=f"{query}{_GEMINI_ES_SUFFIX}",
            config={"tools": [{"google_search": {}}]},
        )
    except Exception as e:
        _note_gemini_error(e)
        raise

    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def _get_ddgs():
    """
    Returns the DDGS class.  The package was renamed duckduckgo-search -> ddgs;
    the legacy package's endpoints are now rejected by DuckDuckGo (news() gets a
    403 Ratelimit, text() silently returns zero results), so warn loudly if we
    end up on it instead of failing in silence.
    """
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        from duckduckgo_search import DDGS
        print(
            "[WebSearch] ⚠️ Using the deprecated 'duckduckgo-search' package — "
            "DuckDuckGo blocks its endpoints, so every search will come back "
            "empty.  Fix with:  pip install -U ddgs"
        )
        return DDGS


def _ddg_search(
    query: str,
    max_results: int = 6,
    *,
    region: str = _DDG_REGION,
) -> list[dict]:
    DDGS = _get_ddgs()
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, region=region):
                results.append({
                    "title":   r.get("title",  ""),
                    "snippet": r.get("body",   ""),
                    "url":     r.get("href",   ""),
                })
    except Exception as e:
        print(f"[WebSearch] ⚠️ DDG text() failed: {e}")
    return results


def _dedupe_results(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in results:
        key = (r.get("url") or r.get("title", "").lower().strip())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _ddg_news(
    query: str,
    max_results: int = 8,
    *,
    region: str = _DDG_REGION,
) -> list[dict]:
    """DDG news search — returns actual articles, not website homepages."""
    DDGS = _get_ddgs()
    results: list[dict] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results, region=region):
                results.append({
                    "title":   r.get("title",  ""),
                    "snippet": r.get("body",   ""),
                    "url":     r.get("url",    ""),
                    "source":  r.get("source", ""),
                })
    except Exception as e:
        print(f"[WebSearch] ⚠️ DDG news() failed ({e}) — falling back to text search")
    # news() often returns 1–3 hits; pad with text search in the same region.
    if len(results) < max_results:
        extra = _ddg_search(query, max_results=max_results, region=region)
        results = _dedupe_results(results + extra)
    return _prefer_spanish(results, max_results)


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No se encontraron resultados para: {query}"

    lines = [f"Resultados de búsqueda: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   Fuente: {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_news(query: str, results: list[dict], *, include_urls: bool = True) -> str:
    if not results:
        return f"No se encontraron noticias para: {query}"

    lines = [f"Últimas noticias: {query}\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        if not title:
            continue
        src = f"  [{r['source']}]" if r.get("source") else ""
        lines.append(f"{i}. {title}{src}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:140]}")
        if include_urls and r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_news_digest(
    sections: list[tuple[str, list[dict]]],
    *,
    include_urls: bool = True,
) -> str:
    if not sections:
        return "No se encontraron noticias."

    lines = ["Resumen de noticias del día\n"]
    for label, results in sections:
        if not results:
            continue
        lines.append(f"▸ {label}")
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            if not title:
                continue
            src = f" [{r['source']}]" if r.get("source") else ""
            lines.append(f"  {i}. {title}{src}")
            if r.get("snippet"):
                lines.append(f"     {r['snippet'][:120]}")
            if include_urls and r.get("url"):
                lines.append(f"     {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _news_digest(
    topics: list[tuple[str, str]] | None = None,
    *,
    per_topic: int = 2,
) -> tuple[str, str]:
    """
    Fetch headlines across several topics for the startup briefing.
    Returns (spoken_text, display_text) — URLs only in display_text.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    topic_list = topics or DEFAULT_NEWS_DIGEST_TOPICS
    order = {label: i for i, (label, _) in enumerate(topic_list)}
    sections: list[tuple[str, list[dict]]] = []

    def _fetch_one(label: str, query: str) -> tuple[str, list[dict]]:
        hits = _dedupe_results(_ddg_news(query, max_results=per_topic + 2))[:per_topic]
        return label, hits

    with ThreadPoolExecutor(max_workers=min(6, len(topic_list))) as pool:
        futures = {
            pool.submit(_fetch_one, label, query): label
            for label, query in topic_list
        }
        for fut in as_completed(futures):
            try:
                label, hits = fut.result()
                if hits:
                    sections.append((label, hits))
            except Exception as e:
                print(f"[WebSearch] ⚠️ Digest topic failed ({futures[fut]}): {e}")

    sections.sort(key=lambda s: order.get(s[0], 99))

    if not sections:
        return _news("")

    spoken  = _format_news_digest(sections, include_urls=False)
    display = _format_news_digest(sections, include_urls=True)
    flat    = [r for _, rs in sections for r in rs]
    _print_news_urls(flat)
    print(f"[WebSearch] 📰 Digest ({len(flat)} titulares):\n{display}")
    return spoken, display


def _print_news_urls(results: list[dict]) -> None:
    """Log article URLs to the console — never sent to TTS."""
    urls = [
        (i, r.get("title", "")[:70], r["url"])
        for i, r in enumerate(results, 1)
        if r.get("url")
    ]
    if not urls:
        return
    print("[WebSearch] 🔗 URLs de noticias (solo consola, no vocalizar):")
    for i, title, url in urls:
        print(f"  {i}. {title}")
        print(f"     {url}")


# ── Briefing helper ────────────────────────────────────────────────────────────

def _gemini_headlines(n: int = 5) -> tuple[list[str], str]:
    """
    Fetches current headlines via Gemini grounded search.
    Optimised for speed: minimal prompt + strict token cap.
    Returns (headline_list, raw_text_for_display).
    On Ollama backend, returns empty so callers fall through to DDG.
    """
    import re
    from core.local_llm import is_ollama_backend

    if is_ollama_backend():
        return [], ""

    from google import genai

    client = genai.Client(api_key=_get_api_key())
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=(
            f"Noticias mundiales actuales: {n} titulares. "
            f"Lista numerada, solo títulos, en español.{_GEMINI_ES_SUFFIX}"
        ),
        config={"tools": [{"google_search": {}}]},
    )

    raw = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            raw += part.text

    headlines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Only accept lines that begin with a number — skips preamble/closing sentences
        if not re.match(r'^[\d]+[.\)\-]', line):
            continue
        clean = re.sub(r'^[\d]+[.\)\-]\s*', '', line)
        clean = re.sub(r'^\*+\s*',          '', clean).strip()
        if clean and len(clean) > 10:
            headlines.append(clean)

    return headlines[:n], raw.strip()


# ── Modes ──────────────────────────────────────────────────────────────────────

def _search(query: str) -> str:
    """Default search — Gemini grounded, DDG fallback."""
    try:
        return _gemini_search(query)
    except Exception as e:
        _log_gemini_failure("Gemini search", e)
        results = _ddg_search(query)
        return _format_ddg(query, results)


def _news(query: str) -> tuple[str, str]:
    """
    DDG first, Gemini as backup.

    Returns (spoken_text, display_text). URLs appear only in display_text and
    are printed to the console — never in spoken_text, so JARVIS won't read them.

    The old version raced both backends in parallel and kept the first answer.
    That burned one google_search grounding call on *every* news request —
    including the startup briefing — even when DDG had already won the race.
    Grounding has a small quota, so it ran dry after a handful of launches and
    then 429'd for everything else (research/compare), which are the modes that
    actually need a synthesised answer.

    DDG news returns in well under a second and gives raw headlines, which is
    exactly what the briefing wants, so it goes first and Gemini is only touched
    when DDG comes back empty.
    """
    gemini_query = (
        f"últimas noticias de hoy en español: {query}"
        if query else "principales noticias de México y el mundo hoy en español"
    )
    ddg_query    = query if query else "noticias Mexico hoy"

    def _ddg_attempt() -> tuple[str, str]:
        results = _ddg_news(ddg_query, max_results=8)
        spoken  = _format_news(ddg_query, results, include_urls=False)
        display = _format_news(ddg_query, results, include_urls=True)
        _print_news_urls(results)
        print(f"[WebSearch] 📰 Noticias:\n{display}")
        return spoken, display

    pair = _run_bounded(_ddg_attempt, timeout=5.0, label="DDG news")
    if pair and len(pair[0]) > 60 and not pair[0].startswith("No se encontraron noticias"):
        return pair

    text = _run_bounded(
        lambda: _gemini_search(gemini_query), timeout=6.0, label="Gemini news"
    )
    if text and len(text) > 60:
        print(f"[WebSearch] 📰 Noticias (Gemini):\n{text}")
        return text, text

    err = f"No se encontraron noticias para: {query}"
    return err, err


def _research(query: str) -> str:
    """
    Deep dive — asks Gemini for a comprehensive answer with context.
    Falls back to a wider DDG fetch.
    """
    research_query = (
        f"Explicación completa y detallada de: {query}. "
        "Incluye contexto, datos clave, estado actual y matices importantes."
    )
    try:
        return _gemini_search(research_query)
    except Exception as e:
        _log_gemini_failure("Gemini research", e)
        results = _ddg_search(query, max_results=10)
        return _format_ddg(query, results)


def _price(query: str) -> str:
    """Product price lookup — searches for current market prices."""
    price_query = f"precio actual de {query} — cuánto cuesta hoy"
    try:
        return _gemini_search(price_query)
    except Exception as e:
        _log_gemini_failure("Gemini price", e)
        results = _ddg_search(f"{query} price buy", max_results=6)
        return _format_ddg(query, results)


def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compara {', '.join(items)} en cuanto a {aspect}. "
        "Da datos y hechos concretos."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        _log_gemini_failure("Gemini compare", e)

    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparación — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
            if r.get("url"):
                lines.append(f"    {r['url']}")
    return "\n".join(lines)


# ── Public entry point ─────────────────────────────────────────────────────────

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Indica qué quieres buscar."

    if items and mode not in ("compare",):
        mode = "compare"

    if player:
        player.write_log(f"[Search:{mode}] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 mode={mode!r}  query={query!r}")

    try:
        if mode == "compare" and items:
            return _compare(items, aspect)
        if mode == "news":
            spoken, display = _news(query)
            if player and display and not display.startswith(
                ("No se encontraron noticias", "Error en la búsqueda", "Indica qué")
            ):
                _label = f"NEWS — {(query or 'noticias')[:38]}"
                player.show_content(_label, display)
            return spoken
        if mode == "research":
            return _research(query)
        if mode == "price":
            return _price(query)
        return _search(query)

    except Exception as e:
        print(f"[WebSearch] ❌ All backends failed: {e}")
        return f"Error en la búsqueda: {e}"
