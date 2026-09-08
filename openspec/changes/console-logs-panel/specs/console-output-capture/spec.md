## Purpose

Captura y visualiza en tiempo real toda la salida de stdout/stderr de la aplicación Python en un panel dedicado de la UI, permitiendo debugging, monitoreo de errores, y análisis de logs completos sin interferir con la consola del sistema.

## ADDED Requirements

### Requirement: Capture stdout and stderr streams

El sistema SHALL capturar todos los mensajes escritos a `sys.stdout` y `sys.stderr` y mostrarlos en el panel Console Output de la UI.

#### Scenario: Python print statement captured
- **WHEN** código Python ejecuta `print("debug message")`
- **THEN** el texto "debug message" aparece en el Console Output panel
- **AND** el texto también aparece en la consola/terminal original del sistema

#### Scenario: Exception traceback captured
- **WHEN** una excepción no capturada genera un traceback en stderr
- **THEN** el traceback completo aparece en Console Output con color rojo
- **AND** el traceback también aparece en stderr de la consola original

#### Scenario: Library warnings captured
- **WHEN** una biblioteca de terceros emite un warning a stderr
- **THEN** el warning aparece en Console Output con color rojo
- **AND** el warning también aparece en stderr original

### Requirement: Thread-safe UI updates

El sistema SHALL actualizar el Console Output panel de forma thread-safe cuando los mensajes provengan de cualquier thread de la aplicación.

#### Scenario: Output from background thread
- **WHEN** un thread worker ejecuta `print("background task complete")`
- **THEN** el mensaje aparece en Console Output sin causar crash
- **AND** la UI permanece responsive durante la actualización

#### Scenario: Concurrent output from multiple threads
- **WHEN** múltiples threads escriben a stdout simultáneamente
- **THEN** todos los mensajes aparecen en Console Output
- **AND** no ocurren race conditions ni corrupciones de texto
- **AND** la aplicación no se congela

### Requirement: Visual differentiation by stream

El sistema SHALL diferenciar visualmente mensajes de stdout vs stderr en el Console Output panel.

#### Scenario: Stdout appears in default color
- **WHEN** mensaje se escribe a stdout
- **THEN** aparece en Console Output con color de texto normal (cyan/text color)

#### Scenario: Stderr appears in red
- **WHEN** mensaje se escribe a stderr
- **THEN** aparece en Console Output con color rojo
- **AND** es fácilmente distinguible de mensajes stdout

### Requirement: Memory management with line limits

El sistema SHALL mantener un máximo de 1000 líneas en Console Output para prevenir consumo excesivo de memoria.

#### Scenario: Trimming old lines when limit reached
- **WHEN** Console Output contiene 1000 líneas
- **AND** llega una nueva línea
- **THEN** la línea más antigua se elimina automáticamente
- **AND** la nueva línea se agrega al final

#### Scenario: Performance remains stable with full buffer
- **WHEN** Console Output contiene 1000 líneas
- **AND** continúan llegando nuevos mensajes
- **THEN** la UI permanece responsive
- **AND** no hay degradación notable de performance

### Requirement: Manual clear functionality

El sistema SHALL permitir al usuario limpiar manualmente el contenido del Console Output.

#### Scenario: User clears console
- **WHEN** usuario hace click en el botón "Clear"
- **THEN** todo el contenido del Console Output se elimina
- **AND** el panel queda vacío listo para nuevos mensajes

### Requirement: Buffered output for performance

El sistema SHALL usar buffering para agrupar múltiples mensajes consecutivos y minimizar actualizaciones de UI.

#### Scenario: Multiple rapid prints batched
- **WHEN** código ejecuta 50 print statements consecutivos en menos de 100ms
- **THEN** los mensajes se agrupan en un solo update de UI
- **AND** todos los mensajes aparecen en Console Output
- **AND** el UI thread no se satura

#### Scenario: Large output flushed on buffer limit
- **WHEN** el buffer interno acumula más de 50 mensajes sin flush
- **THEN** el buffer se vacía inmediatamente a la UI
- **AND** todos los mensajes se muestran correctamente

### Requirement: UTF-8 encoding support

El sistema SHALL manejar correctamente caracteres UTF-8 en la salida de console, incluyendo emojis y caracteres internacionales.

#### Scenario: Unicode characters displayed correctly
- **WHEN** código ejecuta `print("Hello 世界 🌍")`
- **THEN** el texto "Hello 世界 🌍" aparece correctamente en Console Output
- **AND** no hay caracteres corruptos o reemplazados

### Requirement: Preserve original streams

El sistema SHALL mantener la funcionalidad de stdout/stderr originales para permitir debugging desde terminal.

#### Scenario: Output visible in both UI and terminal
- **WHEN** la aplicación se ejecuta desde una terminal
- **AND** código ejecuta `print("test")`
- **THEN** "test" aparece en Console Output de la UI
- **AND** "test" también aparece en la terminal donde se lanzó la aplicación

#### Scenario: Redirection can be disabled
- **WHEN** la aplicación cierra o se resetea
- **THEN** sys.stdout y sys.stderr se restauran a sus valores originales
- **AND** la salida vuelve a funcionar normalmente sin la UI
