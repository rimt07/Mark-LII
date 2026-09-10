## Purpose

Combines filesystem/git data, web research, and conversation history into a single structured engineering report (for example a weekly summary), so the user can produce a report from multiple sources with one request.

## ADDED Requirements

### Requirement: Multi-Source Aggregation
The system SHALL aggregate data from multiple sources — git history, open Jira tickets, and conversation history — into a single report when those sources are available.

#### Scenario: Weekly report from combined sources
- **WHEN** the user asks to generate a weekly engineering report from their git history and open Jira tickets
- **THEN** the system SHALL collect data from each available source and combine it into one report

#### Scenario: Source unavailable
- **WHEN** one of the requested sources is unavailable (such as Jira not configured)
- **THEN** the system SHALL generate the report from the available sources and note which sources were unavailable

### Requirement: Structured Output
The system SHALL produce the report in a structured, readable format with clear sections per source or theme.

#### Scenario: Sectioned report
- **WHEN** the report is generated
- **THEN** the output SHALL be organized into clear sections rather than an undifferentiated block of text

### Requirement: Report Time Window
The system SHALL scope the report to a requested time window and state the window used.

#### Scenario: Weekly window
- **WHEN** the user requests a weekly report
- **THEN** the system SHALL scope source data to the past week and state the window in the report
