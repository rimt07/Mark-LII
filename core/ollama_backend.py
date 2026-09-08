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
        self.vad_threshold = 0.02  # Voice activity detection threshold

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
                available = [m['name'] for m in models.get('models', [])]
                self.ui_logger(f"[Ollama] Available models: {', '.join(available)}")

                if self.ollama_model not in available:
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
                    self.ui_logger(f"[Ollama] Loading Whisper model: {model_size}...")
                    self.stt_engine = whisper.load_model(model_size)
                    self.ui_logger("[Ollama] Whisper loaded successfully")
                except ImportError:
                    self.ui_logger("[Ollama] ERROR: 'whisper' package not installed. Run: pip install -U openai-whisper")
                    return False

            # Initialize TTS
            tts_config = self.config.get("tts", {})
            tts_engine = tts_config.get("engine", "edge")

            if tts_engine == "edge":
                try:
                    import edge_tts
                    self.tts_engine = "edge"
                    self.tts_voice = tts_config.get("voice", "en-US-AriaNeural")
                    self.ui_logger(f"[Ollama] Using Edge TTS with voice: {self.tts_voice}")
                except ImportError:
                    self.ui_logger("[Ollama] WARNING: 'edge-tts' not installed. Run: pip install edge-tts")
                    self.ui_logger("[Ollama] Falling back to no TTS (text-only mode)")
                    self.tts_engine = None

            # Store system prompt and tools
            self.system_prompt = system_prompt
            self.tools = tools
            self.tool_executor = tool_executor

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
        Buffers audio until silence detected, then transcribes.
        """
        if not self._running:
            return

        # Convert bytes to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Voice Activity Detection (simple energy-based)
        energy = np.abs(audio_np).mean()

        if energy > self.vad_threshold:
            self.audio_buffer.extend(audio_np)
            self.is_listening = True
        elif self.is_listening and len(self.audio_buffer) > 0:
            # Silence detected after speech - transcribe
            await self._transcribe_and_respond()

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

            # Save to temporary WAV file for Whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_np * 32768).astype(np.int16).tobytes())

            # Transcribe with Whisper
            result = await asyncio.to_thread(
                self.stt_engine.transcribe,
                tmp_path,
                language=self.config.get("stt", {}).get("language", "en")
            )

            os.unlink(tmp_path)

            user_text = result.get("text", "").strip()
            if not user_text:
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

    async def _generate_response(self):
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

    async def _synthesize_speech(self, text: str):
        """Convert text to speech and play"""
        if not self.tts_engine:
            # No TTS - just display text
            self.speak_callback(text)
            return

        try:
            if self.tts_engine == "edge":
                import edge_tts

                # Generate audio with Edge TTS
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name

                communicate = edge_tts.Communicate(text, self.tts_voice)
                await communicate.save(tmp_path)

                # Play audio (integrate with existing audio player)
                # For now, just callback with text
                self.speak_callback(text)

                # Clean up
                os.unlink(tmp_path)

        except Exception as e:
            self.ui_logger(f"[Ollama] TTS error: {e}")
            # Fallback to text-only
            self.speak_callback(text)

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
