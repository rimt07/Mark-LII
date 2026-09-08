# Ollama Backend Setup

MARK LII now supports running completely offline using Ollama as a local LLM alternative to Gemini Live API.

## Architecture

The Ollama backend provides a fully local voice-to-voice interaction pipeline:

1. **Speech-to-Text (STT)**: OpenAI Whisper running locally
2. **Language Model**: Ollama with your choice of model (llama3.2, mistral, etc.)
3. **Text-to-Speech (TTS)**: Microsoft Edge TTS (requires internet for synthesis) or Piper TTS (fully offline)

## Prerequisites

### 1. Install Ollama

Download and install Ollama from [ollama.ai](https://ollama.ai)

**Windows:**
```bash
# Download installer from https://ollama.ai/download/windows
# Run the installer
```

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Pull a Model

```bash
# Recommended: Llama 3.2 (3B parameters, good for voice assistant)
ollama pull llama3.2

# Alternatives:
ollama pull mistral        # 7B, more capable but slower
ollama pull phi3          # 3.8B, Microsoft model
ollama pull gemma2:2b     # 2B, very fast
```

### 3. Install Python Dependencies

```bash
# Install Ollama backend dependencies
pip install ollama openai-whisper edge-tts

# For fully offline TTS (recommended):
pip install kokoro-onnx soundfile

# For Windows: you may need ffmpeg for Whisper
# Download from https://ffmpeg.org/download.html or via chocolatey:
choco install ffmpeg
```

### 4. Download Kokoro TTS Models (Optional - For Offline TTS)

If using Kokoro TTS for fully offline operation:

```bash
# Create models directory
mkdir models

# Download Kokoro ONNX model (~180MB)
curl -L -o models/kokoro-v1.0.onnx https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx

# Download voices file (~45MB)
curl -L -o models/voices-v1.0.bin https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin
```

**Windows PowerShell:**
```powershell
New-Item -ItemType Directory -Force models
Invoke-WebRequest -Uri "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx" -OutFile "models/kokoro-v1.0.onnx"
Invoke-WebRequest -Uri "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin" -OutFile "models/voices-v1.0.bin"
```

## Configuration

Edit `config/llm_config.json`:

```json
{
  "backend": "ollama",
  "ollama": {
    "enabled": true,
    "base_url": "http://localhost:11434",
    "model": "llama3.2:latest",
    "temperature": 0.7,
    "stream": true,
    "stt": {
      "engine": "whisper",
      "model": "base",
      "language": "auto"
    },
    "tts": {
      "engine": "edge",
      "voice": "en-US-AriaNeural",
      "speed": 1.0
    }
  }
}
```

### Configuration Options

**Ollama Settings:**
- `base_url`: Ollama server URL (default: `http://localhost:11434`)
- `model`: Model name from `ollama list` (e.g., `llama3.2:latest`, `mistral`)
- `temperature`: Response randomness (0.0-1.0, default: 0.7)

**STT (Speech-to-Text):**
- `engine`: Only `"whisper"` supported currently
- `model`: Whisper model size: `tiny`, `base`, `small`, `medium`, `large`
  - `tiny`: Fastest, least accurate (~75MB)
  - `base`: Good balance (~150MB) **← Recommended**
  - `small`: Better accuracy (~500MB)
  - `medium`: High accuracy (~1.5GB)
  - `large`: Best accuracy (~3GB)
- `language`: `"auto"` for auto-detection or ISO code (`"en"`, `"es"`, `"fr"`, etc.)

**TTS (Text-to-Speech):**
- `engine`: TTS engine selection
  - **`"kokoro"`**: Fully offline, high-quality ONNX-based TTS (recommended for privacy)
  - **`"edge"`**: Microsoft Edge TTS (requires internet, good quality)
  - **`"none"`**: Text-only mode (no speech synthesis)
- `voice`: Voice selection (depends on engine)
  - **Kokoro voices**: `af_sarah`, `am_adam`, `bf_emma`, `bm_george`, etc.
  - **Edge TTS voices**: See [available voices](https://speech.microsoft.com/portal/voicegallery)
  - **Voice blending** (Kokoro only): `"af_sarah:60,am_adam:40"` for 60-40 mix
- `speed`: Speech rate (0.5-2.0, default: 1.0)
- `lang`: Language code for Kokoro (`"en-us"`, `"en-gb"`, `"fr-fr"`, `"ja"`, `"cmn"`, etc.)
- `model_path`: Custom path to kokoro-v1.0.onnx (optional, defaults to `./models/kokoro-v1.0.onnx`)
- `voices_path`: Custom path to voices-v1.0.bin (optional, defaults to `./models/voices-v1.0.bin`)

## Usage

### 1. Start Ollama Server

```bash
# In a terminal, start the Ollama service
ollama serve
```

Leave this running in the background.

### 2. Launch MARK LII

```bash
python main.py
```

The application will:
1. Detect `backend: "ollama"` in `config/llm_config.json`
2. Load Whisper STT model (first run downloads ~150MB)
3. Connect to Ollama server
4. Start listening for voice commands

### 3. Verify Backend

Check the activity log in the UI:
```
SYS: Initializing Ollama backend...
[Ollama] Available models: llama3.2:latest
[Ollama] Loading Whisper model: base...
[Ollama] Whisper loaded successfully
[Ollama] Using Edge TTS with voice: en-US-AriaNeural
SYS: Ollama backend ready.
SYS: Microphone active.
```

## Kokoro TTS: Fully Offline Speech Synthesis

Kokoro TTS provides high-quality, fully offline text-to-speech synthesis using ONNX models. It's the recommended TTS engine for privacy-focused deployments.

### Features

- **100% Offline**: No internet required after model download
- **High Quality**: Natural-sounding voices with emotion
- **Fast**: ONNX-optimized inference (~200ms latency)
- **Voice Blending**: Mix two voices for unique sound
- **Multi-Language**: English (US/GB), French, Italian, Japanese, Mandarin

### Available Voices

**American English:**
- `af_sarah`: Female, clear, professional
- `af_nicole`: Female, warm, friendly
- `am_adam`: Male, deep, authoritative
- `am_michael`: Male, neutral, conversational

**British English:**
- `bf_emma`: Female, British accent
- `bm_george`: Male, British accent

**Other Languages:**
- `fr_*`: French voices
- `it_*`: Italian voices
- `ja_*`: Japanese voices
- `cmn_*`: Mandarin Chinese voices

### Voice Blending Example

```json
{
  "tts": {
    "engine": "kokoro",
    "voice": "af_sarah:70,am_adam:30",
    "speed": 1.0
  }
}
```

This creates a 70% feminine, 30% masculine voice blend for unique character.

### Configuration Examples

**Fully offline setup (Kokoro):**
```json
{
  "backend": "ollama",
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "llama3.2:latest",
    "stt": {
      "engine": "whisper",
      "model": "base"
    },
    "tts": {
      "engine": "kokoro",
      "voice": "af_sarah",
      "speed": 1.0,
      "lang": "en-us"
    }
  }
}
```

**Edge TTS setup (requires internet):**
```json
{
  "tts": {
    "engine": "edge",
    "voice": "en-US-AriaNeural",
    "speed": 1.0
  }
}
```

## Performance Tuning

### LLM Model Selection

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| `gemma2:2b` | 1.6GB | ★★★★★ | ★★★ | Fast responses, simple tasks |
| `llama3.2:latest` | 2.0GB | ★★★★ | ★★★★ | Balanced, recommended |
| `phi3` | 2.3GB | ★★★★ | ★★★★ | Microsoft model, good reasoning |
| `mistral` | 4.1GB | ★★★ | ★★★★★ | Best quality, slower |

### Whisper Model Selection

- **Low-end PC**: `tiny` or `base`
- **Mid-range PC**: `base` or `small` (recommended)
- **High-end PC**: `medium` or `large`

### GPU Acceleration

Ollama automatically uses GPU if available. To verify:

```bash
ollama list
# Should show your model
# GPU memory usage will show in Task Manager (NVIDIA) or Activity Monitor (Mac)
```

## Troubleshooting

### "Cannot connect to Ollama"

1. Ensure Ollama is running: `ollama serve`
2. Test connection: `ollama list` should show installed models
3. Check `base_url` in `config/llm_config.json` matches Ollama server address

### "Model not found"

```bash
# Pull the model specified in llm_config.json
ollama pull llama3.2
```

### Slow Transcription

- Use smaller Whisper model: `"model": "tiny"` or `"model": "base"`
- Check CPU usage during transcription
- Consider upgrading to `base` or `small` for better accuracy

### No Audio Output (Kokoro TTS)

1. **Check model files exist:**
   ```bash
   ls models/
   # Should show kokoro-v1.0.onnx and voices-v1.0.bin
   ```

2. **Verify kokoro-onnx installation:**
   ```bash
   pip list | grep kokoro
   # Should show kokoro-onnx
   ```

3. **Test Kokoro directly:**
   ```python
   from kokoro_onnx import Kokoro
   kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")
   samples, sr = kokoro.create("Hello world", voice="af_sarah", lang="en-us")
   print(f"Generated {len(samples)} samples at {sr}Hz")
   ```

4. **Fallback to Edge TTS:**
   Change `"engine": "edge"` in config if Kokoro fails

### No Audio Output (Edge TTS)

- Edge TTS requires internet connection
- Check speaker/output device in MARK LII settings
- Verify Edge TTS works: `edge-tts --text "Hello" --write-media test.mp3`

### High Memory Usage

- Whisper `large` model uses ~3GB RAM
- Ollama model + context can use 2-8GB RAM
- Total: 5-11GB RAM recommended for smooth operation
- Use smaller models on systems with <8GB RAM

## Switching Back to Gemini

Edit `config/llm_config.json`:

```json
{
  "backend": "gemini",
  "gemini": {
    "model": "models/gemini-2.5-flash-native-audio-preview-12-2025",
    "api_version": "v1alpha"
  }
}
```

Restart MARK LII.

## Limitations

Current Ollama backend limitations:

1. **No Vision Support**: Camera/screen capture not yet integrated
2. **No Streaming Audio**: Responses synthesized after completion (not real-time like Gemini)
3. **Tool Execution**: Full tool support, but slower than Gemini
4. **Context Window**: Limited by model (4K-32K tokens vs Gemini's 1M+)

## Fully Offline Operation

With Kokoro TTS, MARK LII can run **100% offline**:

✅ **Ollama**: Local LLM (no API calls)  
✅ **Whisper**: Local STT (no cloud transcription)  
✅ **Kokoro**: Local TTS (no internet synthesis)

This provides:
- **Privacy**: All data stays on your machine
- **Reliability**: No dependency on cloud services
- **Speed**: No network latency for STT/TTS
- **Cost**: No API usage fees

## Future Enhancements

- [x] Kokoro TTS integration (fully offline) ✅ **DONE**
- [ ] Vision model integration (LLaVA, BakLLaVA)
- [ ] Streaming audio generation
- [ ] Context window management
- [ ] Multi-modal input (images + voice)
- [ ] Voice cloning support

## Resources

- [Ollama Documentation](https://github.com/ollama/ollama/tree/main/docs)
- [Ollama Model Library](https://ollama.ai/library)
- [Whisper Documentation](https://github.com/openai/whisper)
- [Kokoro TTS GitHub](https://github.com/nazdridoy/kokoro-tts)
- [Kokoro ONNX PyPI](https://pypi.org/project/kokoro-onnx/)
- [Edge TTS Voices](https://speech.microsoft.com/portal/voicegallery)
