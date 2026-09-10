## Purpose

Runs a suite of diagnostic checks (logs, health check, database connections, latency) concurrently and aggregates the findings into a single report, so the user can triage a service with one request.

## ADDED Requirements

### Requirement: Diagnostic Suite Execution
The system SHALL run a configurable set of diagnostic checks for a named target in response to a single request.

#### Scenario: Run full diagnostics
- **WHEN** the user asks to run full diagnostics on a target (for example "the API: logs, health check, db connections, latency")
- **THEN** the system SHALL execute each requested check for that target

#### Scenario: Subset of checks
- **WHEN** the user requests only specific checks
- **THEN** the system SHALL run only the requested checks

### Requirement: Parallel Execution
The system SHALL execute independent diagnostic checks concurrently without blocking the main audio/event loop.

#### Scenario: Concurrent checks
- **WHEN** multiple independent checks are requested
- **THEN** the system SHALL run them in parallel rather than strictly sequentially

#### Scenario: One check fails
- **WHEN** an individual check fails or times out
- **THEN** the system SHALL record that check as failed and continue running and reporting the remaining checks

### Requirement: Aggregated Findings
The system SHALL aggregate the results of all checks into a single readable report.

#### Scenario: Aggregate results
- **WHEN** all diagnostic checks have completed or timed out
- **THEN** the system SHALL return one consolidated report summarizing each check's outcome and any problems found
