"""
Kokoro TTS Wrapper for MARK LII

Provides high-quality offline text-to-speech using Kokoro ONNX models.
Fully local synthesis with no internet dependency.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional, Callable
import soundfile as sf


class KokoroTTS:
    """
    Wrapper for Kokoro TTS (offline, ONNX-based TTS)
    https://github.com/nazdridoy/kokoro-tts
    """

    def __init__(
        self,
        voice: str = "af_sarah",
        speed: float = 1.0,
        lang: str = "en-us",
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
        logger: Optional[Callable] = None
    ):
        """
        Initialize Kokoro TTS engine.

        Args:
            voice: Voice ID (e.g., "af_sarah", "am_adam") or blended voices
            speed: Speech rate multiplier (0.5-2.0)
            lang: Language code (en-us, en-gb, fr-fr, ja, cmn, etc.)
            model_path: Path to kokoro-v1.0.onnx (default: ./models/kokoro-v1.0.onnx)
            voices_path: Path to voices-v1.0.bin (default: ./models/voices-v1.0.bin)
            logger: Optional logging function
        """
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self.logger = logger or print

        # Default model paths
        base_dir = Path(__file__).parent.parent
        models_dir = base_dir / "models"
        models_dir.mkdir(exist_ok=True)

        self.model_path = model_path or str(models_dir / "kokoro-v1.0.onnx")
        self.voices_path = voices_path or str(models_dir / "voices-v1.0.bin")

        self.kokoro = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Load Kokoro ONNX model and voices.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if kokoro_onnx is installed
            try:
                from kokoro_onnx import Kokoro
            except ImportError:
                self.logger("[Kokoro] ERROR: 'kokoro_onnx' package not installed")
                self.logger("[Kokoro] Install with: pip install kokoro-onnx")
                return False

            # Check if model files exist
            if not os.path.exists(self.model_path):
                self.logger(f"[Kokoro] ERROR: Model file not found: {self.model_path}")
                self.logger("[Kokoro] Download from: https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx")
                self.logger(f"[Kokoro] Place in: {Path(self.model_path).parent}")
                return False

            if not os.path.exists(self.voices_path):
                self.logger(f"[Kokoro] ERROR: Voices file not found: {self.voices_path}")
                self.logger("[Kokoro] Download from: https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin")
                self.logger(f"[Kokoro] Place in: {Path(self.voices_path).parent}")
                return False

            # Load Kokoro model
            self.logger(f"[Kokoro] Loading model from {self.model_path}")
            self.kokoro = Kokoro(self.model_path, self.voices_path)

            # Validate language
            supported_langs = set(self.kokoro.get_languages())
            if self.lang not in supported_langs:
                self.logger(f"[Kokoro] WARNING: Language '{self.lang}' not in {supported_langs}")
                self.logger(f"[Kokoro] Falling back to 'en-us'")
                self.lang = "en-us"

            # Validate and prepare voice
            self.voice = self._validate_voice(self.voice)

            self._initialized = True
            self.logger(f"[Kokoro] Initialized with voice '{self.voice}', speed {self.speed}, lang '{self.lang}'")
            return True

        except Exception as e:
            self.logger(f"[Kokoro] Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _validate_voice(self, voice: str):
        """
        Validate voice selection and handle blending.

        Supports:
        - Single voice: "af_sarah"
        - Blended voices: "af_sarah:60,am_adam:40" or "af_sarah,am_adam"

        Returns:
            Voice string or numpy array (blended voice style)
        """
        import numpy as np

        supported_voices = set(self.kokoro.get_voices())

        # Handle voice blending
        if ',' in voice:
            voices = []
            weights = []

            for pair in voice.split(','):
                if ':' in pair:
                    v, w = pair.strip().split(':')
                    voices.append(v.strip())
                    weights.append(float(w.strip()))
                else:
                    voices.append(pair.strip())
                    weights.append(50.0)  # Default 50-50 blend

            if len(voices) != 2:
                raise ValueError("Voice blending requires exactly 2 voices")

            # Validate both voices
            for v in voices:
                if v not in supported_voices:
                    raise ValueError(f"Unsupported voice: {v}")

            # Normalize weights to sum to 100
            total = sum(weights)
            if total != 100:
                weights = [w * (100 / total) for w in weights]

            # Create blended voice style
            style1 = self.kokoro.get_voice_style(voices[0])
            style2 = self.kokoro.get_voice_style(voices[1])
            blend = np.add(style1 * (weights[0] / 100), style2 * (weights[1] / 100))

            self.logger(f"[Kokoro] Blended voice: {voices[0]}@{weights[0]:.0f}% + {voices[1]}@{weights[1]:.0f}%")
            return blend

        # Single voice validation
        if voice not in supported_voices:
            raise ValueError(f"Unsupported voice: {voice}. Available: {sorted(supported_voices)}")

        return voice

    async def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Synthesize speech from text.

        Args:
            text: Text to speak
            output_path: Optional path to save audio file (if None, generates temp file)

        Returns:
            Path to generated audio file, or None on error
        """
        if not self._initialized:
            self.logger("[Kokoro] Not initialized")
            return None

        try:
            # Generate audio samples
            samples, sample_rate = self.kokoro.create(
                text,
                voice=self.voice,
                speed=self.speed,
                lang=self.lang
            )

            # Create output file
            if output_path is None:
                fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="kokoro_")
                os.close(fd)

            # Save audio
            sf.write(output_path, samples, sample_rate)

            return output_path

        except Exception as e:
            self.logger(f"[Kokoro] Synthesis error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_voices(self):
        """List all available voices"""
        if not self._initialized:
            return []
        return sorted(self.kokoro.get_voices())

    def get_languages(self):
        """List all supported languages"""
        if not self._initialized:
            return []
        return sorted(self.kokoro.get_languages())

    def set_voice(self, voice: str):
        """Change voice"""
        if self._initialized:
            self.voice = self._validate_voice(voice)
            self.logger(f"[Kokoro] Voice changed to: {self.voice}")

    def set_speed(self, speed: float):
        """Change speech speed (0.5-2.0)"""
        self.speed = max(0.5, min(2.0, speed))
        self.logger(f"[Kokoro] Speed changed to: {self.speed}")

    def set_language(self, lang: str):
        """Change language"""
        if self._initialized:
            supported_langs = set(self.kokoro.get_languages())
            if lang in supported_langs:
                self.lang = lang
                self.logger(f"[Kokoro] Language changed to: {self.lang}")
            else:
                self.logger(f"[Kokoro] Unsupported language: {lang}")
