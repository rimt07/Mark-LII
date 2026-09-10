"""
Ollama Backend for MARK LII

Local LLM backend using Ollama + Whisper STT + Piper TTS.
Provides voice-to-voice interaction without cloud dependencies.
"""
import asyncio
import json
import os
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

import numpy as np


class OllamaBackend:
    """
    Local voice assistant backend using:
    - Ollama for LLM inference
    - Whisper for speech-to-text
    - Piper/edge-tts for text-to-speech
    """

    def __init__(self, config: dict, ui_logger: Callable, speak_callback: Callable):
        self.config = config
        self.ui_logger = ui_logger
        self.speak_callback = speak_callback

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
                    import whisper
                    model_size = stt_config.get("model", "base")

                    # Pick the device. Honour an explicit config override
                    # ("cuda"/"cpu"); otherwise auto-detect CUDA. On CPU, Whisper
                    # warns "FP16 is not supported on CPU; using FP32" and runs
                    # noticeably slower — moving to the GPU (when a CUDA-enabled
                    # torch is installed) removes that warning and speeds up STT.
                    _dev = (stt_config.get("device", "") or "").strip().lower()
                    if _dev not in ("cuda", "cpu"):
                        try:
                            import torch
                            _dev = "cuda" if torch.cuda.is_available() else "cpu"
                        except Exception:
                            _dev = "cpu"

                    self.ui_logger(f"[Ollama] Loading Whisper model: {model_size} on {_dev}...")
                    try:
                        self.stt_engine = whisper.load_model(model_size, device=_dev)
                    except Exception as _e:
                        # A CUDA load can fail (out of VRAM, driver mismatch);
                        # never let that take STT down — retry on CPU.
                        if _dev == "cuda":
                            self.ui_logger(f"[Ollama] Whisper GPU load failed ({_e}); using CPU.")
                            self.stt_engine = whisper.load_model(model_size, device="cpu")
                        else:
                            raise
                    self.ui_logger("[Ollama] Whisper loaded successfully")
                except ImportError:
                    self.ui_logger("[Ollama] ERROR: 'whisper' package not installed. Run: pip install -U openai-whisper")
                    return False

            # Initialize TTS
            tts_config = self.config.get("tts", {})
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
                        logger=self.ui_logger
                    )
                    if self.tts_kokoro.initialize():
                        self.ui_logger(f"[Ollama] Using Kokoro TTS (offline) with voice: {tts_config.get('voice', 'af_sarah')}")
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

            # Save to temporary WAV file for Whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_np * 32768).astype(np.int16).tobytes())

            # Transcribe with Whisper. Whisper does NOT accept the literal
            # "auto" as a language — autodetection requires language=None. The
            # config default of "auto" (and any empty value) is therefore mapped
            # to None here, so Whisper detects the spoken language per utterance.
            _lang = (self.config.get("stt", {}).get("language", "") or "").strip().lower()
            _whisper_lang = None if _lang in ("", "auto") else _lang
            _t0 = time.monotonic()
            result = await asyncio.to_thread(
                self.stt_engine.transcribe,
                tmp_path,
                language=_whisper_lang
            )
            _elapsed = time.monotonic() - _t0

            os.unlink(tmp_path)

            user_text = result.get("text", "").strip()
            if self._vad_debug:
                _detected = result.get("language", "?")
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

    async def _generate_response(self):
        """
        Generate a response from Ollama, executing any tools the model calls.

        Flow: send the conversation (with the tool list) to Ollama; if the reply
        contains tool_calls, run each via the app's tool_executor, feed the
        results back as role="tool" messages, and ask the model again — looping
        until it produces a plain text answer or a safety cap is hit. Streaming
        is disabled while tools are enabled because tool_calls arrive in the
        final message object, not in streamed content deltas.
        """
        try:
            self.ui_logger("[Ollama] Generating response...")

            use_tools = bool(self.ollama_tools and self.tool_executor)
            max_tool_rounds = 5   # safety cap against tool-call loops
            response_text = ""

            for _round in range(max_tool_rounds + 1):
                kwargs = dict(model=self.ollama_model, messages=self.messages)
                if use_tools:
                    kwargs["tools"] = self.ollama_tools

                resp = await self.ollama_client.chat(**kwargs)

                # Normalise message access across ollama-python versions.
                msg = resp.get("message", {}) if isinstance(resp, dict) else getattr(resp, "message", {})
                if not isinstance(msg, dict):
                    msg = {
                        "role": getattr(msg, "role", "assistant"),
                        "content": getattr(msg, "content", "") or "",
                        "tool_calls": getattr(msg, "tool_calls", None),
                    }

                content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls") or []

                if not tool_calls:
                    # Plain answer — done.
                    response_text = content
                    if content:
                        self.messages.append({"role": "assistant", "content": content})
                    break

                # The model wants to call tools. Record its (possibly empty)
                # assistant turn with the tool_calls so the context is coherent.
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
                    # Ollama may hand arguments back as a JSON string.
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args) if fn_args.strip() else {}
                        except Exception:
                            fn_args = {}

                    self.ui_logger(f"[Ollama] 🔧 tool call: {fn_name} {fn_args}")

                    if not fn_name:
                        result_text = "Tool call had no name."
                    else:
                        try:
                            fc = self._FnCall(fn_name, fn_args, f"ollama-{_round}-{fn_name}")
                            fn_response = await self.tool_executor(fc)
                            result_text = self._extract_result_text(fn_response)
                        except Exception as e:
                            result_text = f"Tool '{fn_name}' failed: {e}"
                            self.ui_logger(f"[Ollama] tool error: {e}")

                    if self._vad_debug:
                        self.ui_logger(f"[Ollama] 📤 {fn_name} → {str(result_text)[:120]}")

                    # Feed the tool result back for the next round.
                    self.messages.append({
                        "role": "tool",
                        "name": fn_name,
                        "content": str(result_text),
                    })
            else:
                # Loop exhausted without a final text answer.
                self.ui_logger("[Ollama] Tool loop hit its round cap; answering with what we have.")

            if not response_text:
                return

            self.ui_logger(f"[Ollama] Assistant: {response_text}")

            # Synthesize speech
            await self._synthesize_speech(response_text)

        except Exception as e:
            self.ui_logger(f"[Ollama] Generation error: {e}")
            import traceback
            traceback.print_exc()

    async def _generate_response_OLD(self):
        """Generate response from Ollama"""
        try:
            self.ui_logger("[Ollama] Generating response...")

            # Call Ollama with streaming
            response_text = ""
            async for chunk in await self.ollama_client.chat(
                model=self.ollama_model,
                messages=self.messages,
                stream=True,
            ):
                content = chunk.get('message', {}).get('content', '')
                response_text += content
                # Could stream to UI here if desired

            if not response_text:
                return

            self.ui_logger(f"[Ollama] Assistant: {response_text}")

            # Add to conversation history
            self.messages.append({"role": "assistant", "content": response_text})

            # Synthesize speech
            await self._synthesize_speech(response_text)

        except Exception as e:
            self.ui_logger(f"[Ollama] Generation error: {e}")
            import traceback
            traceback.print_exc()

    async def _play_audio_file(self, path: str) -> bool:
        """
        Play a synthesized audio file (wav from Kokoro, mp3 from Edge) on the
        user's chosen speaker, off the event loop so synthesis playback never
        blocks the asyncio loop that drives the mic and Ollama.

        Returns True if playback ran, False if it could not (caller then falls
        back to text-only). Never raises.
        """
        def _blocking_play() -> bool:
            try:
                import sounddevice as sd
                import soundfile as sf
            except Exception as e:
                self.ui_logger(f"[Ollama] TTS playback deps missing: {e}")
                return False

            try:
                data, sr = sf.read(path, dtype="float32")
            except Exception as e:
                self.ui_logger(f"[Ollama] Could not decode TTS audio ({e}).")
                return False

            duration = len(data) / float(sr) if sr else 0.0

            # Build the device try-order. The chosen speaker is tried first, but
            # some Windows host APIs (notably PortAudio DirectSound output) report
            # success while emitting NOTHING — sd.play + sd.wait return in ~0 ms
            # for seconds of audio (the "silent sink" the startup probe warns
            # about). So after each attempt we check that playback actually took
            # roughly real time; if it returned far too fast, we treat the device
            # as silent and fall through to the next candidate. The system
            # default (device=None) was verified to play in real time.
            candidates = []
            try:
                from core import audio_devices
                from memory.config_manager import get_output_device
                _resolved = audio_devices.resolve(get_output_device(), "output")
            except Exception:
                _resolved = None
            if _resolved is not None:
                candidates.append(_resolved)
            candidates.append(None)  # system default — known-good real-time sink

            import time as _t
            for dev in candidates:
                try:
                    t0 = _t.monotonic()
                    sd.play(data, sr, device=dev)
                    sd.wait()
                    took = _t.monotonic() - t0
                    # Real playback consumes ~duration seconds. If it finished in
                    # well under half that, no audio actually left the device.
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
                    if self._vad_debug:
                        self.ui_logger(f"[Ollama] TTS device={dev!r} failed: {e}")
                    continue

            self.ui_logger("[Ollama] TTS: no working output device produced sound.")
            return False

        return await asyncio.to_thread(_blocking_play)

    async def _synthesize_speech(self, text: str):
        """Convert text to speech and play it on the chosen speaker."""
        if not self.tts_engine:
            # No TTS - just display text
            self.speak_callback(text)
            return

        # Always surface the text in the UI regardless of playback outcome.
        self.speak_callback(text)

        try:
            if self.tts_engine == "kokoro":
                # Generate audio with Kokoro TTS (fully offline)
                audio_path = await self.tts_kokoro.synthesize(text)
                if audio_path:
                    try:
                        await self._play_audio_file(audio_path)
                    finally:
                        try:
                            os.unlink(audio_path)
                        except Exception:
                            pass

            elif self.tts_engine == "edge":
                import edge_tts

                # Generate audio with Edge TTS (requires internet)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    communicate = edge_tts.Communicate(text, self.tts_voice)
                    await communicate.save(tmp_path)
                    await self._play_audio_file(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        except Exception as e:
            self.ui_logger(f"[Ollama] TTS error: {e}")

    async def send_text(self, text: str):
        """Send text message directly (for text input)"""
        self.messages.append({"role": "user", "content": text})
        await self._generate_response()

    async def execute_tool(self, tool_name: str, parameters: dict) -> str:
        """Execute a tool and return result"""
        if self.tool_executor:
            return await self.tool_executor(tool_name, parameters)
        return "Tool execution not configured"

    def reset_conversation(self):
        """Clear conversation history"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.ui_logger("[Ollama] Conversation reset")
