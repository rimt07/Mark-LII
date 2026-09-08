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

# For Windows: you may need ffmpeg for Whisper
# Download from https://ffmpeg.org/download.html or via chocolatey:
choco install ffmpeg
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
- `engine`: `"edge"` (Microsoft Edge TTS, requires internet) or `"piper"` (fully offline, WIP)
- `voice`: Voice name (Edge TTS voices: see [available voices](https://speech.microsoft.com/portal/voicegallery))
- `speed`: Speech rate (0.5-2.0, default: 1.0)

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

## Performance Tuning

### Model Selection

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

### No Audio Output

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
4. **Internet Required**: Edge TTS requires connection (Piper TTS is WIP)
5. **Context Window**: Limited by model (4K-32K tokens vs Gemini's 1M+)

## Future Enhancements

- [ ] Piper TTS integration (fully offline)
- [ ] Vision model integration (LLaVA, BakLLaVA)
- [ ] Streaming audio generation
- [ ] Context window management
- [ ] Multi-modal input (images + voice)
- [ ] Voice cloning support

## Resources

- [Ollama Documentation](https://github.com/ollama/ollama/tree/main/docs)
- [Ollama Model Library](https://ollama.ai/library)
- [Whisper Documentation](https://github.com/openai/whisper)
- [Edge TTS Voices](https://speech.microsoft.com/portal/voicegallery)
