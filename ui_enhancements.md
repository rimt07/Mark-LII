# UI Enhancements for Ollama/Kokoro Integration

## Mejoras Necesarias en ui.py

### 1. Indicador de Backend Activo (Gemini vs Ollama)
**Ubicación:** Barra de estado superior (junto a indicador MCP)

```python
# En MainWindow.__init__ agregar:
self._backend_label = QLabel("Backend: Gemini Live")
self._backend_label.setFont(QFont("Segoe UI", 8))
self._backend_label.setStyleSheet("color: #888; background: transparent;")
top_right_layout.addWidget(self._backend_label)

# Método para actualizar:
def update_backend_status(self, backend: str, details: str = ""):
    """
    backend: "gemini" | "ollama"
    details: información adicional (modelo, etc.)
    """
    if backend == "gemini":
        icon = "☁"  # Cloud
        color = "#4A9EFF"
        text = "Gemini Live"
    else:  # ollama
        icon = "⚙"  # Gear for local
        color = "#00C853"
        text = f"Ollama ({details})" if details else "Ollama"
    
    self._backend_label.setText(f"{icon} {text}")
    self._backend_label.setStyleSheet(f"color: {color}; background: transparent;")
    self._backend_label.setToolTip(f"Backend: {text}")
```

### 2. Indicador de TTS Engine (Edge vs Kokoro vs None)
**Ubicación:** Debajo del indicador de backend o en barra de estado

```python
# En MainWindow.__init__ agregar:
self._tts_label = QLabel("TTS: --")
self._tts_label.setFont(QFont("Segoe UI", 7))
self._tts_label.setStyleSheet("color: #666; background: transparent;")
top_right_layout.addWidget(self._tts_label)

# Método para actualizar:
def update_tts_status(self, engine: str, voice: str = ""):
    """
    engine: "kokoro" | "edge" | "none"
    voice: nombre de la voz activa
    """
    icons = {
        "kokoro": "🔇",  # Speaker with no internet
        "edge": "🔊",    # Speaker (requires internet)
        "none": "🔕"     # No sound
    }
    colors = {
        "kokoro": "#00C853",  # Green (offline)
        "edge": "#FFA726",    # Orange (online)
        "none": "#666"        # Gray
    }
    
    icon = icons.get(engine, "")
    color = colors.get(engine, "#666")
    
    if engine == "none":
        text = "Text Only"
    elif voice:
        text = f"{engine.title()}: {voice}"
    else:
        text = engine.title()
    
    self._tts_label.setText(f"{icon} {text}")
    self._tts_label.setStyleSheet(f"color: {color}; background: transparent;")
    
    tooltip = {
        "kokoro": "Kokoro TTS (Fully Offline)",
        "edge": "Edge TTS (Requires Internet)",
        "none": "Text-only mode (No TTS)"
    }.get(engine, "")
    self._tts_label.setToolTip(tooltip)
```

### 3. Indicador de Modo Offline
**Ubicación:** Badge visible cuando está 100% offline

```python
# En MainWindow.__init__ agregar:
self._offline_badge = QLabel("● OFFLINE")
self._offline_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
self._offline_badge.setStyleSheet("""
    color: #00C853;
    background: rgba(0, 200, 83, 0.15);
    border: 1px solid #00C853;
    border-radius: 8px;
    padding: 2px 8px;
""")
self._offline_badge.hide()  # Oculto por defecto
top_right_layout.addWidget(self._offline_badge)

# Método para actualizar:
def update_offline_mode(self, is_offline: bool):
    """Muestra badge verde cuando está 100% offline"""
    if is_offline:
        self._offline_badge.show()
        self._offline_badge.setToolTip(
            "100% Offline Mode\n"
            "✓ Ollama (Local LLM)\n"
            "✓ Whisper (Local STT)\n"
            "✓ Kokoro (Local TTS)"
        )
    else:
        self._offline_badge.hide()
```

### 4. Logs Coloreados para Ollama/Kokoro
**Ubicación:** Activity Log con colores distintivos

```python
# En write_log, agregar detección de prefijos:
def write_log(self, text: str):
    """Enhanced log with color coding for different backends"""
    if text.startswith("[Ollama]"):
        color = "#00C853"  # Green for Ollama
    elif text.startswith("[Kokoro]"):
        color = "#00BCD4"  # Cyan for Kokoro TTS
    elif text.startswith("[Whisper]"):
        color = "#FF9800"  # Orange for Whisper STT
    elif text.startswith("[Gemini]"):
        color = "#4A9EFF"  # Blue for Gemini
    else:
        color = None  # Default color
    
    # Pass color to log widget
    self._log_sig.emit(text, color)
```

### 5. Selector de Backend en Settings
**Ubicación:** Panel de configuración (Settings Drawer)

```python
# En _build_settings_panel agregar:
backend_section = QVBoxLayout()

backend_label = QLabel("Backend:")
backend_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
backend_section.addWidget(backend_label)

self._backend_combo = QComboBox()
self._backend_combo.addItems(["Gemini Live", "Ollama (Local)"])
self._backend_combo.setCurrentText(current_backend)
self._backend_combo.currentTextChanged.connect(self._on_backend_change)
backend_section.addWidget(self._backend_combo)

# Agregar info tooltip
info_label = QLabel("⚠ Requires restart to take effect")
info_label.setFont(QFont("Segoe UI", 7))
info_label.setStyleSheet("color: #FFA726;")
backend_section.addWidget(info_label)

settings_layout.addLayout(backend_section)

# Handler:
def _on_backend_change(self, backend_text):
    """Save backend preference and notify user"""
    backend = "gemini" if "Gemini" in backend_text else "ollama"
    
    # Update config/llm_config.json
    try:
        import json
        config_path = Path(__file__).parent / "config" / "llm_config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config["backend"] = backend
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        self.write_log(f"SYS: Backend changed to {backend_text}. Restart MARK LII to apply.")
    except Exception as e:
        self.write_log(f"ERROR: Failed to save backend preference: {e}")
```

### 6. Selector de TTS Engine (Solo para Ollama)
**Ubicación:** Panel de configuración, visible solo si backend es Ollama

```python
# En _build_settings_panel agregar (después de backend selector):
tts_section = QVBoxLayout()

tts_label = QLabel("TTS Engine (Ollama only):")
tts_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
tts_section.addWidget(tts_label)

self._tts_combo = QComboBox()
self._tts_combo.addItems([
    "Kokoro (Offline, Best Quality)",
    "Edge TTS (Requires Internet)",
    "None (Text Only)"
])
self._tts_combo.setCurrentText(current_tts)
self._tts_combo.currentTextChanged.connect(self._on_tts_change)
tts_section.addWidget(self._tts_combo)

# Enable/disable based on backend
self._tts_combo.setEnabled(backend == "ollama")

settings_layout.addLayout(tts_section)
```

### 7. Indicador de Estado de Modelos Kokoro
**Ubicación:** Activity Log al iniciar

```python
# En el inicio de Ollama backend, agregar verificación de modelos:
def check_kokoro_models(self):
    """Check if Kokoro models are downloaded"""
    model_path = Path("models/kokoro-v1.0.onnx")
    voices_path = Path("models/voices-v1.0.bin")
    
    if not model_path.exists() or not voices_path.exists():
        self.write_log("[Kokoro] ⚠ Models not found!")
        self.write_log("[Kokoro] Download instructions: See models/README.md")
        self.write_log("[Kokoro] Quick download:")
        self.write_log("[Kokoro]   curl -L -o models/kokoro-v1.0.onnx https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx")
        self.write_log("[Kokoro]   curl -L -o models/voices-v1.0.bin https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin")
        return False
    
    # Check file sizes
    model_size = model_path.stat().st_size / (1024 * 1024)  # MB
    voices_size = voices_path.stat().st_size / (1024 * 1024)
    
    if model_size < 150 or voices_size < 40:
        self.write_log(f"[Kokoro] ⚠ Model files incomplete (model: {model_size:.1f}MB, voices: {voices_size:.1f}MB)")
        return False
    
    self.write_log(f"[Kokoro] ✓ Models loaded ({model_size:.1f}MB + {voices_size:.1f}MB)")
    return True
```

## Resumen de Cambios Necesarios

### Archivos a Modificar:
1. **ui.py**
   - Agregar `_backend_label` y `update_backend_status()`
   - Agregar `_tts_label` y `update_tts_status()`
   - Agregar `_offline_badge` y `update_offline_mode()`
   - Mejorar `write_log()` con colores para [Ollama]/[Kokoro]/[Whisper]
   - Agregar selectores de backend/TTS en settings panel

2. **main.py**
   - Llamar `ui.update_backend_status()` al iniciar
   - Llamar `ui.update_tts_status()` después de inicializar TTS
   - Llamar `ui.update_offline_mode(True)` cuando Ollama+Whisper+Kokoro estén activos

### Prioridad:
1. ✅ **Alta**: Indicador de backend (Gemini vs Ollama)
2. ✅ **Alta**: Indicador de TTS (Edge vs Kokoro vs None)
3. ✅ **Alta**: Badge de modo offline (100% local)
4. ✅ **Media**: Logs coloreados por componente
5. 🔲 **Baja**: Selectores en settings (requiere más trabajo)
6. 🔲 **Baja**: Verificación visual de modelos Kokoro

## Beneficios:
- **Transparencia**: Usuario sabe exactamente qué backend está usando
- **Debugging**: Logs coloreados facilitan identificar problemas
- **Privacidad**: Badge de "OFFLINE" destaca modo privado
- **UX**: Fácil cambiar backend sin editar JSON manualmente
