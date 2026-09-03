## Unreleased

### Added
- **`label_create` GitHub operation**: create repository labels
  (`label`, optional `color` as 6-char hex and `description`) — the
  missing companion to `issue_edit add_label`, since gh never
  auto-creates labels. Requires explicit opt-in via
  `tools.github.allowed_operations`.
- **`issue_edit` GitHub operation**: edit existing issues — labels and
  assignees (add/remove), plus state changes (`state="closed"` closes via
  `gh issue close`, `state="open"` reopens via `gh issue reopen`).
  Returns the updated issue summary. Requires explicit opt-in via
  `tools.github.allowed_operations`, like all write operations.

### Changed
- **github tool (#1): `repo` optional for all write operations** —
  `pr_create`, `release_create`, `issue_create`, and `label_create` no
  longer reject a missing `repo`; like the read operations, gh then
  auto-detects the repository from the current git remote, matching the
  documented "If omitted, uses current git repo" behavior. `pr_reviews`,
  `pr_comments`, and `pr_draft` still require `repo` (they use `gh api`,
  which has no auto-detection). The `require_explicit_repo` config option
  still forces an explicit repo for every operation.
- **write tool `create_parents` defaults to True**: writing to a path whose
  parent directories do not exist now creates them automatically
  (`mkdir -p` semantics) instead of failing with "Parent directory does not
  exist" — eliminating a guaranteed error → mkdir → retry round trip.
  Pass `create_parents=false` to keep the old strict behavior. The
  protected-files guardrail is unaffected: parent creation happens only
  for already-approved paths.

### Fixed
- **Bare-name tool dispatch**: a model emitting a bare tool name (`list`)
  instead of the namespaced schema name (`yoker__list`) no longer fails
  with `Error: Unknown tool`. Dispatch now falls back to
  `ToolRegistry.resolve()` (precedent: `AgentRegistry.resolve()`): one
  match is dispatched, several raise an ambiguity error listing the full
  namespaced names, and the not-found error now lists the available tools
  so the model can self-correct on the next attempt.
- **make tool (#59)**: env-var rejections now name the target's effective
  allowlist (or that no entry exists — deny by default) and point to
  `[tools.make.allowed_env_vars]` in yoker.toml; the tool description now
  documents the per-target env-var mechanism.
- **post_filter guidance (#60)**: overflow guidance and the auto-injected
  `post_filter` description now include pytest collection-error patterns
  (`ERROR collecting`, `ERRORS`, `##[error]`), warn that matching is
  substring-based, explain the line-number prefix on sliced read output
  for ^-anchored patterns, and add a hint when a filter matches zero lines.
- **github tool (#68)**: allowlist rejections now name the enabling key —
  add the operation to `[tools.github] allowed_operations` in yoker.toml.
  Write operations remain opt-in.

## 0.11.0 (2026-08-31)

### Added
- **Team-of-agents operations**: `Session` now supports ephemeral agent
  spawning plus a `release_agent` tool, so agents can scale their team
  on demand and free slots when done.
- **GitHub tool expansion**: new `pr_comment`, `pr_edit` (assignees,
  reviewers, labels), `pr_draft`, `pr_ready` (draft → ready), and
  `issue_create` operations, plus draft support for `pr_create` and
  merged review comment types.
- **Git tool expansion**: new `rebase` operation, `ref` argument for
  `log`/`diff`/`show` (branch and range diffs), a `set_upstream` flag on
  `push`, and improved path error reporting.
- **Path guardrail redesign**: read/write split with spec-driven guard
  lookup and unified approval across all agents; approval prompts now
  only trigger for write/update/file tools, and read `allowed_extensions`
  supports filenames (defaults to allow-all).
- **`update` tool operation inference**: the operation is inferred from
  the arguments, while `delete` must always be requested explicitly.
- **`notify` tool**: macOS notifications for long-running tasks.
- **`/session` command**: lists active agents in the interactive UI,
  with agent names shown (in color) in feedback and stats lines.
- **`--prompt` option**: `yoker chat` now accepts a prompt argument.
- **Configurable context files**: the hardcoded `AGENTS.md` context file
  is replaced by a configurable context files list.
- **Today's date** is injected into the agent's environment information.

### Fixed
- **GitHub**: `repo_view` passes the repo positionally again, list
  operations control payload size, and `pr_comment` places the `--body`
  flag correctly before `--`.
- **Session**: sub-agent timeouts exclude approval-wait time, and spawned
  agents stay active for follow-up messages.
- **Core**: orphaned `_process_consumer` tasks no longer emit
  "Task destroyed" warnings.
- **Guardrails**: `~` is expanded in `filesystem_paths`, the allowed
  scope is checked before prompting for approval, and extension checks
  are skipped when the user approved a protected file.
- **Markdown streaming**: preserved newline between buffer and
  accumulator on flush.
- **UI**: stats line uses a consistent BULLET prefix.
- **Windows**: tilde-expansion tests set `USERPROFILE`; content-type
  detection no longer hangs.
- **Config**: read `allowed_extensions` defaults to empty (allow all).

### Changed
- **Liveness management** moved from `Session` to the `Agent` layer.
- **Makefile**: `upload` target split from `publish` for granular PyPI
  uploads.

## 0.10.1 (2026-08-12)
### Fixed
- **Ollama cloud base URL**: Corrected the Ollama cloud API endpoint in the
  bootstrap wizard.
### Added
- **`show_prompts` parameter**: `InteractiveUIHandler` now accepts a
  `show_prompts` flag (default `True`). When disabled, user input is not
  echoed to the console. Bootstrap handlers in `chat` and `init` pass
  `show_prompts=False` so API keys and other sensitive input are not
  displayed during the wizard.

# Changelog

All notable changes to yoker are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## 0.10.0 (2026-09-16)

### Added

- **Config `enabled` master switch**: New `enabled` field on `Config` acts as
  a global on/off switch for the agent system. When set to `false`, the agent
  short-circuits without making any backend calls, useful for feature
  flagging and testing.

- **Markdown streaming with timestamps and MotD**: The interactive UI now
  supports markdown streaming with live rendering, conversation timestamps,
  and a configurable Message of the Day (MotD) banner displayed on startup.

- **Gitignore-aware search and list**: The `search` and `list` tools now
  respect `.gitignore` patterns by default, preventing noisy results from
  build artifacts, virtual environments, and other ignored paths.

- **Sleep tool**: New `sleep` tool allows agents to pause execution for
  1–300 seconds, enabling polling workflows and wait-for-state patterns.

- **Git tag creation**: The `git` tool now supports creating annotated tags
  (`tag create`) and pushing tags to remote, completing the tag lifecycle
  alongside the existing `tag list` and `tag last` operations.

- **`make verify-wheel` target**: New Makefile target to verify built wheel
  contents before publishing, complementing the existing `build` target.

- **Unified tool output formatting**: Tool call results now render with
  middle-collapse previews — long outputs are truncated in the middle with
  a `…` marker, keeping both the head and tail visible.

- **Show spinners flag**: `InteractiveUIHandler` now accepts a
  `show_spinners` flag to suppress spinner animations, useful for session
  recording and demo generation.

### Fixed

- **Malformed JSON in tool call arguments**: The agent processing loop now
  detects and repairs malformed JSON in tool call arguments (e.g., unescaped
  quotes, trailing commas) and returns descriptive error messages instead
  of crashing the tool execution loop.

- **Post-filter error preservation**: Short error messages are no longer
  stripped by `post_filter` — the filter now preserves the error field while
  still truncating oversized output.

- **Bootstrap wizard config path**: The wizard now shows the actual config
  file path in its opening step, clarifying where the configuration will be
  written.

- **Bootstrap model list**: Updated curated Ollama models from GLM-5 to
  GLM-5.2.

- **Ollama API key**: `OLLAMA_API_KEY` is now set from the config's
  `api_key` field, enabling authenticated Ollama cloud API usage.

- **List tool `max_depth` semantics**: Changed `max_depth` semantics so
  `1` means root-only (listing just the directory's immediate contents),
  matching user expectations.

- **Session file check**: Moved the session file existence check inside the
  `Session` context manager, preventing premature file access errors.

- **GitHub release notes**: Markdown characters in release notes and PR text
  are now properly escaped, preventing CLI parsing issues.

- **Demo screenshot regeneration**: Fixed demo scripts to use `Session`
  for proper `agent`/`send_message` tool injection, route `MarkdownStreamer`
  output through the recording console, show the MotD banner, and suppress
  spinners for clean recordings.

- **Search path normalization**: Paths in search results are now normalized
  to POSIX format, and trailing whitespace in formatting output is removed.

- **Tool call display**: `post_filter` is now shown in the tool call display,
  and an inline width threshold prevents excessively wide output.

- **Multi-line argument indentation**: Stripped braces and fixed
  multi-line argument indentation in tool call rendering.

- **Markdown double styling**: Rendered output is now written via `print`
  to avoid double Rich styling on markdown content.

- **mypy compliance**: Resolved `no-any-return` warning in
  `_is_skill_discovery_block`.

### Changed

- **Documentation overhaul**: Unified tagline to "Python-first agent harness
  framework", updated all documentation for 0.10.0, cleaned up TODO.md,
  and noted the cosmetic asyncio traceback in test stderr as a known issue.

- **Demo screenshots regenerated**: All demo screenshots refreshed to
  reflect the current UI state.

## 0.9.0 (2026-08-05)

### Added

- **Ollama API usage in status line**: When using the Ollama backend with an
  API key configured, the status line now shows session and weekly usage
  percentages from the Ollama cloud API (`https://ollama.com/api/usage`).
  This requires `httpx` (already a dependency) and the `api_key` field set
  in the Ollama provider config.

- **Wall-clock elapsed time**: The status line now reports wall-clock
  elapsed time for the entire turn (stream + tool calls), measured with
  `time.monotonic()`. This replaces the backend-reported
  `total_duration_ms` which only reflected the last chunk's latency, not
  the full turn duration. The timing is provider-independent.

- **Session resume hint on shutdown**: When exiting an interactive session
  with persistence enabled, a hint is printed showing the session ID and
  the `--resume` command to continue the conversation later.

- **AGENTS.md context injection**: If an `AGENTS.md` file exists in the
  working directory, its contents are embedded directly into the system
  prompt at startup, providing project-specific instructions to the agent.

- **Dict-based agent/skill directories**: The `agents.directories` and
  `skills.directories` config fields now accept a dict mapping
  `namespace → path` (e.g., `[agents.directories]` / `c3 = "../c3/agents"`)
  in addition to the list form. The dict form gives explicit control over
  the namespace name.

- **GitHub tool enhancements**: Added `workflow_logs` operation (fetches
  failed-step logs), `pr_reviews` and `pr_comments` operations, and
  `include_comments` option on `pr_view`. Removed internal output
  truncation in favor of `post_filter` guidance.

- **Git tool enhancements**: Added `pull`, `tag` (list/last), and
  `branch show_current` operations. Git `diff` and `show` now support
  files in subdirectories.

- **Search tool accepts file paths**: The `search` tool now accepts a
  single file path (not just directories) for targeted content search
  within one file.

- **Skill lazy resource loading**: Skills can now declare resources that
  are loaded on-demand via the `skill` tool, rather than all being loaded
  at startup.

- **Bare skill name resolution**: Skills can now be referenced by their
  bare name (without namespace prefix) when there is no ambiguity.

- **File tool (copy/move/delete)**: New `file` tool for filesystem
  operations (copy, move, delete) with recursive support.

- **`make clean-sessions`**: New Makefile target to delete session `.jsonl`
  files older than a configurable age.

- **Custom Yoker badge**: Added a custom SVG badge for README
  documentation.

### Changed

- **`output_stats` signature**: The `UIHandler.output_stats` method now
  accepts an optional `usage_limits: dict[str, object] | None` parameter.
  All implementations (`InteractiveUIHandler`, `BatchUIHandler`) and
  test mocks have been updated.

- **`update` tool: `line_range` parameter**: The `replace` and `delete`
  operations now accept a `line_range` parameter (`[start, end]`, 1-indexed,
  inclusive) to edit a range of lines directly without string matching. This
  avoids ambiguous matches in large files and enables precise line-targeted
  edits. When `line_range` is provided, it takes precedence over `old_string`.

- **`update` tool: `require_exact_match` per-call override**: The
  `require_exact_match` parameter can now be passed per-call to override the
  config default. When set to `false`, whitespace is normalized for matching
  (regex-based fuzzy match), and the first occurrence is used without
  ambiguity errors.

- **`update` tool: improved error messages**: When `old_string` is not found,
  the error message now includes the closest matching line with a similarity
  percentage. When multiple matches are found, the error lists the line
  numbers of all occurrences and suggests using `line_range`.

- **`update` tool: `insert`/`append` operations**: Replaced
  `insert_before`/`insert_after` with a cleaner set: `insert` (content
  appears at `line_number`, pushing existing lines down) and `append` (add
  content at end of file, no `line_number` needed). Operations are now:
  `replace`, `insert`, `append`, `delete`.

- **Default Tools Behavior (M.2, Option C)**: Agent definitions without a
  `tools:` line now grant ALL config-enabled tools at runtime. Previously,
  a missing `tools:` field raised `ConfigurationError` at load time. To get
  "no tools", explicitly set `tools:` (bare), `tools: null`, `tools: ~`,
  `tools: ""`, or `tools: []` in YAML; or pass `tools=None` / `tools=[]` to
  `AgentDefinition()` / `yoker.agent()`. A visible WARN event
  `agent_tools_default_granted` is emitted whenever all-tools is granted by
  omission, so operators can spot agents that silently broadened on upgrade.
  The `ALL_TOOLS` sentinel is a module-level `[]` (empty list) in
  `yoker.agents.schema`, used as the default value of
  `AgentDefinition.tools`. It distinguishes "no `tools:` line" (`ALL_TOOLS` —
  all tools) from "tools explicitly empty" (`[]` — no tools) via identity
  (`is ALL_TOOLS`). The sentinel is resolved in exactly ONE place —
  `Agent._filter_tools_by_definition` — which replaces it with the real list
  of all tool names from the registry; everywhere else, `tools` is just a
  list.

- **Validator on runtime path**: `validate_agent_definition` is now called
  during `Agent` construction (warnings only; never blocks). Unknown bare
  tool names and disabled tools produce warnings instead of raising. The
  runtime `_warn_missing_tools` check stays authoritative for tool
  availability.

- **Thin API tools contract aligned with `AgentDefinition` (M.2)**: The
  `yoker.agent()` / `yoker.process()` / `yoker.do()` / `yoker.session()`
  `tools` kwarg now defaults to the `ALL_TOOLS` sentinel (all tools) and is
  passed through UNCHANGED to `AgentDefinition` — the previous api.py bridge
  that translated `tools=None` → `ALL_TOOLS` (all tools) is removed. This
  eliminates the dual contract: `yoker.agent(tools=None)` now means "no
  tools" (matching `AgentDefinition(tools=None)`), not "all tools". Omit the
  arg (or pass `ALL_TOOLS` explicitly) for all tools; `tools=[]` also
  disables all tools; `tools=["read", ...]` filters as before.

- **Builtin tool names namespaced**: Built-in tools are now prefixed with
  `yoker:` namespace (e.g., `yoker:read`, `yoker:write`) for consistency
  with agent and skill namespacing.

- **Async subprocess execution for tool calls**: Tool calls are now rendered
  immediately in the UI while subprocess execution runs asynchronously,
  improving responsiveness.

- **Post-filter improvements**: `post_filter` now applies on failure results,
  filters the `error` field, and enforces output limits after filtering.
  Tool args are no longer mutated. Content metadata content is also filtered.

- **Git flag naming**: Underscores in git flag names are now converted to
  dashes (e.g., `show_current` → `show-current`) for consistency with Git CLI
  conventions.

### Fixed

- **Config union type corruption**: Reordered `directories` field type from
  `tuple[str, ...] | dict[str, str]` to `dict[str, str] | tuple[str, ...]`
  to prevent dacite from matching TOML dicts against the tuple type first
  (which iterated dict keys character-by-character, corrupting
  `{"c3": "../c3/agents"}` into `("c", "3")`).

- **Agent process-consumer task leak**: The process-consumer task is now
  properly cancelled when an agent is released, preventing asyncio warnings.

- **Tool-execution spinner during approval**: The spinner is now stopped
  before the approval prompt is shown, preventing UI overlap.

- **Windows CI failures**: Unix-only tests are now skipped on Windows to
  fix CI. The `nul.txt` test fixture was renamed to avoid the Windows
  reserved device name.

- **GitHub workflow run IDs**: Raised `_MAX_NUMBER` to 64-bit to handle
  large GitHub Actions workflow run IDs.

- **GitHub empty array handling**: GitHub tool now handles empty arrays in
  responses and removes `--json` flag for write operations.

- **Session back-reference**: `agent._session` is now set for all agents,
  fixing the `/agents` slash command.

- **Agents allowlist default**: Agent definitions without an `agents`
  allowlist in frontmatter now default to `ALL_AGENTS` instead of raising
  an error.

### Upgrade Notes

- **Plugins with a missing `tools:` line gain all tools on upgrade.** Add an
  explicit `tools: []` to agent definition files that should have no tools.
  The bundled `examples/plugins/demo/.../backwards.md` already uses
  `tools: []` as a regression guard.

- **`update` tool: `insert_before`/`insert_after` removed.** Use `insert`
  at `line_number` (content appears at that line) or `insert` at
  `line_number + 1` to replicate `insert_after`. Use `append` to add
  content at end of file.

## 0.8.0 (2026-07-15)

### Added

- **CLI Subcommands (MBI-004)**: Seven subcommands registered with Clevis:
  `chat` (default, interactive REPL), `run`, `init`, `config`, `loop`,
  `inspect`, and `container`.
- **Config-override manifest layer**: `agent.toml` support for agentic
  packages, with deep-merge of nested table overrides and TOML array
  replacement for tuple-typed fields.
- **Two-phase source resolution**: `resolve_source()` then `load_source()`
  supports module, folder, GitHub URL, and zip file sources.
- **Security trust gate**: `check_source_allowed()` is a security invariant
  — `load_source()` is never called before the trust gate returns True.
  Non-interactive mode rejects untrusted sources by default
  (`YOKER_TRUST_SOURCE=1` env var overrides).
- **`yoker run <source>`**: Flagship command for running agentic packages,
  with `--dry-run`, `--persist`, and `--session-id` options.
- **`yoker inspect <source>`**: Read-only source report (no trust gate, no
  code execution).
- **`yoker loop <source>`**: Interval-based execution with graceful shutdown.
- **`yoker container <source>`**: Dockerfile/Containerfile generation with
  security hardening.
- **`yoker init`**: Config generation with bootstrap wizard integration.
- **`yoker config`**: Display effective configuration with API key masking.

### Changed

- **Clevis upgraded from 0.3.3 to 0.7.0**: Replaced `sys.argv` patching with
  native Clevis `default_cmd=True`; replaced private Clevis internals with
  the public 0.7.0 API (`clevis.load`, `build_default_cascade`,
  `get_config(cascade=...)`); removed all `TODO(clevis-feature-request)`
  workarounds and `type: ignore[attr-defined]` comments.
- **`dacite` added as explicit dependency**: Was previously transitive
  through Clevis.

### Fixed

- **Windows-specific test failures**: Path and permission assertions now
  pass on Windows.

## 0.7.0 (2026-07-07)

### Added

- **Python API Facade (MBI-003)**: New thin single-module public API in
  `yoker.api` exposing `process`, `do`, `agent`, `session`, `run_sync`, and
  `ThinkingLiteral`. `yoker.agent(**kwargs)` is the reusable factory
  (builder → customised `Config` → `Agent`); `yoker.process` / `yoker.do`
  are one-shot helpers built on it; `yoker.session(...)` is an async context
  manager yielding the real `yoker.session.Session`.
- **Session.send accepts Agent instances**: `Session.send(*, to, from_,
  content)` resolves `Agent` instances back to ids via `_id_of()`; the
  `agent` tool and `send_message` tool fold spawn/process/release inline.
- **Session.create_primary_agent**: Single end-to-end path for creating the
  primary agent, used by both `__main__.py` and `yoker.session()`.
- **Python API examples**: New `examples/python_api/` covering builder,
  one-shot, sync usage, sessions, event handling, skill invocation, and a
  full workflow.
- **Context Manager Factory**: `yoker.context.factory` constructs the
  context manager agent-scoped from `Config`; `Session` owns the lifecycle
  and passes the context manager into `Agent`.
- **Structured Logging at CLI Startup**: CLI wires `structlog` configuration
  at startup.

### Changed

- **Agent package relocated**: `yoker.agent` → `yoker.core` (unified `Agent`
  class backed by `_setup.py` / `_processing.py`).
- **Plugin loader merged**: `yoker.plugins.loader` consolidated;
  registries (`ToolRegistry`, `SkillRegistry`, `AgentRegistry`) now own
  their own plugin registration. `register_tools` / `register_skills` free
  functions removed.
- **API collapsed to a module**: `yoker.api` is now a single module
  (`api.py`), not a package; `_internal`/`one_shot`/`session` submodules
  removed.
- **Config dataclasses unfrozen**: `Config` and provider configs are now
  mutable, eliminating `replace()` workarounds.
- **session() signature explicit**: `yoker.session(id=..., *, persist=True,
  fresh=False, **kwargs)` uses explicit kwargs instead of a kwargs-pop block.
- **Plugins-enabled sanity check**: Moved into `Config` validation;
  `check_plugins_enabled` removed. The plugins-disabled warning is now
  visible and covers CLI `--with` packages too.
- **Clearer session error**: `Session` emits a clear error when a configured
  agent cannot be resolved.

### Removed

- **Public API removals**: `ApiSession`, `make_config`, `Message`,
  `SpawnResult`, `EventReplayAgent`, `ThinkingMode` (public re-export),
  `add_event_handler` / `remove_event_handler` / `get_event_handlers`
  (use `Agent.on_event(handler)`), `max_recursion_depth` config field,
  `load_configured_plugins`, `check_plugins_enabled`,
  `register_tools` / `register_skills` free functions,
  `yoker.plugins.registration` module, `yoker.api` submodules
  (`_internal` / `one_shot` / `session`), `yoker.events.replay`,
  `yoker.session.message`, `yoker.session.spawn_result`.

### Fixed

- **5 code regressions from MBI-003 cleanup**:
  - `Agent.__init__` coerces `plugins=None` to `()` so `load_plugins` never
    receives a non-iterable `None`.
  - `context/factory` sanitizes `agent_id` colons before filename
    interpolation so namespaced ids like `file:researcher` pass
    `validate_session_id`.
  - `Session._derive_config` deep-copies `parent_config` before applying
    model override, leaving the caller's sub-config untouched.
  - `render_config_toml` deep-copies config before applying overrides so
    `_set_dotted` no longer mutates the caller's `Config`.
  - `agents/registry` drops a stray `raise` in `register_config_agents` so
    invalid/malformed agent dirs are warned-and-skipped, not fatal.
- **CLI logging wiring**: Structured logging configured at startup.
- **Stale test mocks**: Fixed 6 stale `yoker.core.Agent` mock targets.

### Documentation

- Refreshed `CLAUDE.md` module structure to match the current tree.
- Refreshed user-facing docs: `README.md`, `docs/quickstart.md`,
  `docs/api/index.md`, `docs/rationale.md`.
- Cleaned up `PLAN.md` and `TODO.md`; added `DEVELOPMENT.md`.
- Updated `MBI-003 Python API` design doc.

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
