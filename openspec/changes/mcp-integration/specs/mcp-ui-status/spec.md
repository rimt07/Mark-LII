## Purpose

Provides visual feedback in the UI showing the connection status of MCP servers, allowing users to monitor server health at a glance.

## ADDED Requirements

### Requirement: Status Indicator Display
The system SHALL display MCP server connection status in the bottom corner of the UI.

#### Scenario: Indicator placement
- **WHEN** the UI is visible
- **THEN** the MCP status indicator appears in the bottom corner without obscuring other UI elements

#### Scenario: Multiple servers display
- **WHEN** multiple MCP servers are configured
- **THEN** the indicator shows status for each server (e.g., "● fs ○ db")

### Requirement: Connection State Visualization
The system SHALL use distinct visual indicators for each connection state.

#### Scenario: Connected state
- **WHEN** an MCP server is connected and operational
- **THEN** the indicator shows a green filled circle (●) next to the server ID

#### Scenario: Connecting state
- **WHEN** an MCP server is in the process of connecting
- **THEN** the indicator shows a yellow half-filled circle (◐) next to the server ID

#### Scenario: Disconnected state
- **WHEN** an MCP server is disabled or not running
- **THEN** the indicator shows a gray empty circle (○) next to the server ID

#### Scenario: Error state
- **WHEN** an MCP server connection has failed
- **THEN** the indicator shows a red X (✗) next to the server ID

### Requirement: Status Updates
The system SHALL update the status indicator in real-time as server connection states change.

#### Scenario: Startup connection update
- **WHEN** MARK LII starts and begins connecting to MCP servers
- **THEN** the indicator transitions from ◐ (connecting) to ● (connected) as each server establishes connection

#### Scenario: Connection loss update
- **WHEN** an MCP server connection is lost during operation
- **THEN** the indicator immediately transitions to ✗ (error)

#### Scenario: Reconnection update
- **WHEN** a failed MCP server successfully reconnects
- **THEN** the indicator transitions from ✗ (error) through ◐ (connecting) to ● (connected)

### Requirement: Detailed Information on Hover
The system SHALL display detailed server information when user hovers over the status indicator.

#### Scenario: Hover tooltip for connected server
- **WHEN** user hovers over a connected server indicator (● fs)
- **THEN** a tooltip displays "PyMCP-FS: Connected, 10 tools available"

#### Scenario: Hover tooltip for error server
- **WHEN** user hovers over an error server indicator (✗ fs)
- **THEN** a tooltip displays "PyMCP-FS: Error - Connection lost" or similar diagnostic message

#### Scenario: Hover tooltip for disabled server
- **WHEN** user hovers over a disabled server indicator (○ db)
- **THEN** a tooltip displays "Database Server: Disabled"

### Requirement: Non-intrusive Design
The system SHALL display the status indicator without interfering with existing UI functionality.

#### Scenario: No blocking of activity log
- **WHEN** the status indicator is displayed
- **THEN** the activity log remains fully visible and scrollable

#### Scenario: No blocking of waveform
- **WHEN** the status indicator is displayed
- **THEN** the audio waveform visualization is not obscured

#### Scenario: No impact on HUD controls
- **WHEN** the status indicator is displayed
- **THEN** all existing HUD controls (mute, settings, etc.) remain accessible
