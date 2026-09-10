"""
Ollama Backend for MARK LII

Local LLM backend using Ollama + Whisper STT + Kokoro/Edge TTS.
Provides voice-to-voice interaction without cloud dependencies.
"""
import asyncio
import base64
import json
import os
import re
import tempfile
import time
from typing import Callable, List, Dict, Any

from core.stt import WhisperSTT

import numpy as np

# Sentence/clause boundaries for streaming TTS.
_SENT_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)\s*\n')
_CLAUSE_END = re.compile(r'(?<=[,;])\s+')
_TTS_SENTINEL = object()

_TTS_FLOW_DEFAULTS = {
    "merge_max_chars": 400,
    "max_chunk_chars": 400,
    "clause_flush_chars": 100,
    "flush_timeout_sec": 1.8,
    "min_flush_chars": 40,
    "max_pause_ms": 200,
    "trailing_pause_ms": 60,
    "mid_pad_ms": 45,
    "last_pad_ms": 120,
    "warmup_phrase": "Hola.",
}


class OllamaBackend:
    """
    Local voice assistant backend using:
    - Ollama for LLM inference
    - Whisper for speech-to-text
    - Kokoro ONNX or Edge TTS for text-to-speech
    """

    def __init__(
        self,
        config: dict,
        ui_logger: Callable,
        speak_callback: Callable,
        speaking_callback: Callable | None = None,
    ):
        self.config = config
        self.ui_logger = ui_logger
        self.speak_callback = speak_callback
        # Optional: notify the host UI when TTS starts/stops (for mute/HUD).
        self.speaking_callback = speaking_callback

        # Audio processing
        self.sample_rate = 16000
        self.audio_buffer = []
        self.is_listening = False
        # Energy-based VAD. Threshold is configurable because mic sensitivity
        # varies wildly (a Yeti Nano runs hot); default lowered from 0.02 to
        # 0.01 so normal speech reliably crosses it.
        _stt_cfg = config.get("stt", {})
        self.vad_threshold = float(_stt_cfg.get("vad_threshold", 0.01))
        # A single quiet chunk (~64 ms) used to end an utterance, which cut
        # speech between words. Require a run of quiet chunks (~0.8 s) instead,
        # and ignore utterances shorter than ~0.3 s (coughs, clicks, key taps).
        # At 16 kHz / 1024-sample chunks each chunk is ~64 ms.
        self._vad_silence_needed = int(_stt_cfg.get("silence_chunks", 12))   # ~0.8 s
        self._vad_min_speech_chunks = int(_stt_cfg.get("min_speech_chunks", 5))  # ~0.3 s
        self._vad_silence_run = 0        # consecutive quiet chunks while listening
        self._vad_speech_chunks = 0      # voiced chunks in the current utterance
        self._vad_peak = 0.0             # loudest energy seen this utterance
        self._vad_debug = bool(_stt_cfg.get("debug", False))

        # Ollama client
        self.ollama_client = None
        self.ollama_base_url = config.get("base_url", "http://localhost:11434")
        self.ollama_model = config.get("model", "llama3.2:latest")
        self.temperature = float(config.get("temperature", 0.7))
        self.stream_enabled = bool(config.get("stream", True))
        self.vision_model = (config.get("vision_model") or "").strip() or None

        # STT/TTS engines
        self.stt_engine = None
        self.tts_engine = None

        # Conversation history
        self.messages: List[Dict[str, str]] = []
        self.system_prompt = ""

        # Tool registry
        self.tools = []
        self.ollama_tools = []      # tools converted to Ollama's schema
        self.tool_executor = None

        self._initialized = False
        self._running = False
        self._busy = False          # True while STT/LLM/TTS turn is in flight
        self._is_speaking = False
        self._interrupted = False
        self._speak_lock = asyncio.Lock()
        self._apply_tts_flow_config({})

    def _apply_tts_flow_config(self, tts_config: dict) -> None:
        """Load TTS pacing options from config/llm_config.json → ollama.tts.flow."""
        flow = {**_TTS_FLOW_DEFAULTS, **(tts_config.get("flow") or {})}
        self._tts_merge_max_chars = int(flow["merge_max_chars"])
        self._tts_max_chunk_chars = int(flow["max_chunk_chars"])
        self._tts_clause_flush_chars = int(flow["clause_flush_chars"])
        self._tts_flush_timeout_sec = float(flow["flush_timeout_sec"])
        self._tts_min_flush_chars = int(flow["min_flush_chars"])
        self._tts_max_pause_ms = int(flow["max_pause_ms"])
        self._tts_trailing_pause_ms = int(flow["trailing_pause_ms"])
        self._tts_mid_pad_ms = int(flow["mid_pad_ms"])
        self._tts_last_pad_ms = int(flow["last_pad_ms"])
        self._tts_warmup_phrase = str(flow["warmup_phrase"] or "Hola.")

    async def initialize(self, system_prompt: str, tools: List[dict], tool_executor: Callable):
        """Initialize Ollama backend and load models"""
        try:
            self.ui_logger("[Ollama] Initializing local backend...")

            # Import Ollama client
            try:
                import ollama
                self.ollama_client = ollama.AsyncClient(host=self.ollama_base_url)
            except ImportError:
                self.ui_logger("[Ollama] ERROR: 'ollama' package not installed. Run: pip install ollama")
                return False

            # Test Ollama connection
            try:
                models = await self.ollama_client.list()

                # Normalise across ollama-python versions. Recent versions return
                # a ListResponse of Model objects exposing `.model` (e.g.
                # "llama3.2:latest"); older ones returned dicts keyed by "name"
                # or "model", inside {"models": [...]}. Reading m['name'] on the
                # new objects raises KeyError('name'), which previously aborted
                # startup and made JARVIS fall over on a "cannot connect" message
                # even though Ollama was running fine.
                raw = getattr(models, "models", None)
                if raw is None and isinstance(models, dict):
                    raw = models.get("models", [])
                raw = raw or []

                available = []
                for m in raw:
                    name = (
                        getattr(m, "model", None)
                        or getattr(m, "name", None)
                        or (m.get("model") or m.get("name") if isinstance(m, dict) else None)
                    )
                    if name:
                        available.append(name)

                self.ui_logger(f"[Ollama] Available models: {', '.join(available)}")

                # Match tolerantly: accept an exact match, or a match ignoring a
                # missing ":latest" tag on either side (Ollama treats a bare name
                # as ":latest").
                def _norm(n: str) -> str:
                    return n if ":" in n else f"{n}:latest"

                wanted = _norm(self.ollama_model)
                available_norm = {_norm(a) for a in available}
                if wanted not in available_norm:
                    self.ui_logger(f"[Ollama] WARNING: Model '{self.ollama_model}' not found. Download with: ollama pull {self.ollama_model}")
                    return False

            except Exception as e:
                self.ui_logger(f"[Ollama] ERROR: Cannot connect to Ollama at {self.ollama_base_url}: {e}")
                self.ui_logger("[Ollama] Make sure Ollama is running: ollama serve")
                return False

            # Initialize STT (Whisper)
            stt_config = self.config.get("stt", {})
            stt_engine = stt_config.get("engine", "whisper")

            if stt_engine == "whisper":
                try:
                    model_size = stt_config.get("model", "base")
                    _dev = (stt_config.get("device", "") or "").strip().lower()
                    _dev = _dev if _dev in ("cuda", "cpu") else None
                    self.stt_engine = WhisperSTT(
                        model_size,
                        language=stt_config.get("language"),
                        device=_dev,
                        logger=self.ui_logger,
                    )
                    self.ui_logger("[Ollama] Whisper loaded successfully")
                except ImportError:
                    self.ui_logger(
                        "[Ollama] ERROR: 'faster-whisper' not installed. "
                        "Run: pip install faster-whisper nvidia-cublas-cu12 nvidia-cuda-runtime-cu12"
                    )
                    return False

            # Initialize TTS
            tts_config = self.config.get("tts", {})
            self._apply_tts_flow_config(tts_config)
            tts_engine = tts_config.get("engine", "edge")

            if tts_engine == "kokoro":
                try:
                    from core.kokoro_tts_wrapper import KokoroTTS
                    self.tts_engine = "kokoro"
                    self.tts_kokoro = KokoroTTS(
                        voice=tts_config.get("voice", "af_sarah"),
                        speed=tts_config.get("speed", 1.0),
                        lang=tts_config.get("lang", "en-us"),
                        model_path=tts_config.get("model_path"),
                        voices_path=tts_config.get("voices_path"),
                        logger=self.ui_logger,
                        max_pause_ms=self._tts_max_pause_ms,
                        trailing_pause_ms=self._tts_trailing_pause_ms,
                    )
                    if self.tts_kokoro.initialize():
                        self.ui_logger(f"[Ollama] Using Kokoro TTS (offline) with voice: {tts_config.get('voice', 'af_sarah')}")
                        await asyncio.to_thread(
                            self.tts_kokoro.warmup, self._tts_warmup_phrase
                        )
                    else:
                        self.ui_logger("[Ollama] Kokoro TTS initialization failed, falling back to Edge TTS")
                        tts_engine = "edge"  # Fallback to Edge TTS
                except ImportError:
                    self.ui_logger("[Ollama] WARNING: 'kokoro-onnx' not installed. Run: pip install kokoro-onnx")
                    self.ui_logger("[Ollama] Falling back to Edge TTS")
                    tts_engine = "edge"

            if tts_engine == "edge":
                try:
                    import edge_tts
                    self.tts_engine = "edge"
                    # The configured `voice` may be a Kokoro voice id (e.g.
                    # "af_sarah") because Kokoro is the primary engine. Edge
                    # rejects those — its voices look like "en-US-AriaNeural"
                    # (locale-Name+"Neural"). Only reuse the configured voice if
                    # it already looks like an Edge voice; otherwise fall back to
                    # the configured Edge fallback, then a sane default.
                    import re as _re
                    _cfg_voice = (tts_config.get("voice", "") or "").strip()
                    _edge_fallback = (tts_config.get("_edge_voice_fallback", "")
                                      or "en-US-AriaNeural").strip()
                    _looks_like_edge = bool(_re.match(r"^[a-z]{2}-[A-Z]{2}-.+", _cfg_voice))
                    self.tts_voice = _cfg_voice if _looks_like_edge else _edge_fallback
                    if not _looks_like_edge and _cfg_voice:
                        self.ui_logger(
                            f"[Ollama] '{_cfg_voice}' is not an Edge voice — "
                            f"using Edge voice '{self.tts_voice}' instead."
                        )
                    self.ui_logger(f"[Ollama] Using Edge TTS with voice: {self.tts_voice}")
                except ImportError:
                    self.ui_logger("[Ollama] WARNING: 'edge-tts' not installed. Run: pip install edge-tts")
                    self.ui_logger("[Ollama] Falling back to no TTS (text-only mode)")
                    self.tts_engine = None

            # Store system prompt and tools
            self.system_prompt = system_prompt
            self.tools = tools
            self.tool_executor = tool_executor
            # Ollama's chat API expects tools in OpenAI-style JSON Schema
            # ({"type":"function","function":{name,description,parameters}} with
            # lowercase JSON-Schema types), while the app declares them in the
            # Gemini style ("type":"OBJECT"/"STRING"). Convert once here so every
            # chat turn can pass the ready list without re-converting.
            self.ollama_tools = self._convert_tools_for_ollama(tools)
            self.ui_logger(f"[Ollama] {len(self.ollama_tools)} tools available for function calling")

            # Initialize conversation with system prompt
            self.messages = [{"role": "system", "content": system_prompt}]

            self._initialized = True
            self.ui_logger("[Ollama] Backend initialized successfully")
            return True

        except Exception as e:
            self.ui_logger(f"[Ollama] Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def start_session(self):
        """Start interactive session"""
        if not self._initialized:
            self.ui_logger("[Ollama] Backend not initialized")
            return

        self._running = True
        self.ui_logger("[Ollama] Session started - listening for audio...")

    async def stop_session(self):
        """Stop interactive session"""
        self._running = False
        self.ui_logger("[Ollama] Session stopped")

    def interrupt(self) -> None:
        """Stop TTS mid-playback and discard the current mic utterance."""
        self._interrupted = True
        self._reset_vad(keep_buffer=False)
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        if self._is_speaking:
            self._set_speaking(False)
        self.ui_logger("[Ollama] Interrupted — listening...")

    def _set_speaking(self, value: bool) -> None:
        self._is_speaking = value
        if self.speaking_callback:
            try:
                self.speaking_callback(value)
            except Exception:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def is_busy(self) -> bool:
        return self._busy or self._is_speaking

    async def process_audio_chunk(self, audio_data: bytes):
        """
        Process incoming audio chunk.
        Buffers audio while voice is present, and only transcribes once a
        sustained run of silence follows real speech — so natural pauses
        between words don't cut an utterance in half, and brief noises don't
        trigger a transcription of nothing.
        """
        if not self._running:
            return
        # Ignore mic while the assistant is thinking or speaking (no AEC).
        if self._busy or self._is_speaking:
            return

        # Convert bytes to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Voice Activity Detection (simple energy-based)
        energy = float(np.abs(audio_np).mean())

        if energy > self.vad_threshold:
            # Voiced chunk: (re)start the utterance, reset the silence run.
            self.audio_buffer.extend(audio_np)
            self.is_listening = True
            self._vad_silence_run = 0
            self._vad_speech_chunks += 1
            if energy > self._vad_peak:
                self._vad_peak = energy
        elif self.is_listening:
            # Quiet chunk while we were hearing speech. Keep a little trailing
            # audio so word tails aren't clipped, and count the silence run.
            self.audio_buffer.extend(audio_np)
            self._vad_silence_run += 1

            if self._vad_silence_run >= self._vad_silence_needed:
                # End of utterance. Only transcribe if enough voiced audio was
                # captured — otherwise it was noise, so discard and reset.
                if self._vad_speech_chunks >= self._vad_min_speech_chunks:
                    if self._vad_debug:
                        self.ui_logger(
                            f"[Ollama] VAD: utterance ~{self._vad_speech_chunks*64}ms "
                            f"peak={self._vad_peak:.4f} thr={self.vad_threshold:.4f}"
                        )
                    self._reset_vad(keep_buffer=True)
                    await self._transcribe_and_respond()
                else:
                    if self._vad_debug:
                        self.ui_logger(
                            f"[Ollama] VAD: discarded short blip "
                            f"({self._vad_speech_chunks} voiced chunks)"
                        )
                    self._reset_vad(keep_buffer=False)

    def _reset_vad(self, keep_buffer: bool):
        """Reset per-utterance VAD state. Clears the buffer unless the caller
        is about to transcribe it (_transcribe_and_respond empties it itself)."""
        if not keep_buffer:
            self.audio_buffer = []
        self.is_listening = False
        self._vad_silence_run = 0
        self._vad_speech_chunks = 0
        self._vad_peak = 0.0

    async def _transcribe_and_respond(self):
        """Transcribe buffered audio and generate response"""
        if not self.audio_buffer:
            return

        self._busy = True
        self._interrupted = False
        try:
            self.ui_logger("[Ollama] Transcribing audio...")

            # Convert buffer to numpy array
            audio_np = np.array(self.audio_buffer, dtype=np.float32)
            self.audio_buffer = []
            self.is_listening = False

            # Guard: Whisper crashes with "cannot reshape tensor of 0 elements"
            # when handed an empty or effectively-silent clip (the mel-spectrogram
            # ends up with 0 frames). Discard anything shorter than ~0.2 s or
            # whose peak amplitude is below the noise floor before transcribing.
            _min_samples = int(self.sample_rate * 0.2)  # 200 ms
            if audio_np.size < _min_samples or float(np.max(np.abs(audio_np))) < 1e-3:
                if self._vad_debug:
                    self.ui_logger(
                        f"[Ollama] Skipping transcription: audio too short/silent "
                        f"({audio_np.size} samples, peak={float(np.max(np.abs(audio_np))) if audio_np.size else 0:.5f})"
                    )
                return

            _t0 = time.monotonic()
            user_text, _detected = await asyncio.to_thread(
                self.stt_engine.transcribe,
                audio_np,
            )
            _elapsed = time.monotonic() - _t0

            if self._vad_debug:
                self.ui_logger(
                    f"[Ollama] Whisper took {_elapsed:.1f}s, detected lang '{_detected}', "
                    f"text: {user_text!r}"
                )
            if not user_text:
                if not self._vad_debug:
                    self.ui_logger(f"[Ollama] Transcription empty ({_elapsed:.1f}s) — nothing recognised.")
                return

            self.ui_logger(f"[Ollama] User: {user_text}")

            # Add to conversation history
            self.messages.append({"role": "user", "content": user_text})

            # Generate response with Ollama
            await self._generate_response()

        except Exception as e:
            self.ui_logger(f"[Ollama] Transcription error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._busy = False

    # ── Function calling ─────────────────────────────────────────────────────
    @staticmethod
    def _normalize_schema(node):
        """
        Recursively convert a Gemini-style JSON schema to standard JSON Schema
        that Ollama/OpenAI expect. Gemini uses uppercase type names
        ("OBJECT"/"STRING"/"ARRAY"/…); JSON Schema uses lowercase
        ("object"/"string"/"array"/…). Everything else is passed through.
        """
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k == "type" and isinstance(v, str):
                    out[k] = v.lower()
                else:
                    out[k] = OllamaBackend._normalize_schema(v)
            return out
        if isinstance(node, list):
            return [OllamaBackend._normalize_schema(x) for x in node]
        return node

    @staticmethod
    def _convert_tools_for_ollama(tools):
        """
        Convert the app's Gemini-style tool declarations
        ({name, description, parameters}) into Ollama's function-calling format
        ({"type":"function","function":{name, description, parameters}}), with
        the parameter schema normalized to lowercase JSON-Schema types.
        Tools that can't be converted are skipped rather than aborting the set.
        """
        converted = []
        for t in tools or []:
            try:
                name = t.get("name")
                if not name:
                    continue
                params = t.get("parameters") or {"type": "object", "properties": {}}
                converted.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": t.get("description", ""),
                        "parameters": OllamaBackend._normalize_schema(params),
                    },
                })
            except Exception:
                continue
        return converted

    class _FnCall:
        """
        Minimal stand-in for the Gemini FunctionCall object that the app's
        tool_executor (main.py:_execute_tool) expects: it reads .name, .args
        and .id. Ollama gives us a name + an args dict, so we wrap them.
        """
        __slots__ = ("name", "args", "id")

        def __init__(self, name, args, call_id):
            self.name = name
            self.args = args or {}
            self.id = call_id

    @staticmethod
    def _extract_result_text(fn_response) -> str:
        """
        The tool_executor returns a Gemini types.FunctionResponse whose payload
        lives in .response["result"]. Pull the text out defensively so a shape
        change can't crash the loop.
        """
        try:
            resp = getattr(fn_response, "response", None)
            if isinstance(resp, dict):
                return str(resp.get("result", resp))
            if resp is not None:
                return str(resp)
            return str(fn_response)
        except Exception:
            return str(fn_response)

    def _build_chat_kwargs(self, use_tools: bool) -> dict:
        opts: dict = {"temperature": self.temperature}
        num_predict = self.config.get("num_predict")
        if num_predict is not None:
            opts["num_predict"] = int(num_predict)
        kwargs = dict(
            model=self.ollama_model,
            messages=self.messages,
            options=opts,
            keep_alive=-1,
        )
        if use_tools:
            kwargs["tools"] = self.ollama_tools
        return kwargs

    @staticmethod
    def _normalize_stream_message(chunk) -> dict:
        """Normalise one Ollama stream chunk to a plain message dict."""
        msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", chunk)
        if isinstance(msg, dict):
            return {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", "") or "",
                "tool_calls": msg.get("tool_calls") or [],
            }
        return {
            "role": getattr(msg, "role", "assistant"),
            "content": getattr(msg, "content", "") or "",
            "tool_calls": getattr(msg, "tool_calls", None) or [],
        }

    def _extract_sentences(self, buf: str) -> tuple[list[str], str]:
        """Pull complete sentences, clauses, or long spans from a text buffer."""
        sentences: list[str] = []
        max_chunk = self._tts_max_chunk_chars
        clause_at = self._tts_clause_flush_chars
        while buf:
            match = _SENT_END.search(buf)
            if match:
                sentence = buf[: match.start() + 1].strip()
                buf = buf[match.end() :]
                if sentence:
                    sentences.append(sentence)
                continue
            if len(buf) >= clause_at:
                match = _CLAUSE_END.search(buf)
                if match:
                    sentence = buf[: match.end()].strip()
                    buf = buf[match.end() :]
                    if sentence:
                        sentences.append(sentence)
                    continue
            if len(buf) >= max_chunk:
                split_at = buf.rfind(" ", 0, max_chunk)
                if split_at < 20:
                    split_at = max_chunk
                sentence = buf[:split_at].strip()
                buf = buf[split_at:].lstrip()
                if sentence:
                    sentences.append(sentence)
                continue
            break
        return sentences, buf

    def _try_timeout_flush(
        self, buf: str, buf_t0: float | None
    ) -> tuple[list[str], str, float | None]:
        """Speak buffered text after a pause even if the model omitted punctuation."""
        if not buf or buf_t0 is None:
            return [], buf, buf_t0
        if len(buf.strip()) < self._tts_min_flush_chars:
            return [], buf, buf_t0
        if time.monotonic() - buf_t0 < self._tts_flush_timeout_sec:
            return [], buf, buf_t0

        split_at = buf.rfind(" ", 0, len(buf))
        if split_at < self._tts_min_flush_chars:
            return [], buf, buf_t0

        chunk = buf[:split_at].strip()
        rest = buf[split_at:].lstrip()
        if not chunk:
            return [], buf, buf_t0
        return [chunk], rest, (time.monotonic() if rest else None)

    def _merge_tts_chunks(self, chunks: list[str]) -> list[str]:
        """Combine short back-to-back sentences into one synthesis call."""
        merged: list[str] = []
        buf = ""
        limit = self._tts_merge_max_chars
        for raw in chunks:
            chunk = (raw or "").strip()
            if not chunk:
                continue
            if not buf:
                buf = chunk
                continue
            if len(buf) + 1 + len(chunk) <= limit:
                buf = f"{buf} {chunk}"
            else:
                merged.append(buf)
                buf = chunk
        if buf:
            merged.append(buf)
        return merged

    async def _edge_tts_to_file(self, text: str) -> str | None:
        """Synthesize Edge TTS via streaming HTTP chunks (faster than save())."""
        import edge_tts

        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="edge_")
        os.close(fd)
        try:
            comm = edge_tts.Communicate(text, self.tts_voice)
            with open(tmp_path, "wb") as handle:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        handle.write(chunk["data"])
            return tmp_path
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise

    async def _synthesize_tts_payload(self, text: str):
        """
        Synthesize one TTS unit.

        Returns ('array', (samples, sr)) for Kokoro or ('file', path) for Edge.
        """
        if not text or self._interrupted:
            return None
        from core.tts import sanitize_for_tts
        text = sanitize_for_tts(text)
        if not text:
            return None
        if self._vad_debug:
            self.ui_logger(f"[Ollama] TTS synthesizing: {text[:80]!r}")
        if self.tts_engine == "kokoro":
            result = await asyncio.to_thread(self.tts_kokoro.synthesize_arrays, text)
            if result:
                return ("array", result)
            return None
        if self.tts_engine == "edge":
            path = await self._edge_tts_to_file(text)
            if path:
                return ("file", path)
        return None

    async def _play_tts_payload(self, payload, *, pad_ms: int | None = None) -> bool:
        if pad_ms is None:
            pad_ms = self._tts_mid_pad_ms
        """Play one synthesized payload and release any temp file."""
        if not payload or self._interrupted:
            return False

        kind, data = payload
        try:
            if kind == "array":
                samples, sr = data
                return await self._play_audio_array(samples, sr, pad_ms=pad_ms)
            if kind == "file":
                return await self._play_audio_file(data, pad_ms=pad_ms)
        finally:
            if kind == "file":
                try:
                    os.unlink(data)
                except Exception:
                    pass
        return False

    async def _play_tts_chunks(self, chunks: list[str]) -> None:
        """
        Play sentences with pipelined synthesis — chunk N+1 synthesises while
        chunk N plays so gaps between periods stay minimal.
        """
        chunks = self._merge_tts_chunks(chunks)
        if not chunks or self._interrupted:
            return

        pending = asyncio.create_task(self._synthesize_tts_payload(chunks[0]))
        any_played = False

        for i, text in enumerate(chunks):
            if self._interrupted:
                pending.cancel()
                break

            try:
                payload = await pending
            except asyncio.CancelledError:
                break

            if i + 1 < len(chunks):
                pending = asyncio.create_task(self._synthesize_tts_payload(chunks[i + 1]))

            if not payload:
                engine = self.tts_engine or "none"
                self.ui_logger(f"[Ollama] TTS: {engine} synthesis returned no audio.")
                continue

            pad_ms = self._tts_last_pad_ms if i == len(chunks) - 1 else self._tts_mid_pad_ms
            if await self._play_tts_payload(payload, pad_ms=pad_ms):
                any_played = True

        if not any_played and not self._interrupted:
            self.ui_logger("[Ollama] TTS: playback failed - check speaker in Settings.")

    async def _run_tts_consumer(self, tts_q: asyncio.Queue) -> None:
        """Background worker: play TTS while the LLM stream keeps producing text."""
        while not self._interrupted:
            item = await tts_q.get()
            if item is _TTS_SENTINEL:
                break

            batch = [item]
            while True:
                try:
                    nxt = tts_q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if nxt is _TTS_SENTINEL:
                    await self._play_tts_chunks(batch)
                    return
                batch.append(nxt)

            await self._play_tts_chunks(batch)

    async def _play_tts_chunk(self, text: str) -> None:
        """Synthesize and play one sentence/clause. Caller must hold _speak_lock."""
        await self._play_tts_chunks([text])

    async def _stream_chat_with_tts(self, kwargs: dict) -> tuple[str, list, bool]:
        """
        Stream an Ollama chat turn and speak each sentence as it arrives.
        Returns (full_text, tool_calls, spoke_via_tts).
        """
        stream_kwargs = dict(kwargs)
        stream_kwargs["stream"] = True
        if self._vad_debug:
            self.ui_logger("[Ollama] Waiting for model stream...")
        stream = await self.ollama_client.chat(**stream_kwargs)

        full_content = ""
        buf = ""
        buf_t0: float | None = None
        tool_calls: list = []
        spoke = False
        use_tts = bool(self.tts_engine) and not self._interrupted
        wait_logged = False

        tts_q: asyncio.Queue | None = None
        tts_task: asyncio.Task | None = None

        async with self._speak_lock:
            if use_tts:
                self._set_speaking(True)
                tts_q = asyncio.Queue()
                tts_task = asyncio.create_task(self._run_tts_consumer(tts_q))
            try:
                async for chunk in stream:
                    if self._interrupted:
                        break

                    msg = self._normalize_stream_message(chunk)
                    delta = msg.get("content") or ""
                    if delta:
                        if not wait_logged:
                            wait_logged = True
                            if self._vad_debug:
                                self.ui_logger("[Ollama] First token received.")
                        if not buf:
                            buf_t0 = time.monotonic()
                        full_content += delta
                        buf += delta
                        sentences, buf = self._extract_sentences(buf)
                        if not sentences:
                            sentences, buf, buf_t0 = self._try_timeout_flush(buf, buf_t0)
                        else:
                            buf_t0 = time.monotonic() if buf.strip() else None
                        if sentences:
                            self.speak_callback(full_content)
                            if use_tts and tts_q is not None:
                                for sentence in sentences:
                                    await tts_q.put(sentence)
                                spoke = True
                            elif not spoke:
                                spoke = True

                    tc = msg.get("tool_calls") or []
                    if tc:
                        tool_calls.extend(tc)

                tool_calls = self._dedupe_tool_calls(tool_calls)

                if buf.strip() and use_tts and tts_q is not None and not self._interrupted:
                    self.speak_callback(full_content)
                    await tts_q.put(buf.strip())
                    spoke = True

                if tts_q is not None:
                    await tts_q.put(_TTS_SENTINEL)
                if tts_task is not None:
                    await tts_task
            except Exception as e:
                self.ui_logger(f"[Ollama] Stream error: {e}")
                if tts_q is not None:
                    await tts_q.put(_TTS_SENTINEL)
                if tts_task is not None:
                    tts_task.cancel()
                    try:
                        await tts_task
                    except asyncio.CancelledError:
                        pass
                raise
            finally:
                if use_tts:
                    self._set_speaking(False)

        if not wait_logged and not full_content and not tool_calls:
            self.ui_logger("[Ollama] Model returned empty response.")

        return full_content.strip(), tool_calls, spoke

    @staticmethod
    def _dedupe_tool_calls(tool_calls: list) -> list:
        """Ollama streaming may repeat the same tool_call across chunks."""
        seen: set[tuple] = set()
        unique: list = []
        for call in tool_calls or []:
            fn = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
            if isinstance(fn, dict):
                key = (fn.get("name"), json.dumps(fn.get("arguments", {}), sort_keys=True, default=str))
            else:
                key = (getattr(fn, "name", None), str(getattr(fn, "arguments", {})))
            if key in seen:
                continue
            seen.add(key)
            unique.append(call)
        return unique

    async def _chat_non_streaming(self, kwargs: dict) -> tuple[str, list]:
        """Single non-streaming Ollama chat turn."""
        resp = await self.ollama_client.chat(**kwargs)
        msg = resp.get("message", {}) if isinstance(resp, dict) else getattr(resp, "message", {})
        if not isinstance(msg, dict):
            msg = {
                "role": getattr(msg, "role", "assistant"),
                "content": getattr(msg, "content", "") or "",
                "tool_calls": getattr(msg, "tool_calls", None),
            }
        return (msg.get("content", "") or "", msg.get("tool_calls") or [])

    async def _generate_response(self):
        """
        Generate a response from Ollama, executing any tools the model calls.

        When streaming is enabled (config ``stream: true``), tokens are spoken
        sentence-by-sentence via TTS as they arrive instead of waiting for the
        full reply. Tool calls are accumulated from the stream and executed in
        the same loop as before.
        """
        try:
            self.ui_logger("[Ollama] Generating response...")

            use_tools = bool(self.ollama_tools and self.tool_executor)
            max_tool_rounds = 5   # safety cap against tool-call loops
            response_text = ""

            for _round in range(max_tool_rounds + 1):
                if self._interrupted:
                    return

                kwargs = self._build_chat_kwargs(use_tools)
                spoke = False

                if self.stream_enabled and self.tts_engine:
                    content, tool_calls, spoke = await self._stream_chat_with_tts(kwargs)
                else:
                    content, tool_calls = await self._chat_non_streaming(kwargs)

                if tool_calls and not spoke and not content.strip() and self.tts_engine:
                    self.ui_logger("[Ollama] Tool call without speech - playing hold prompt.")
                    await self._synthesize_speech("Un momento.")

                if not tool_calls:
                    response_text = content
                    if content:
                        self.messages.append({"role": "assistant", "content": content})
                    if self._interrupted:
                        return
                    if content:
                        self.ui_logger(f"[Ollama] Assistant: {response_text}")
                    if content and not spoke:
                        await self._synthesize_speech(response_text)
                    break

                self.messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                })

                for call in tool_calls:
                    fn = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
                    if isinstance(fn, dict):
                        fn_name = fn.get("name")
                        fn_args = fn.get("arguments", {})
                    else:
                        fn_name = getattr(fn, "name", None)
                        fn_args = getattr(fn, "arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args) if fn_args.strip() else {}
                        except Exception:
                            fn_args = {}

                    self.ui_logger(f"[Ollama] tool call: {fn_name} {fn_args}")

                    if not fn_name:
                        result_text = "La llamada a herramienta no tenía nombre."
                    else:
                        try:
                            fc = self._FnCall(fn_name, fn_args, f"ollama-{_round}-{fn_name}")
                            fn_response = await self.tool_executor(fc)
                            result_text = self._extract_result_text(fn_response)
                        except Exception as e:
                            result_text = f"La herramienta '{fn_name}' falló: {e}"
                            self.ui_logger(f"[Ollama] tool error: {e}")

                    if self._vad_debug:
                        self.ui_logger(f"[Ollama] tool result: {fn_name} -> {str(result_text)[:120]}")

                    self.messages.append({
                        "role": "tool",
                        "name": fn_name,
                        "content": str(result_text),
                    })
            else:
                self.ui_logger("[Ollama] Tool loop hit its round cap; answering with what we have.")

        except Exception as e:
            self.ui_logger(f"[Ollama] Generation error: {e}")
            import traceback
            traceback.print_exc()

    async def analyze_image(
        self,
        image_bytes: bytes,
        question: str,
        *,
        mime: str = "image/jpeg",
        speak_result: bool = True,
    ) -> str:
        """
        Multimodal follow-up for screen_process / camera. Uses vision_model
        when configured, otherwise the chat model (must support images).
        """
        model = self.vision_model or self.ollama_model
        prompt = (question or "What do you see?").strip()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        self.ui_logger(f"[Ollama] Vision via '{model}'…")
        try:
            resp = await self.ollama_client.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }],
                options={"temperature": self.temperature},
            )
            msg = resp.get("message", {}) if isinstance(resp, dict) else getattr(resp, "message", {})
            if not isinstance(msg, dict):
                text = (getattr(msg, "content", "") or "").strip()
            else:
                text = (msg.get("content") or "").strip()
            if not text:
                text = "No pude analizar esa imagen."
            self.messages.append({"role": "user", "content": f"[Vision] {prompt}"})
            self.messages.append({"role": "assistant", "content": text})
            if speak_result and not self._interrupted:
                await self._synthesize_speech(text)
            return text
        except Exception as e:
            err = (
                f"Falló la visión con el modelo '{model}': {e}. "
                f"Descarga un modelo multimodal (p. ej. ollama pull llava) y configura "
                f"ollama.vision_model en config/llm_config.json."
            )
            self.ui_logger(f"[Ollama] {err}")
            return err

    async def _play_audio_array(
        self,
        data: np.ndarray,
        sr: int,
        *,
        pad_ms: int | None = None,
    ) -> bool:
        if pad_ms is None:
            pad_ms = self._tts_mid_pad_ms
        """Play in-memory Kokoro audio without temp-file round trip."""
        return await asyncio.to_thread(self._blocking_play_samples, data, sr, pad_ms)

    async def _play_audio_file(
        self,
        path: str,
        *,
        pad_ms: int | None = None,
    ) -> bool:
        if pad_ms is None:
            pad_ms = self._tts_last_pad_ms
        """Play a synthesized audio file (mp3/wav). Never raises."""
        def _load_and_play() -> bool:
            try:
                import soundfile as sf
            except Exception as e:
                self.ui_logger(f"[Ollama] TTS playback deps missing: {e}")
                return False
            try:
                data, sr = sf.read(path, dtype="float32")
            except Exception as e:
                self.ui_logger(f"[Ollama] Could not decode TTS audio ({e}).")
                return False
            return self._blocking_play_samples(data, sr, pad_ms)

        return await asyncio.to_thread(_load_and_play)

    def _blocking_play_samples(
        self,
        data: np.ndarray,
        sr: int,
        pad_ms: int,
    ) -> bool:
        """
        Play float32 audio on the user's chosen speaker (blocking).

        Returns True if playback ran, False if it could not. Honour interrupt.
        """
        try:
            import sounddevice as sd
            from core.tts import _append_playback_tail
        except Exception as e:
            self.ui_logger(f"[Ollama] TTS playback deps missing: {e}")
            return False

        data = _append_playback_tail(np.asarray(data, dtype=np.float32), sr, ms=pad_ms)
        duration = len(data) / float(sr) if sr else 0.0

        candidates = []
        try:
            from core import audio_devices
            from memory.config_manager import get_output_device
            _resolved = audio_devices.resolve(get_output_device(), "output")
        except Exception:
            _resolved = None
        if _resolved is not None:
            candidates.append(_resolved)
        candidates.append(None)

        for dev in candidates:
            if self._interrupted:
                return False
            try:
                t0 = time.monotonic()
                sd.play(data, sr, device=dev)
                sd.wait()
                took = time.monotonic() - t0
                if self._interrupted:
                    return False
                if duration > 0.3 and took < duration * 0.5:
                    if self._vad_debug:
                        self.ui_logger(
                            f"[Ollama] TTS device={dev!r} looks silent "
                            f"(played {took:.2f}s for {duration:.2f}s) — trying next."
                        )
                    continue
                if self._vad_debug:
                    self.ui_logger(f"[Ollama] TTS played on device={dev!r} ({took:.2f}s).")
                return True
            except Exception as e:
                if self._interrupted:
                    return False
                if self._vad_debug:
                    self.ui_logger(f"[Ollama] TTS device={dev!r} failed: {e}")
                continue

        self.ui_logger("[Ollama] TTS: no working output device produced sound.")
        return False

    async def _synthesize_speech(self, text: str):
        """Convert text to speech and play it sentence-by-sentence."""
        if not text or not str(text).strip():
            return
        if self._interrupted:
            return

        async with self._speak_lock:
            if self._interrupted:
                return
            if not self.tts_engine:
                self.speak_callback(text)
                return

            self.speak_callback(text)
            self._set_speaking(True)
            try:
                buf = text.strip()
                while buf and not self._interrupted:
                    sentences, buf = self._extract_sentences(buf)
                    if sentences:
                        await self._play_tts_chunks(sentences)
                    if (
                        buf.strip()
                        and len(buf) < self._tts_max_chunk_chars
                        and not _SENT_END.search(buf)
                    ):
                        await self._play_tts_chunks([buf.strip()])
                        break
            except Exception as e:
                self.ui_logger(f"[Ollama] TTS error: {e}")
            finally:
                self._set_speaking(False)

    async def speak(self, text: str) -> None:
        """Public mid-turn speech channel (plugins, tool speak=, errors)."""
        self._interrupted = False
        await self._synthesize_speech(text)

    async def send_text(self, text: str):
        """Send text message directly (for text input)"""
        self._busy = True
        self._interrupted = False
        try:
            self.messages.append({"role": "user", "content": text})
            await self._generate_response()
        finally:
            self._busy = False

    async def execute_tool(self, tool_name: str, parameters: dict) -> str:
        """Execute a tool and return result"""
        if self.tool_executor:
            fc = self._FnCall(tool_name, parameters, f"ollama-manual-{tool_name}")
            fn_response = await self.tool_executor(fc)
            return self._extract_result_text(fn_response)
        return "Ejecución de herramientas no configurada"

    def reset_conversation(self):
        """Clear conversation history"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.ui_logger("[Ollama] Conversation reset")
