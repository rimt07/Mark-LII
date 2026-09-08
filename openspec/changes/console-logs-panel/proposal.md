## Why

Los usuarios y desarrolladores necesitan ver la salida cruda de consola (stdout/stderr) durante la ejecución de MARK LII para debugging, monitoreo de errores, y análisis de logs completos. Actualmente, el Activity Log muestra mensajes formateados con colores y animación, pero no captura tracebacks completos, warnings de bibliotecas, ni output de print() statements. Esta información es crítica para diagnosticar problemas y entender el comportamiento interno de la aplicación.

## What Changes

- **Nuevo panel "Console Output"** en el sidebar derecho, bajo Activity Log
- **QSplitter vertical** reemplaza el layout fijo, permitiendo ajustar dinámicamente el espacio entre Activity Log y Console Output
- **Redirección de stdout/stderr** captura toda la salida de Python y la muestra en tiempo real en el panel de Console
- **Panel colapsable** por defecto (Console Output inicia colapsado, se expande cuando el usuario lo necesita)
- **Botón Clear** para limpiar el contenido del console cuando se llena
- **Límite de 1000 líneas** con auto-trim para prevenir consumo excesivo de memoria
- **Thread-safe signal system** para actualizar la UI desde cualquier thread sin crashes
- **Mantener stdout/stderr original** para que la salida siga visible en terminal/consola del sistema

## Capabilities

### New Capabilities

- `console-output-capture`: Sistema de captura y visualización de stdout/stderr en tiempo real con redirección thread-safe, colores diferenciados (stderr en rojo), y gestión de buffer para performance
- `right-panel-splitter`: Implementación de QSplitter en el panel derecho para permitir ajuste dinámico de espacio entre Activity Log y Console Output, con capacidad de colapsar/expandir

### Modified Capabilities

<!-- No hay capacidades existentes que cambien - esta es una adición pura -->

## Impact

### Archivos Afectados

- **ui.py**:
  - `_build_right_panel()`: Refactor completo para usar QSplitter en lugar de VBoxLayout simple
  - Nueva clase `ConsoleWidget`: Widget personalizado con QTextEdit + header + botón clear
  - Nueva clase `ConsoleRedirector`: Stream object que captura stdout/stderr y emite signals a Qt
  - `__init__()`: Setup de redirección después de inicializar Qt
  - `closeEvent()`: Restaurar streams originales al cerrar

### Dependencias

- **PyQt6**: Ya incluido, no requiere nuevas dependencias
- **sys.stdout/stderr**: Redirección estándar de Python, compatible con el encoding UTF-8 ya configurado en main.py

### Comportamiento de Usuario

- El panel derecho mantiene su estructura visual, pero ahora el área de logs es redimensionable
- Console Output inicia colapsado, no impacta el flujo existente
- Los mensajes de Activity Log siguen funcionando exactamente igual
- La salida de consola es adicional, no reemplaza nada existente

### Riesgos

- **Performance**: Muchos print() simultáneos podrían saturar la UI → mitigado con buffer de 100ms y limit de 1000 líneas
- **Thread safety**: Escribir a QTextEdit desde threads no-Qt causa crashes → mitigado con signal/slot pattern
- **Encoding**: Caracteres especiales en console → ya manejado por el reconfigure UTF-8 existente en main.py líneas 10-18
