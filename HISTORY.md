# Yoker Version History

## 0.5.0 (2026-06-26)

### New Features
- UI Separation migration complete: Agent layer is purely event-driven, UI layer owns all presentation
- Added `UIHandler` protocol and built-in `InteractiveUIHandler` and `BatchUIHandler`
- Added `UIBridge` to dispatch agent events to UI handlers without terminal logic in the agent
- Added package plugin system: load tools, skills, and agents from Python packages via `--with <package>`
- Added `__YOKER_MANIFEST__` plugin declaration format
- Added content type detection utility (`yoker.content_type`)
- Tools now emit `ToolContentEvent` with appropriate MIME types (text/plain, text/x-diff, application/json)
- Added slash commands: `/skills`, `/context`, `/tools`, `/agents`
- Migrated configuration system to Clevis with auto-generated CLI arguments and environment variable support

### Architecture
- Removed `Agent.begin_session()` and `Agent.end_session()`; agent lifecycle is now create → use → discard
- Removed `ConsoleEventHandler`; all terminal output is handled by `UIHandler` implementations
- Refactored `Agent` into `yoker.agent` package with `AgentCore`, `Agent`, `processing`, and `tools` modules
- `ContextManager` is now list-like and extends `UserList`

### Bug Fixes
- Graceful handling of non-recoverable `NetworkError` in the CLI session loop
- Fixed content type detection fallbacks for unknown file types
- Fixed tool parsing: tools are now parsed into `ToolSpec` during plugin load for consistent architecture
- Fixed error handling: `clevis.SecurityError` is now caught and displays a clean error message

---

## 0.4.0 (2026-05-26)

### New Features
- Added `Config.discover()` class method for auto-discovering configuration
- Added environment variable configuration support (`YOKER_*` or `{PREFIX}_YOKER_*`)
- Added agent definition path in configuration (`agents.definition`)
- Config now auto-discovers from `./yoker.toml`, `~/.yoker.toml`, and environment variables

### Bug Fixes
- Fixed config file discovery to properly locate agent definitions
- Fixed TOML path handling for Windows compatibility (forward slashes)

### Changes
- Configuration resolution order: environment variables → explicit config → explicit path → discovered config → defaults

---

## 0.3.0 (2026-05-25)

### New Features
- Added async event handler support (handlers can be sync or async)
- Async handlers can directly `await` I/O operations
- Added proper async `__call__` method detection on handler instances

### Bug Fixes
- Fixed async event handler invocation
- Fixed spinner issues in async context
- Fixed storage path expansion for `~` (home directory)
- Fixed hatch build configuration for wheel packaging

### Changes
- All Agent methods are now async: `begin_session()`, `process()`, `end_session()`
- CLI uses async prompt input for consistency
- Removed conflicting hatch sources configuration

---

## 0.2.x (Earlier)

### Features
- Event-driven architecture with session, turn, thinking, content, and tool events
- Tool system with guardrails: read, list, write, update, search, existence, mkdir, git, agent
- Web tools: web_search, web_fetch with SSRF protection
- Agent definitions from Markdown files with YAML frontmatter
- Context persistence (JSONL) for session resumption
- Thinking mode (LLM reasoning trace)
- Configuration system with frozen dataclasses
- Slash commands: /help, /think, /context
- Demo session scripts for documentation

### Architecture
- Library-first design (Agent emits events, handlers subscribe)
- Async-first implementation
- Guardrails for filesystem tools (defense-in-depth validation)
- Static permissions defined in configuration

---

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for detailed release notes.
