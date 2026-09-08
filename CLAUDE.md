# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MARK LII** is a cross-platform voice AI assistant built on the Gemini Live API. It's a JARVIS-style personal assistant with real-time voice interaction, visual awareness, system control, and a plugin architecture. The project runs on Windows, macOS, and Linux.

Core architecture:
- **main.py**: Core event loop handling Gemini Live session, bidirectional audio streaming, tool dispatch, and plugin orchestration
- **ui.py**: PyQt6-based HUD with reactive waveform, boot animation, activity log, plugin manager, and camera feed
- **Plugin system**: Drop-in `.py` files in `plugins/` that get auto-discovered at startup (copy `plugins/_template.py` to start)
- **Memory system**: Persistent user preferences, identity, project context stored in `memory/long_term.json` with unlimited store and on-demand recall

## Development Commands

### Setup and Running
```bash
# Initial setup
python setup.py                    # Installs requirements + Playwright browsers + pywin32 post-install
python main.py                     # Launch MARK LII (runs first-time config wizard if needed)

# Manual dependency installation (if setup.py fails)
pip install -r requirements.txt
python -m playwright install
```

### Testing
No automated test suite exists. Manual testing workflow:
1. Start the app: `python main.py`
2. Test voice interaction through microphone
3. Monitor activity log in the HUD for tool execution and errors
4. Check `memory/long_term.json` for memory persistence

### Code Quality
No linters/formatters configured. Code follows project conventions:
- Tool functions in `actions/*.py` return spoken-language strings
- Plugin `run()` functions catch their own exceptions and return error strings
- UTF-8 encoding enforced on all streams (see main.py:10-18)

## Architecture

### Audio Pipeline
- **Input**: 16 kHz mono microphone → Gemini Live API
- **Output**: 24 kHz audio from Gemini → speakers
- **Device selection**: `core/audio_devices.py` filters, measures, and validates devices (rejects silent sinks like DirectSound output on Windows)
- Audio levels drive reactive waveform and arc-reactor core visualization

### Tool Execution Flow
1. Gemini Live API returns tool call via `ModelTurn`
2. `_execute_tool()` dispatches to:
   - Built-in actions (`actions/*.py`)
   - Plugin system (`core/plugin_loader.py` → `plugins/*.py`)
3. Tool returns natural-language string → spoken back to user
4. Some tools register undo actions (`core/undo.py`) or confirmation gates (`core/confirm.py`)

### Plugin System
- Discovery: `core/plugin_loader.py` scans `plugins/*.py` at startup
- Each plugin defines `PLUGIN` dict (name, description, parameters) and `run()` function
- Collision detection: duplicate names across plugins → both rejected
- Crash isolation: plugin exceptions caught and logged, don't kill session
- Enable/disable: stored in `config/api_keys.json`, toggled via UI without restart

### Memory Architecture
- **Prompt budget**: Recently updated facts fit in prompt (under 1000 chars for 61 facts)
- **Storage**: Unlimited in `memory/long_term.json` (categories: identity, preferences, projects, sessions, monitors)
- **On-demand recall**: `recall_memory` tool searches full store locally (<1ms)
- **Index**: Keys that don't fit in prompt → carried as index so model knows to recall them

### Undo System
- Actions register closures to reverse themselves (files, settings)
- User says "undo" → last action reversed
- Files >1MB excluded (too large to keep in memory)
- `organize_desktop` journals all moves → reverses in one call

### Confirmation Gate
- Irreversible actions (shutdown, restart, toggle_wifi) require UI button press
- Tool returns `[CONFIRMATION_PENDING]` → UI shows banner
- Token issued by UI, not model (model can't forge confirmation)
- Non-blocking: JARVIS continues speaking while banner is up

## Key Configuration Files

### `config/api_keys.json`
Stores API key, user/assistant names, voice choice, UI theme color, audio device names, plugin enable/disable state. Modified by UI and setup wizard.

### `memory/long_term.json`
Persistent memory store (identity, preferences, projects, sessions, monitors). Managed by `memory/memory_manager.py`. Grows without limit; old entries never auto-deleted.

### `core/prompt.txt`
JARVIS personality, tool routing rules, language detection behavior, and execution protocol. Injected into Gemini system prompt.

## Common Development Tasks

### Adding a New Tool/Action
1. Create `actions/my_tool.py` with function signature: `def my_tool(parameters: dict, player=None) -> str`
2. Import in main.py: `from actions.my_tool import my_tool`
3. Add Gemini function declaration in `_build_tools()` (main.py ~lines 200-500)
4. Add dispatch case in `_execute_tool()` (main.py ~line 700)

### Adding a Plugin
1. Copy `plugins/_template.py` → `plugins/my_plugin.py`
2. Fill in `PLUGIN` dict (name, description, parameters)
3. Implement `run(parameters, player, session_memory)` function
4. No changes to other files needed (auto-discovered at next launch)

### Modifying UI
- Edit `ui.py` (PyQt6 application)
- Reactive waveform: driven by `self.levels` queue (populated by main.py audio levels)
- Activity log: `write_log(message)` from any tool
- Boot animation: triggered by `show_boot_animation()` on launch

### Audio Device Debugging
- Devices measured at startup by `core/audio_devices.py`
- Probe results logged to console (MME vs DirectSound timing test)
- User selection stored by name in `config/api_keys.json`
- Fallback to system default if saved device missing

## Platform-Specific Notes

### Windows
- Subprocess calls patched to use `CREATE_NO_WINDOW` flag (main.py:22-31)
- Audio: DirectSound for input, MME for output (measured as reliable)
- Dependencies: `comtypes`, `pycaw`, `win10toast`, `pywinauto`, `pywin32`

### macOS/Linux
- Platform-specific deps conditional in requirements.txt
- Fewer audio host APIs to filter
- LaunchAgent (macOS) / systemd (Linux) for reminders/auto-start

## Language Handling
- User language detected on first utterance → silently saved to memory
- All responses in user's MOST RECENT message language (not memory language)
- Tool parameters always extracted in English (internal protocol)
- Console encoding forced to UTF-8 with replacement fallback (main.py:10-18)

## Session Lifecycle
1. Load config + memory → build Gemini system prompt
2. Start audio streams (measure+select devices)
3. Connect to Gemini Live API with session resumption handle
4. Event loop: audio chunks ↔ tool calls ↔ spoken responses
5. On disconnect: session handle cached for reconnect (conversation continues)
6. On exit: save session summary to memory for next morning briefing

## Third-Party Integrations
- **Gemini Live API**: Native audio streaming, function calling, vision
- **DDG Search**: Fallback when Gemini grounded search unavailable
- **Playwright**: Browser automation for web_search
- **YouTube, Steam, Epic Games**: Controlled via respective APIs/automation
- **FastAPI + QR pairing**: Remote dashboard (`dashboard/server.py`)
