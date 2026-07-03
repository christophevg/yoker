# Changelog

All notable changes to yoker are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## 0.6.0 (2026-07-03)

### Added

- **Multi-Provider Backend System (MBI-006)**: Introduced a `ModelBackend`
  Protocol with `ChatChunk` abstraction, plus `OllamaBackend` and
  `LitellmBackend` adapters. Yoker now supports OpenAI, Anthropic, Gemini,
  and Ollama through a unified backend layer.
- **BackendConfig Tagged Union**: New `BackendConfig` schema with
  provider-specific config classes (`OllamaConfig`, `GenericConfig`,
  `GeminiConfig`, etc.), eliminating provider-specific if-then-else chains
  in config validation.
- **API Key CLI Exclusion**: API keys are now excluded from CLI argument
  rendering to prevent accidental exposure.
- **Token Accounting**: `TurnEndEvent` now carries `input_tokens` and
  `output_tokens` for usage tracking.
- **Bootstrap Wizard (MBI-002)**: Interactive onboarding wizard with
  multi-provider support, curated model selection, ASCII art banner,
  provider display in welcome message, and step-by-step configuration flow.
- **Provider-aware Subagent Spawning**: `Agent.subagent()` now uses the
  parent's backend, keeping spawned agents provider-agnostic.
- **End-user Documentation**: New getting-started guides for Yoker, Ollama,
  and Gemini (with screenshots), plus a comprehensive models reference page.

### Fixed

- **User-Friendly LiteLLM Errors**: LiteLLM exceptions are now caught and
  surfaced as clean messages instead of stack traces.
- **Tool Calling in LitellmBackend**: Corrected tool-calling implementation
  to properly forward tool invocations across providers.
- **Litellm Logging Noise**: Suppressed INFO-level logging from LiteLLM
  across all logger names.
- **Bootstrap Security**: Bootstrap inputs are no longer logged to command
  history (prevents API key leakage in shell history).
- **GeminiConfig Initialization**: Ensured `GeminiConfig` is initialized
  when the Gemini provider is selected during bootstrap.
- **Ollama Web Tools**: Populated `Agent._tool_backends` so Ollama web tools
  work correctly.
- **Windows CI**: Skipped Unix-only assertions (chmod 600, tilde expansion,
  history security tests) on Windows CI runners.
- **Provider Error Display**: Improved error rendering for provider errors
  in the interactive UI.

### Changed

- **Provider Configs Module**: Split provider configs into a dedicated
  `providers` module; added `GenericConfig` for unknown providers.
- **Centralized DEFAULT_BASE_URLS**: Moved default base URLs from
  `LitellmBackend` into the provider config classes.
- **Skills Loading Warning**: Centralized the `skills_dir` not-found warning
  in `load_skills_from_package`.
- **Documentation Refactoring (PR #39)**: Comprehensive documentation review
  with 33 fixes, reorganized screenshots, corrected version references, and
  a new models reference page.

## 0.5.0 (2026-06-26)

### Added

- **UI Separation Migration Complete**: Agent layer is now purely
  event-driven; UI layer owns all presentation.
- **UIHandler Protocol**: Added `UIHandler` protocol with built-in
  `InteractiveUIHandler` and `BatchUIHandler`.
- **UIBridge**: Dispatches agent events to UI handlers without terminal
  logic in the agent.
- **Plugin System**: Load tools, skills, and agents from Python packages
  via `--with <package>`.
- **Plugin Manifest**: Added `__YOKER_MANIFEST__` plugin declaration format.
- **Content Type Detection**: Added content type detection utility
  (`yoker.content_type`).
- **Tool Content Events**: Tools now emit `ToolContentEvent` with
  appropriate MIME types.
- **Slash Commands**: Added `/skills`, `/context`, `/tools`, `/agents`
  commands.
- **Clevis Integration**: Migrated configuration system to Clevis with
  auto-generated CLI arguments.

### Changed

- **Agent Lifecycle**: Removed `Agent.begin_session()` and
  `Agent.end_session()`; agent lifecycle is now create → use → discard.
- **ConsoleEventHandler Removed**: All terminal output is handled by
  `UIHandler` implementations.
- **Agent Refactoring**: Refactored `Agent` into `yoker.agent` package with
  modular components.
- **ContextManager**: Now list-like and extends `UserList`.

### Fixed

- **NetworkError Handling**: Graceful handling of non-recoverable
  `NetworkError` in the CLI session loop.
- **Content Type Detection**: Fixed content type detection fallbacks for
  unknown file types.
- **Tool Parsing**: Tools are now parsed into `ToolSpec` during plugin load
  for consistent architecture.
- **SecurityError Handling**: `clevis.SecurityError` is now caught and
  displays a clean error message.