# Kokoro TTS Models

This directory contains the ONNX models for Kokoro TTS (offline text-to-speech).

## Required Files

To use Kokoro TTS with MARK LII, you need to download two model files:

1. **kokoro-v1.0.onnx** (~180MB) - Main ONNX inference model
2. **voices-v1.0.bin** (~45MB) - Voice embeddings and style data

## Download Instructions

### Option 1: Command Line (Recommended)

**Linux/macOS:**
```bash
cd models/
curl -L -o kokoro-v1.0.onnx https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx
curl -L -o voices-v1.0.bin https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin
```

**Windows PowerShell:**
```powershell
cd models
Invoke-WebRequest -Uri "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx" -OutFile "kokoro-v1.0.onnx"
Invoke-WebRequest -Uri "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin" -OutFile "voices-v1.0.bin"
```

**Using wget:**
```bash
cd models/
wget https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx
wget https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin
```

### Option 2: Manual Download

1. Go to [Kokoro TTS Releases](https://github.com/nazdridoy/kokoro-tts/releases/tag/v1.0.0)
2. Download `kokoro-v1.0.onnx` and `voices-v1.0.bin`
3. Place both files in this `models/` directory

## Directory Structure

After downloading, this directory should contain:

```
models/
├── README.md (this file)
├── kokoro-v1.0.onnx
└── voices-v1.0.bin
```

## Verification

To verify the models were downloaded correctly:

**Linux/macOS:**
```bash
ls -lh models/
# Should show:
# kokoro-v1.0.onnx (~180MB)
# voices-v1.0.bin (~45MB)
```

**Windows:**
```powershell
Get-ChildItem models\ | Format-Table Name, Length
```

## Testing

Test the models with Python:

```python
from kokoro_onnx import Kokoro

kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")

# List available voices
print("Available voices:", kokoro.get_voices())

# Generate test audio
samples, sr = kokoro.create("Hello, this is a test", voice="af_sarah", lang="en-us")
print(f"Generated {len(samples)} samples at {sr}Hz")
```

## Troubleshooting

**"File not found" error:**
- Ensure you're in the correct directory (should see `main.py` in parent directory)
- Check file names exactly match: `kokoro-v1.0.onnx` and `voices-v1.0.bin`
- Verify files are not empty: should be ~180MB and ~45MB respectively

**Download failed:**
- Check your internet connection
- Try alternative download method (curl vs wget vs browser)
- Verify GitHub releases page is accessible

**Permission denied:**
- Ensure write permissions in `models/` directory
- Try running download command with elevated permissions (Windows: Run as Administrator)

## Alternative Locations

If you want to store models elsewhere, specify custom paths in `config/llm_config.json`:

```json
{
  "ollama": {
    "tts": {
      "engine": "kokoro",
      "model_path": "/path/to/custom/kokoro-v1.0.onnx",
      "voices_path": "/path/to/custom/voices-v1.0.bin"
    }
  }
}
```

## License

The Kokoro TTS models are released by the Kokoro TTS project. See [Kokoro TTS License](https://github.com/nazdridoy/kokoro-tts/blob/main/LICENSE) for details.

## Resources

- [Kokoro TTS GitHub](https://github.com/nazdridoy/kokoro-tts)
- [Kokoro TTS Releases](https://github.com/nazdridoy/kokoro-tts/releases)
- [MARK LII Documentation](../docs/OLLAMA_SETUP.md)
