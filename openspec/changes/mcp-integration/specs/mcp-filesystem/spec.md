## Purpose

Integrates PyMCP-FS server to provide filesystem access capabilities to JARVIS, enabling reading, writing, editing, listing, searching, and managing files within an allowed directory.

## ADDED Requirements

### Requirement: Server Initialization
The system SHALL launch PyMCP-FS as a subprocess with access restricted to `D:/Programacion/ia/Mark-LII` directory.

#### Scenario: Launch with directory restriction
- **WHEN** starting the PyMCP-FS server
- **THEN** the system executes `python PyMCP-FS/main.py -d D:/Programacion/ia/Mark-LII`

#### Scenario: Security boundary enforcement
- **WHEN** PyMCP-FS is configured with allowed directory `D:/Programacion/ia/Mark-LII`
- **THEN** the server SHALL reject any file operations outside that directory tree

### Requirement: Read File
The system SHALL expose `fs_read_file` tool to read complete UTF-8 text file contents.

#### Scenario: Read existing file
- **WHEN** Gemini calls `fs_read_file` with `{"path": "main.py"}`
- **THEN** the system returns the complete text content of `D:/Programacion/ia/Mark-LII/main.py`

#### Scenario: Read non-existent file
- **WHEN** Gemini calls `fs_read_file` with a path that does not exist
- **THEN** the system returns an error message indicating the file was not found

#### Scenario: Read file outside allowed directory
- **WHEN** Gemini calls `fs_read_file` with `{"path": "C:/Windows/System32/drivers/etc/hosts"}`
- **THEN** PyMCP-FS rejects the request with an access denied error

### Requirement: Write File
The system SHALL expose `fs_write_file` tool to create or overwrite files with specified content.

#### Scenario: Create new file
- **WHEN** Gemini calls `fs_write_file` with `{"path": "test.txt", "content": "Hello"}`
- **THEN** the system creates `D:/Programacion/ia/Mark-LII/test.txt` with content "Hello"

#### Scenario: Overwrite existing file
- **WHEN** Gemini calls `fs_write_file` on an existing file
- **THEN** the system replaces the file content completely

### Requirement: Edit File
The system SHALL expose `fs_edit_file` tool to apply line-based edits with optional dry-run preview.

#### Scenario: Apply edits to file
- **WHEN** Gemini calls `fs_edit_file` with edit instructions
- **THEN** the system modifies the specified lines in the target file

#### Scenario: Dry-run preview
- **WHEN** Gemini calls `fs_edit_file` with `dry_run: true`
- **THEN** the system returns a preview of changes without modifying the file

### Requirement: List Directory
The system SHALL expose `fs_list_directory` tool to enumerate files and subdirectories.

#### Scenario: List directory contents
- **WHEN** Gemini calls `fs_list_directory` with `{"path": "plugins/"}`
- **THEN** the system returns a list of all files and subdirectories in `D:/Programacion/ia/Mark-LII/plugins/`

#### Scenario: Include metadata
- **WHEN** listing directory contents
- **THEN** the system SHALL include file sizes, types, and modification timestamps

### Requirement: Directory Tree
The system SHALL expose `fs_directory_tree` tool to generate hierarchical JSON structure.

#### Scenario: Full tree generation
- **WHEN** Gemini calls `fs_directory_tree` with `{"path": "."}`
- **THEN** the system returns a nested JSON structure representing the entire project directory tree

### Requirement: Search Files
The system SHALL expose `fs_search_files` tool to recursively find files by name pattern or content.

#### Scenario: Search by filename pattern
- **WHEN** Gemini calls `fs_search_files` with `{"pattern": "*.py"}`
- **THEN** the system returns all Python files in the directory tree

#### Scenario: Search by content
- **WHEN** Gemini calls `fs_search_files` with `{"content": "memory_manager"}`
- **THEN** the system returns all files containing the text "memory_manager"

### Requirement: Move File
The system SHALL expose `fs_move_file` tool to relocate or rename files.

#### Scenario: Rename file
- **WHEN** Gemini calls `fs_move_file` with source and destination paths
- **THEN** the system moves the file and refuses to overwrite if destination exists

### Requirement: Get File Info
The system SHALL expose `fs_get_file_info` tool to retrieve file metadata.

#### Scenario: Retrieve metadata
- **WHEN** Gemini calls `fs_get_file_info` with `{"path": "main.py"}`
- **THEN** the system returns size, modification time, creation time, and permissions

### Requirement: Create Directory
The system SHALL expose `fs_create_directory` tool to create new directories including nested structures.

#### Scenario: Create single directory
- **WHEN** Gemini calls `fs_create_directory` with `{"path": "new_dir"}`
- **THEN** the system creates `D:/Programacion/ia/Mark-LII/new_dir`

#### Scenario: Create nested directories
- **WHEN** Gemini calls `fs_create_directory` with `{"path": "a/b/c"}`
- **THEN** the system creates all intermediate directories

### Requirement: Read Multiple Files
The system SHALL expose `fs_read_multiple_files` tool to fetch content from multiple files in one call.

#### Scenario: Batch read files
- **WHEN** Gemini calls `fs_read_multiple_files` with `{"paths": ["ui.py", "main.py"]}`
- **THEN** the system returns content of both files in a single response

### Requirement: Coexistence with file_controller
The system SHALL maintain existing `file_controller` action functionality without conflicts.

#### Scenario: Both tools available
- **WHEN** Gemini needs to perform a file operation
- **THEN** both `file_controller` and MCP filesystem tools are available for selection

#### Scenario: Namespace prevents collision
- **WHEN** both `file_controller` and `fs_*` tools are registered
- **THEN** Gemini can distinguish and call either without ambiguity
