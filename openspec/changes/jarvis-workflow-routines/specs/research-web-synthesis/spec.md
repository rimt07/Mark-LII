## Purpose

Searches the web, fetches the most relevant pages, and synthesizes the findings into a compared answer rather than returning a list of links, so the user gets an analysis instead of raw results.

## ADDED Requirements

### Requirement: Web Search And Retrieval
The system SHALL search the web for a research query and retrieve content from the most relevant results.

#### Scenario: Search and fetch
- **WHEN** the user asks to research a topic (for example "the top 5 approaches to rate limiting APIs")
- **THEN** the system SHALL perform a web search and retrieve content from the top relevant pages

#### Scenario: Retrieval failure for a source
- **WHEN** one of the selected pages cannot be retrieved
- **THEN** the system SHALL continue with the remaining sources and note the omission

### Requirement: Synthesized Comparison
The system SHALL synthesize the retrieved content into a coherent answer that compares approaches, not merely a list of links.

#### Scenario: Compared synthesis
- **WHEN** the user asks to compare multiple approaches
- **THEN** the system SHALL produce a synthesized comparison summarizing each approach and its tradeoffs

#### Scenario: Source attribution
- **WHEN** the synthesized answer draws on specific sources
- **THEN** the system SHALL reference the sources it used

### Requirement: No Results Handling
The system SHALL handle the case where the search yields no usable results.

#### Scenario: No usable results
- **WHEN** the search returns no usable content
- **THEN** the system SHALL report that no usable results were found rather than fabricating an answer
