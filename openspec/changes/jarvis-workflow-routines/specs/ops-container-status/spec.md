## Purpose

Reports the health of running containers and flags any exceeding a resource threshold, so the user can check container status in natural language without recalling Docker or orchestration commands.

## ADDED Requirements

### Requirement: Running Container Listing
The system SHALL list currently running containers with their identity and status when container tooling is available.

#### Scenario: List running containers
- **WHEN** the user asks to show running containers
- **THEN** the system SHALL return the list of running containers with name and status

#### Scenario: Container tooling unavailable
- **WHEN** container tooling (such as the Docker CLI) is not installed or reachable
- **THEN** the system SHALL return a spoken explanation that container tooling is unavailable instead of failing

### Requirement: Resource Threshold Flagging
The system SHALL flag containers whose resource usage exceeds a specified threshold.

#### Scenario: Flag high CPU containers
- **WHEN** the user asks to flag containers using more than a stated CPU percentage
- **THEN** the system SHALL identify and highlight containers exceeding that threshold

#### Scenario: Default threshold
- **WHEN** the user asks to flag high-usage containers without stating a threshold
- **THEN** the system SHALL apply a default threshold and state the threshold it used

### Requirement: No Running Containers
The system SHALL handle the case where no containers are running.

#### Scenario: Nothing running
- **WHEN** container tooling is available but no containers are running
- **THEN** the system SHALL report that there are no running containers
