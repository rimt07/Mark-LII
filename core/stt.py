"""
Speech-to-Text engines for MARK XL.

Whisper  – offline transcription via faster-whisper (VAD-buffered)
Vosk     – offline streaming transcription (lighter)
"""
import json
import os
import site
from typing import Callable

import numpy as np


def _ensure_cuda_dlls() -> None:
    """Register NVIDIA pip-package DLL dirs on Windows for ctranslate2/CUDA."""
    if os.name != "nt":
        return
    import ctypes

    search = list(site.getsitepackages())
    try:
        search.append(site.getusersitepackages())
    except Exception:
        pass

    bin_dirs: list[str] = []
    for base in search:
        nvidia = os.path.join(base, "nvidia")
        if not os.path.isdir(nvidia):
            continue
        for sub in os.listdir(nvidia):
            binp = os.path.join(nvidia, sub, "bin")
            if os.path.isdir(binp):
                bin_dirs.append(binp)

    if not bin_dirs:
        return

    path_prefix = os.pathsep.join(bin_dirs)
    os.environ["PATH"] = path_prefix + os.pathsep + os.environ.get("PATH", "")
    for binp in bin_dirs:
        try:
            os.add_dll_directory(binp)
        except Exception:
            pass

    # ctranslate2 loads cuBLAS lazily on first GPU encode; preload so Windows
    # resolves dependencies before faster-whisper imports the CUDA backend.
    for dll in ("cublas64_12.dll", "cublasLt64_12.dll"):
        for binp in bin_dirs:
            dll_path = os.path.join(binp, dll)
            if os.path.isfile(dll_path):
                try:
                    ctypes.CDLL(dll_path)
                except Exception:
                    pass
                break


def _cuda_available() -> bool:
    """True when a CUDA runtime is likely usable (torch or NVIDIA pip libs)."""
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    for base in list(site.getsitepackages()) + ([site.getusersitepackages()] if site.getusersitepackages() else []):
        dll = os.path.join(base, "nvidia", "cublas", "bin", "cublas64_12.dll")
        if os.path.isfile(dll):
            return True
    return False


if os.name == "nt":
    _ensure_cuda_dlls()


def _resolve_device(device: str | None) -> str:
    if device and device.strip().lower() in ("cuda", "cpu"):
        return device.strip().lower()
    return "cuda" if _cuda_available() else "cpu"


class WhisperSTT:
    """Offline transcription using faster-whisper."""

    def __init__(
        self,
        model_name: str = "base",
        language: str | None = None,
        device: str | None = None,
        logger: Callable[[str], None] | None = None,
    ):
        self._log = logger or print
        device = _resolve_device(device)
        compute = "float16" if device == "cuda" else "int8"

        if device == "cuda":
            _ensure_cuda_dlls()

        from faster_whisper import WhisperModel

        self._log(f"[STT] Loading Whisper '{model_name}' on {device}…")
        try:
            self._model = WhisperModel(model_name, device=device, compute_type=compute)
        except Exception as first_err:
            if device == "cuda":
                self._log(f"[STT] Whisper GPU load failed ({first_err}); using CPU.")
                device, compute = "cpu", "int8"
                self._model = WhisperModel(model_name, device=device, compute_type=compute)
            else:
                self._load_with_download(model_name, device, compute, first_err)

        self._language = None if (not language or language.strip().lower() == "auto") else language.strip().lower()
        self.device = device
        self._log(f"[STT] Whisper '{model_name}' ready ({device})")

    def _load_with_download(self, model_name: str, device: str, compute: str, first_err: Exception) -> None:
        from faster_whisper import WhisperModel

        err_text = str(first_err).lower()
        offline_keywords = (
            "offline", "not found", "cache", "localentry",
            "does not exist", "outgoing", "local_files_only",
        )
        if not any(k in err_text for k in offline_keywords):
            raise first_err

        self._log(
            f"[STT] Whisper '{model_name}' not in local cache — "
            "downloading (one-time, internet required)…"
        )
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        os.environ.pop("HF_DATASETS_OFFLINE", None)
        try:
            self._model = WhisperModel(model_name, device=device, compute_type=compute)
        except Exception as dl_err:
            raise RuntimeError(
                f"Whisper '{model_name}' model download failed.\n"
                "Internet access is required the first time to download the speech model (~75–290 MB).\n"
                "After the first download it runs fully offline.\n"
                f"Details: {dl_err}"
            ) from dl_err

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        """Transcribe float32 mono 16 kHz audio. Returns (text, detected_language)."""
        try:
            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=1,
                best_of=1,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(s.text for s in segments).strip()
            return text, info.language
        except Exception as e:
            self._log(f"[STT] Transcription error: {e}")
            raise


class VoskSTT:
    """Streaming transcription using Vosk."""

    def __init__(self, model_path: str | None = None, language: str = "en-us"):
        from vosk import Model, KaldiRecognizer
        print("[STT] Loading Vosk model…")
        if model_path:
            model = Model(model_path)
        else:
            lang = language.strip().lower() if language and language.strip().lower() != "auto" else "en-us"
            model = Model(lang=lang)
        self._rec = KaldiRecognizer(model, 16000)
        print("[STT] Vosk ready.")

    def process_chunk(self, audio_bytes: bytes) -> tuple[str, bool]:
        """Feed raw int16 LE PCM bytes. Returns (text, is_final)."""
        if self._rec.AcceptWaveform(audio_bytes):
            result = json.loads(self._rec.Result())
            return result.get("text", ""), True
        partial = json.loads(self._rec.PartialResult())
        return partial.get("partial", ""), False
