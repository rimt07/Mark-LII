## Purpose

Permite ajuste dinámico del espacio entre Activity Log y Console Output en el panel derecho mediante un divisor arrastrable, con capacidad de colapsar/expandir el Console Output según las necesidades del usuario.

## ADDED Requirements

### Requirement: Vertical splitter between log sections

El sistema SHALL dividir el panel derecho en dos secciones ajustables: Activity Log (arriba) y Console Output (abajo), separadas por un divisor arrastrable vertical.

#### Scenario: User drags splitter handle
- **WHEN** usuario arrastra el handle del splitter hacia arriba o abajo
- **THEN** el espacio de Activity Log y Console Output se ajusta en tiempo real
- **AND** ambos widgets se redimensionan suavemente sin parpadeo

#### Scenario: Splitter handle visible on hover
- **WHEN** usuario posiciona el mouse sobre el handle del splitter
- **THEN** el handle cambia de color para indicar que es interactivo
- **AND** el cursor cambia a un indicador de resize vertical

### Requirement: Activity Log non-collapsible

El sistema SHALL prevenir que Activity Log se colapse o sea ocultado por el splitter.

#### Scenario: User cannot collapse Activity Log
- **WHEN** usuario intenta arrastrar el splitter hacia arriba
- **THEN** Activity Log mantiene un tamaño mínimo visible
- **AND** el splitter no permite reducir Activity Log a cero height

### Requirement: Console Output collapsible

El sistema SHALL permitir que Console Output sea completamente colapsado, liberando su espacio para Activity Log.

#### Scenario: User collapses Console Output
- **WHEN** usuario arrastra el handle del splitter hasta el fondo
- **THEN** Console Output se colapsa completamente (height = 0)
- **AND** Activity Log toma todo el espacio vertical disponible

#### Scenario: User expands collapsed Console Output
- **WHEN** Console Output está colapsado (height = 0)
- **AND** usuario arrastra el handle hacia arriba
- **THEN** Console Output se expande proporcionalmente
- **AND** Activity Log cede espacio proporcionalmente

### Requirement: Console Output starts collapsed

El sistema SHALL iniciar con Console Output colapsado por defecto en cada sesión nueva.

#### Scenario: Fresh application launch
- **WHEN** la aplicación MARK LII inicia por primera vez
- **THEN** Console Output está colapsado (no visible)
- **AND** Activity Log ocupa todo el espacio vertical del área de logs

#### Scenario: Application restart preserves default state
- **WHEN** la aplicación se reinicia
- **THEN** Console Output vuelve a estar colapsado
- **AND** el estado expandido previo NO se persiste entre sesiones

### Requirement: Reasonable default sizes when expanded

El sistema SHALL asignar tamaños proporcionales razonables cuando Console Output se expande desde estado colapsado.

#### Scenario: First expansion allocates 30% to Console
- **WHEN** usuario expande Console Output por primera vez desde colapsado
- **THEN** Console Output recibe aproximadamente 30% del espacio total
- **AND** Activity Log mantiene aproximadamente 70% del espacio total

### Requirement: Smooth resize without flickering

El sistema SHALL redimensionar ambas secciones suavemente durante el arrastre del splitter sin flickering o redraws visibles.

#### Scenario: Continuous drag is smooth
- **WHEN** usuario arrastra el handle del splitter continuamente
- **THEN** ambos widgets se redimensionan en cada frame sin lag
- **AND** no hay parpadeo o artifacts visuales durante el drag

### Requirement: Maintain layout of other panel elements

El sistema SHALL preservar el diseño y posición de los elementos bajo las secciones de logs (FILE UPLOAD, COMMAND INPUT, botones).

#### Scenario: File upload section remains accessible
- **WHEN** el splitter ajusta el espacio de logs
- **THEN** FILE UPLOAD section permanece visible debajo
- **AND** el drop zone sigue funcional

#### Scenario: Command input always visible
- **WHEN** Console Output se expande o colapsa
- **THEN** COMMAND INPUT section permanece visible en su posición
- **AND** el input field y botones siguen accesibles

#### Scenario: Interrupt and microphone buttons unaffected
- **WHEN** el splitter se ajusta
- **THEN** los botones INTERRUPT y MICROPHONE permanecen visibles
- **AND** mantienen su altura fija (34px y 30px respectivamente)

### Requirement: Splitter respects fixed panel width

El sistema SHALL mantener el ancho fijo del panel derecho (340px) independientemente del estado del splitter.

#### Scenario: Panel width constant during resize
- **WHEN** usuario ajusta el splitter vertical
- **THEN** el ancho del panel derecho permanece en 340px
- **AND** solo el height de los widgets cambia

### Requirement: Consistent visual styling with existing splitter

El sistema SHALL usar el mismo estilo visual que el splitter central existente (HUD/Content Panel) para mantener consistencia en la UI.

#### Scenario: Splitter handle matches design system
- **WHEN** usuario ve el handle del right panel splitter
- **THEN** tiene el mismo estilo que el center splitter handle
- **AND** usa los mismos colores del theme (C.BORDER, C.PRI_DIM en hover)
- **AND** tiene 4px de altura como el center splitter
