## Context

MARK LII usa PyQt6 para su UI con un layout de tres columnas (left panel, center HUD, right panel). El right panel actualmente usa un `QVBoxLayout` simple con elementos de altura fija excepto el `LogWidget` que tiene `stretch=1`. La aplicación ya maneja encoding UTF-8 en stdout/stderr (main.py líneas 10-18). El center panel usa un `QSplitter` exitoso para dividir HUD y Content Panel con colapso dinámico.

Para motivación y alcance, ver `proposal.md - Why` y `proposal.md - What Changes`.

## Goals / Non-Goals

**Goals:**
- Reutilizar el patrón de `QSplitter` existente del center panel
- Mantener thread-safety usando signal/slot pattern de Qt
- Preservar streams originales para debugging en terminal
- Zero dependencies nuevas (solo PyQt6 existente)
- Performance: manejo de alto throughput de logs sin congelar UI

**Non-Goals:**
- Filtrado avanzado de logs (por nivel, regex, etc) - puede ser extensión futura
- Exportar logs a archivo - fuera de alcance inicial
- Persistir estado expandido/colapsado entre sesiones - Console siempre inicia colapsado
- Colorear syntax de tracebacks - solo diferenciación stdout (normal) vs stderr (rojo)

## Decisions

### Decision 1: QSplitter en lugar de tabs o layout fijo

**Elegido:** `QSplitter(Qt.Orientation.Vertical)` con dos widgets: Activity Log (arriba) y Console Output (abajo).

**Alternativas consideradas:**
- **Tabs**: Rechazado - rompe patrón visual actual (UI no usa tabs), y oculta uno de los logs completamente
- **Layout fijo 50/50**: Rechazado - no hay flexibilidad para el usuario, y Console Output muchas veces no se necesita
- **Modal/Overlay**: Rechazado - menos discoverable, requiere clicks extras

**Rationale:** El QSplitter ya está probado en el center panel (HUD/Content), usuarios están familiarizados con el patrón de drag, y permite colapsar completamente Console cuando no se usa, maximizando espacio para Activity Log.

### Decision 2: Redirección con ConsoleRedirector custom stream

**Elegido:** Clase `ConsoleRedirector` que implementa el protocolo de stream (`write()`, `flush()`) y emite signals Qt.

**Alternativas consideradas:**
- **logging.Handler**: Rechazado - solo captura logs del módulo logging, no stdout/stderr directo ni print()
- **subprocess.PIPE**: Rechazado - requiere lanzar Python en subprocess, complejidad innecesaria
- **Queue + polling thread**: Rechazado - más complejo que signal/slot, y Qt ya tiene thread-safety built-in

**Rationale:** Redirigir `sys.stdout`/`sys.stderr` captura TODO (print, tracebacks, warnings de bibliotecas). El stream wrapper es simple, y usar Qt signals garantiza thread-safety sin locks manuales.

```python
class ConsoleRedirector:
    def __init__(self, text_widget, color, original_stream):
        self.text_widget = text_widget
        self.color = color
        self.original = original_stream
        self._buffer = []
        self._timer = QTimer()
        self._timer.timeout.connect(self._flush_buffer)
        self._timer.start(100)  # Flush cada 100ms
    
    def write(self, text):
        if text and text.strip():
            self._buffer.append((text, self.color))
            if len(self._buffer) > 50:  # Flush si buffer lleno
                self._flush_buffer()
        if self.original:
            self.original.write(text)
            self.original.flush()
    
    def flush(self):
        if self.original:
            self.original.flush()
    
    def _flush_buffer(self):
        if self._buffer:
            combined = "".join(t for t, _ in self._buffer)
            self.text_widget.append_text(combined, self.color)
            self._buffer.clear()
```

### Decision 3: Buffer con timer de 100ms

**Elegido:** Buffer interno en `ConsoleRedirector` que agrupa mensajes y hace flush cada 100ms o cuando acumula >50 mensajes.

**Alternativas consideradas:**
- **Sin buffer (emit inmediato)**: Rechazado - 100 print() consecutivos = 100 UI updates = UI freeze
- **Buffer sin timer (solo por tamaño)**: Rechazado - si hay 1 print cada 200ms, nunca hace flush y el usuario no ve output
- **Buffer más grande (200ms, 100 msgs)**: Rechazado - latencia visible para debugging interactivo

**Rationale:** 100ms es imperceptible para el usuario pero agrupa suficiente throughput. 50 mensajes como límite superior previene buffers gigantes en caso de spam extremo.

### Decision 4: Límite de 1000 líneas en Console Output

**Elegido:** Auto-trim cuando `document().lineCount() > 1000`, elimina las líneas más antiguas.

**Alternativas consideradas:**
- **Sin límite**: Rechazado - después de horas de ejecución, el QTextEdit consume GB de memoria
- **Límite de caracteres**: Rechazado - líneas largas vs cortas hacen difícil predecir cuántas líneas caben
- **Límite configurable**: Rechazado - over-engineering para v1

**Rationale:** 1000 líneas es suficiente para debugging (~50KB de texto), y el trim es rápido (O(n) donde n = líneas a eliminar).

### Decision 5: Console colapsado por defecto, sin persistencia

**Elegido:** `setSizes([total_height, 0])` al inicializar el splitter. Estado NO se guarda en config.

**Alternativas consideradas:**
- **Expandido por defecto**: Rechazado - la mayoría de usuarios solo necesita Activity Log, Console Output es debugging tool
- **Persistir estado en api_keys.json**: Rechazado - añade complejidad y la mayoría de sesiones no usan Console

**Rationale:** Console Output es opt-in para cuando se necesita. Empezar colapsado maximiza espacio para Activity Log (el log principal). Los usuarios que lo expanden lo hacen intencionalmente para debugging y no les molesta re-expandirlo en siguiente sesión.

### Decision 6: Reutilizar estilos existentes (C.* colors)

**Elegido:** Console Output usa el mismo sistema de colores que el resto de la UI (`C.BG`, `C.TEXT`, `C.BORDER`, etc).

**Rationale:** Consistencia visual con Activity Log y Content Panel. Cuando el usuario cambia el theme color, Console Output se actualiza automáticamente.

## Risks / Trade-offs

### Risk: High-frequency print() spam

**Scenario:** Loop con `print()` en cada iteración (ej: `for i in range(10000): print(i)`).

**Mitigation:**
- Buffer de 100ms agrupa los prints antes de actualizar UI
- Límite de 50 mensajes en buffer fuerza flush si se acumula demasiado
- Auto-trim a 1000 líneas previene crecimiento infinito

**Trade-off:** Mensajes muy rápidos pueden aparecer en batches en lugar de uno por uno, pero esto es preferible a UI freeze.

### Risk: Thread safety con escrituras concurrentes

**Scenario:** Múltiples threads worker ejecutan print() simultáneamente.

**Mitigation:**
- Usar Qt signal/slot (thread-safe por diseño)
- `ConsoleRedirector.write()` es called desde thread original, solo emite signal
- `ConsoleWidget._append()` corre en main thread (Qt garantiza esto)

**Trade-off:** None - este es el patrón recomendado por Qt.

### Risk: Corrupted stdout/stderr en edge cases

**Scenario:** Otra biblioteca también redirige stdout/stderr (ej: pytest captura).

**Mitigation:**
- Guardar referencias a `_original_stdout` y `_original_stderr` ANTES de cualquier redirección
- Escribir también al original en cada `write()` (tee pattern)
- Restaurar streams en `closeEvent()` garantiza cleanup

**Trade-off:** Si otra biblioteca redirige DESPUÉS de nosotros, sus mensajes no llegarán a Console Output, pero sí a terminal. Documentar esto como limitación conocida.

### Risk: Performance de QTextEdit con 1000 líneas

**Scenario:** Console Output lleno (1000 líneas) y continúan llegando mensajes.

**Mitigation:**
- `QTextEdit` es eficiente hasta ~10K líneas según Qt docs
- Trim automático mantiene el límite en 1000
- `LineWrapMode.NoWrap` reduce overhead de word-wrapping

**Trade-off:** Si las líneas son MUY largas (>10KB cada una), puede haber lag. Documentar: "Para logs extremadamente largos, usar herramientas externas de log viewing".

### Risk: Unicode/emoji en Windows legacy console

**Scenario:** Caracteres especiales en console cuando original stdout no soporta UTF-8.

**Mitigation:**
- Ya manejado en main.py líneas 10-18 con `reconfigure(encoding="utf-8", errors="replace")`
- `ConsoleRedirector` respeta este encoding
- En UI (QTextEdit), no hay problema - Qt maneja UTF-8 nativamente

**Trade-off:** En la terminal original (si no es UTF-8), los caracteres pueden aparecer como `?`. En Console Output de la UI siempre se ven bien.

## Migration Plan

**Fase 1: Implementar componentes base**
1. Crear `ConsoleWidget` class (widget standalone, probarlo aislado)
2. Crear `ConsoleRedirector` class (probarlo con mock QTextEdit)
3. Unit test: redirección captura print() y emite signal correctamente

**Fase 2: Integrar en right panel**
1. Refactor `_build_right_panel()` para usar QSplitter
2. Agregar `ConsoleWidget` como segundo widget del splitter
3. Configurar splitter: `setCollapsible(1, True)`, `setSizes([height, 0])`
4. Verificar visualmente: Activity Log sigue funcional, Console colapsado

**Fase 3: Activar redirección**
1. En `JarvisUI.__init__()`, después de crear `self._console_widget`:
   ```python
   self._original_stdout = sys.stdout
   self._original_stderr = sys.stderr
   sys.stdout = ConsoleRedirector(self._console_widget, QColor(C.TEXT), self._original_stdout)
   sys.stderr = ConsoleRedirector(self._console_widget, QColor(C.RED), self._original_stderr)
   ```
2. En `closeEvent()`, restaurar:
   ```python
   sys.stdout = self._original_stdout
   sys.stderr = self._original_stderr
   ```

**Fase 4: Testing**
1. Test manual: `python main.py` y verificar que mensajes de startup aparecen en Console
2. Test: expandir Console Output, ver logs acumulados
3. Test: colapsar Console, verificar que Activity Log toma espacio
4. Test: botón Clear limpia Console
5. Test: drag del splitter ajusta tamaños suavemente

**Rollback:** Si hay problemas críticos, comentar las líneas de redirección en `__init__()`. La aplicación funciona sin Console Output (solo no captura logs).

## Open Questions

Ninguna - todas las decisiones técnicas están resueltas y el plan de implementación es claro.
