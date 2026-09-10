## Purpose

Routes the same prompt to multiple LLM providers and compares their answers, so the user can cross-validate a judgment (for example whether code is SQL-injection-safe) across models.

## ADDED Requirements

### Requirement: Multi-Provider Routing
The system SHALL send the same prompt to multiple configured LLM providers when the user requests multi-model validation.

#### Scenario: Route to named providers
- **WHEN** the user asks to route a prompt to multiple named providers (for example "ask both Claude and GPT-4o")
- **THEN** the system SHALL send the identical prompt to each named available provider

#### Scenario: Provider not configured
- **WHEN** a requested provider is not configured or its credentials are absent
- **THEN** the system SHALL skip that provider, note it was unavailable, and continue with the available providers

#### Scenario: No extra providers configured
- **WHEN** no additional providers are configured beyond the default backend
- **THEN** the system SHALL answer with the available backend and state that multi-model comparison was unavailable

### Requirement: Answer Comparison
The system SHALL present the providers' answers in a way that highlights agreement and disagreement.

#### Scenario: Compare answers
- **WHEN** two or more providers return answers
- **THEN** the system SHALL present each provider's answer and summarize where they agree or differ

### Requirement: Credential Handling
The system SHALL read provider credentials from configuration and SHALL NOT expose secret values in its responses.

#### Scenario: Secrets not echoed
- **WHEN** provider credentials are used to route a prompt
- **THEN** the system SHALL reference providers by name and SHALL NOT include credential values in any response
