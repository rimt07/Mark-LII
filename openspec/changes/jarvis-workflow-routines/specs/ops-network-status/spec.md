## Purpose

Reports Tailscale mesh network status, identifies offline nodes, and explains anomalies so the user can assess connectivity without parsing raw network output.

## ADDED Requirements

### Requirement: Mesh Status Reporting
The system SHALL report the status of the Tailscale mesh network when Tailscale is available.

#### Scenario: Report mesh status
- **WHEN** the user asks to check Tailscale status
- **THEN** the system SHALL report each node's name and online/offline state

#### Scenario: Tailscale unavailable
- **WHEN** the Tailscale CLI is not installed or reachable
- **THEN** the system SHALL return a spoken explanation that Tailscale is unavailable instead of failing

### Requirement: Offline Node Identification
The system SHALL identify which nodes are offline and, where the data is available, indicate when they went offline.

#### Scenario: Identify offline nodes
- **WHEN** one or more mesh nodes are offline
- **THEN** the system SHALL list the offline nodes distinctly from the online ones

#### Scenario: Last-seen time available
- **WHEN** last-seen timing data is available for an offline node
- **THEN** the system SHALL include when that node was last seen

### Requirement: Anomaly Explanation
The system SHALL provide a natural-language explanation of notable network anomalies rather than raw status only.

#### Scenario: Explain an anomaly
- **WHEN** the status contains a notable anomaly (such as several nodes offline)
- **THEN** the system SHALL summarize the anomaly in plain language
