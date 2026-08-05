# Yoker Agent Guide

Essential context for working on the Yoker codebase. For user-facing
documentation, see [README.md](README.md).

## IMPORTANT CURRENT DEVELOPMENT PHASE

We are in a dogfooding phase, so we're fixing problems in Yoker with Yoker. This means that you can't test fixes due to the new code not being loaded. If you want to test things, FIRST ASK me to restart the session. I can use the `--resume` argument to reload the current context, which allows me to stop and start with the new code active and the same context.

YOU DON'T HAVE DIRECT CLI ACCESS! This is intentional.

IF A TOOL IS MISSING: STOP!
IF A TOOL FAILS: STOP!

Don't look for workarounds!

Address the problem first. You are working on your own codebase, so you can check the code of the tool yourself to confirm the failure. If sub-operation for a tool is missing: report it, so we can decide to add it first.

Don't try to spawn a random agent to do something you don't have the right tool for.

## Positioning

**USP:** Add LLM capabilities to your Python apps and modules without worrying
about the agentic foundations. Agentic Functions.

Yoker lets developers enhance existing Python code with LLM-powered features
without needing to understand or build the underlying agent infrastructure. The
key differentiator is the concept of **Agentic Functions** — bringing LLM
capabilities into regular Python code seamlessly.

## Conventions

- **Indentation**: Two spaces in all file types.
- **Package manager**: `uv` (see `Makefile` for standard targets).
- **Code quality**: `make check` runs format, lint, typecheck, and test.
- **Entry point**: `python -m yoker` is the application entry point.
- **Version source of truth**: `src/yoker/__init__.py` must match `pyproject.toml`.
- **Commit attribution**: Use `🤖 Implemented together with Yoker` as the trailer line on agent-made commits. No `Co-authored-by` format.
- **Fully qualified imports**: `from yoker.backends.protocol import ChatChunk` — not `from yoker.backends import ChatChunk`.

## Makefile

The Makefile has many targets that are useful and available through the `make` tool:

```
build           Build distribution packages
check-all       Run all quality checks and test all
check           Run all quality checks and test
clean-all       Remove virtualenv and lock file
clean-sessions  Delete session .jsonl files older than $(SESSION_MAX_AGE_DAYS) days
clean           Remove build artifacts
demo            Generate main session screenshot (media/session.svg)
demos           Generate all demo screenshots
docs-view       Build and open documentation
docs            Build HTML documentation
env-dev         Install all dependencies (dev + docs)
env-run         Install runtime dependencies only
format-check    Run all quality checks
format          Format code and fix linting issues
install-pythons Install Python 3.10, 3.11, 3.12
lint            Check code for linting issues
pre-publish     Pre-publication checks (run before publishing)
publish-test    Publish to TestPyPI
publish         Publish to PyPI (runs pre-publish checks)
run             Run the application
test-all        Run tests on all Python versions
test-cov        Run tests with coverage
test            Run tests (usage: make test / optional: TEST=file|file:test_name)
typecheck       Run type checking
```

## Tool Output Discipline

**Always use `post_filter` on every tool call** to keep only lines relevant to
the task. Tool outputs can be very large and consume context budget rapidly.

- `make test` / `make check`: `post_filter="FAILED|ERROR|error|Traceback|assert"`
  — positive output (passing tests, formatting success) is useless noise.
- `read` / `search` on large files: filter for structure markers (`class |def |import `)
  or specific patterns (`TODO|FIXME|HACK`).
- `git log` / `git diff`: filter for the specific file, author, or pattern you need.
- `list` on large directories: use `pattern` or `post_filter` to avoid flooding
  context with thousands of entries.

**Rule of thumb**: if you expect more than ~20 lines of output, you should be
filtering. Not filtering wastes context and processing credit on irrelevant
content.

## Module Structure

```text
src/yoker/
├── __init__.py              # Public API exports (Agent, Session, Config, process, do,
│                           #   agent, session, run_sync, ThinkingLiteral)
├── __main__.py              # CLI entry point — dispatches to subcommand handlers
├── api.py                   # Thin Pythonic API facade: process(), do(), agent(), 
│                           #   session(), run_sync() — no private helpers
├── exceptions.py            # Exception hierarchy (NetworkError, ValidationError, ...)
├── logging.py               # Structured logging (structlog)
├── resources.py             # Resource location for definition files (skills, agents)
├── schema.py                # NameSpaced base class for namespaced dataclasses
├── py.typed                 # PEP 561 typed-package marker
│
├── core/                    # Agent layer (no UI, no Session coupling)
│   ├── __init__.py          # Unified Agent class — async, event-emitting, Session-agnostic
│   ├── _processing.py       # Message processing, streaming, tool loop
│   ├── _setup.py            # Client, guardrail, registry setup
│   └── thinking.py          # Thinking mode enum
│
├── agents/                  # Agent definition parsing (schema, loader, registry)
│   ├── schema.py            # AgentDefinition frozen dataclass (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter; load from dirs/packages
│   ├── registry.py          # AgentRegistry (UserDict keyed by namespaced name)
│   └── validator.py         # validate_agent_definition against config constraints
│
├── backends/                # Provider-neutral backend layer
│   ├── protocol.py          # ModelBackend Protocol, ChatChunk, UsageStats
│   ├── factory.py            # create_backend() dispatch from Config
│   ├── ollama.py             # OllamaBackend (native SDK)
│   ├── litellm.py            # LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
│   └── trust.py              # Custom base URL trust validation
│
├── bootstrap/               # First-run bootstrap wizard
│   ├── wizard.py             # Wizard orchestration
│   ├── steps.py              # Provider-specific setup steps
│   ├── providers.py          # Curated model lists and provider metadata
│   ├── detect.py             # Existing-config detection
│   └── modellist.py          # Model list rendering
│
├── builtin/                 # Built-in tools registered via __YOKER_MANIFEST__
│   ├── __init__.py          # Manifest declaring read, write, git, github, make, 
│   │                        #   websearch, webfetch, search, list, mkdir, existence, skill
│   ├── read.py              # read: file contents (offset/limit slicing)
│   ├── write.py             # write: file contents
│   ├── update.py            # update: edit existing file contents (diff-based)
│   ├── list.py              # list: directory contents
│   ├── mkdir.py             # mkdir: create directories
│   ├── existence.py         # existence: check files/folders exist
│   ├── search.py            # search: file and content search (grep-like, accepts files and directories)
│   ├── git.py               # git: Git operations (status, log, diff, branch, show, 
│   │                        #   add, commit, push, checkout, rm, pull, tag)
│   ├── github.py            # github: read-only GitHub operations via gh CLI
│   ├── make.py              # make: Makefile target execution
│   ├── webfetch.py          # webfetch: fetch web content through a backend
│   ├── websearch.py         # websearch: search the web through a backend
│   └── skill.py             # make_skill_tool factory (skill invocation tool)
│
├── config/                  # Configuration system (Clevis-based)
│   ├── __init__.py          # Config dataclasses, get_yoker_config()
│   ├── providers.py         # Provider configs (Ollama, OpenAI, Anthropic, Gemini, Generic)
│   ├── validators.py        # Field validators
│   └── writer.py            # TOML writer with chmod 600
│
├── context/                 # Context managers (Protocol-based)
│   ├── protocol.py          # ContextManager @runtime_checkable Protocol
│   ├── manager.py           # BaseContextManager (in-memory base)
│   ├── basic.py             # SimpleContextManager (env reminder + system prompt)
│   ├── wrapper.py           # ContextManagerWrapper (pure proxy)
│   ├── persisted.py         # Persisted (JSONL persistence via bulk-rewrite)
│   ├── factory.py           # Context manager factory — agent-scoped from Config
│   ├── interface.py         # ContextStatistics, SessionMetadata dataclasses
│   ├── session.py           # list_sessions, load_session_metadata (JSONL utilities)
│   └── validator.py         # validate_session_id, validate_storage_path, is_safe_path
│
├── events/                  # Event types and serialization
│   ├── types.py             # Event dataclasses (Message, Tool, Error, Stats, ...)
│   ├── session_event.py     # SessionEvent envelope (tags Event with agent_id)
│   └── recorder.py          # EventRecorder, serialize/deserialize_event (JSONL)
│
├── plugins/                 # Plugin system (discover, manifest, trust)
│   ├── loader.py            # Plugin package discovery via __YOKER_MANIFEST__
│   ├── manifest.py          # PluginManifest dataclass (tools, skills, agents declarations)
│   ├── file_manifest.py     # File-based manifest (agent.toml) parser
│   └── security.py          # Plugin trust checks (global opt-in + per-plugin trust table)
│
├── skills/                  # Skill definitions and registry
│   ├── schema.py            # Skill dataclass (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter into Skill objects
│   ├── registry.py          # SkillRegistry: lookup skills by name
│   └── injection.py         # Skill discovery + invocation context blocks
│
├── tools/                   # Tool framework
│   ├── annotations.py       # Path, Url, Query, Text markers + @tool decorator
│   ├── schema.py            # ToolSpec, build_tool_spec() (function→tool introspection)
│   ├── registry.py          # ToolRegistry (UserDict of ToolSpec)
│   ├── context.py           # Tool execution context (config/backends without exposing Agent)
│   ├── content_type.py      # Content type detection from file content and path extension
│   ├── diff.py              # generate_diff() — shared unified-diff helper
│   ├── guardrails/          # Guardrail framework
│   │   ├── env.py           # EnvGuardrail (env var allowlist + hard denylist)
│   │   └── path.py          # PathGuardrail (traversal, size, extension, protected_files)
│   └── web/                 # Web tool backends and guardrails
│       ├── backend.py       # Web search/fetch backend protocol and implementations
│       ├── guardrail.py     # Web guardrail (SSRF, domain allow/deny lists)
│       └── types.py         # SearchResult dataclass, WebSearchError
│
├── session/                 # Session construct (team-of-agents coordinator)
│   ├── __init__.py          # Session: async context manager owning a team of agents;
│   │                        #   spawn(), release(), send(), agent property, inject_tools()
│   └── tools.py             # Session-injected tools: agent + send_message factories
│
├── cli/                     # CLI subcommand config classes + handlers
│   ├── commands.py          # @configclass(cmd=...) subcommand configs registered with Clevis
│   ├── shared.py            # load_subcommand_config() + manifest variant
│   ├── chat.py              # yoker chat: interactive REPL (default subcommand)
│   ├── run.py               # yoker run: load source + trust gate + non-interactive execution
│   ├── config_cmd.py        # yoker config: display effective config
│   ├── init.py              # yoker init: generate default config
│   ├── inspect.py           # yoker inspect: read-only source report
│   ├── loop.py              # yoker loop: interval execution
│   ├── container.py         # yoker container: Dockerfile/Containerfile generation
│   └── sources.py           # resolve_source() + load_source() — two-phase source resolution
│
└── ui/                      # UI layer (strictly separated from the Agent layer)
    ├── handler.py           # UIHandler protocol
    ├── bridge.py            # UIBridge: events -> UIHandler method calls
    ├── interactive.py       # InteractiveUIHandler (Rich append-only + prompt_toolkit)
    ├── batch.py             # BatchUIHandler (stdin/stdout/stderr for pipelines)
    └── commands/            # Slash commands (/help, /agents, /skills, /tools, /think, /context, /config)
```

## Architecture

### Layer Separation

The codebase has strict layer boundaries:

```
Backend Layer:    backends/     — ModelBackend Protocol → provider SDKs
Agent Layer:      core/         — async Agent, event-emitting, no UI coupling
Session Layer:    session/      — team coordinator, spawning, inter-agent messaging
UI Layer:         ui/           — presentation only, receives events via UIBridge
```

**Agent** is async-only and emits `Event` objects via `Agent.on_event()`. It has
no direct UI dependency. **Session** owns the team of agents — registry, spawning,
backend sharing, event aggregation, and inter-agent messaging.

### Event Flow

```
Backend.chat_stream() → ChatChunk → Agent._consume_stream() → Event → UIBridge → UIHandler
```

For multi-agent sessions, sub-agent events are wrapped in `SessionEvent(agent_id, event)`
envelopes before forwarding to session-level handlers.

### Trust Gate (Security Invariant)

`yoker run` loads agentic packages from external sources. The trust gate is a
**security invariant**: `load_source()` is NEVER called before
`check_source_allowed()` returns True. Non-interactive mode rejects untrusted
sources by default (`YOKER_TRUST_SOURCE=1` env var overrides). This ordering
must be preserved in all code paths.

### Tool Framework

Tools are plain functions or callable classes. Guardrail metadata comes from
`yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`). `ToolRegistry`
stores `ToolSpec` objects built via `build_tool_spec()` which introspects the
function signature.

Built-in tools are registered via the plugin loader from
`yoker.builtin.__YOKER_MANIFEST__`. The `agent` and `send_message` tools are
session-injected (need runtime dependencies not available to the static manifest).
The `skill` tool is added via the `make_skill_tool` factory.

### Protected Files Guardrail

`PathGuardrail` enforces a `protected_files` denylist (default: `Makefile`,
`pyproject.toml`, `yoker.toml`, `.git/config`, `.git/hooks/*`,
`.github/workflows/*.yml`, `uv.lock`, etc.). The `write` and `update` tools are
blocked; `read` is never blocked. In interactive mode, an approval handler can
render a diff and prompt y/N. In batch mode, always blocked (fail-safe). An
empty tuple disables all protections (explicit opt-out).

### Git Tool Permission Model

Git operations use an `auto_permission` allowlist:
- `allowed_commands` — all commands the tool may execute
- `auto_permission` — subset auto-approved without asking (default: status, log, diff, branch, show, add)
- Operations in `allowed_commands` but NOT in `auto_permission` (e.g. commit, push) require interactive approval
- In batch mode (no handler), blocked — fail-safe

### Context Persistence

`Persisted` wraps a `BaseContextManager` and writes conversation history to
JSONL. On resume (`fresh=False`), the `Persisted.agent` setter detects
pre-loaded conversation history and preserves it — it does NOT call `clear()`
when resuming. This is important: calling `clear()` would wipe loaded history.

## Public Python API

Exports from `yoker/__init__.py`:

- `Agent` — async, event-emitting, Session-agnostic primitive
- `Session` — async context manager owning a team of agents
- `Config` — configuration dataclass
- `process(prompt, **kwargs)` — one-shot LLM call (no tools, no system prompt)
- `do(skill_name, prompt, args="", **kwargs)` — one-shot skill invocation
- `agent(**kwargs) -> Agent` — reusable agent factory
- `session(id=..., *, persist=True, fresh=False, **kwargs)` — async context manager yielding `Session`
- `run_sync(coro)` — wraps `asyncio.run`

## CLI

CLI arguments are auto-generated by Clevis from the `Config` dataclass.
Subcommands: `chat` (default), `run`, `init`, `config`, `inspect`, `loop`,
`container`. Config-backed subcommands extend `Config`; standalone subcommands
have their own fields.

Common UI-related flags:
- `--ui-mode {interactive,batch}`
- `--ui-show-thinking`
- `--ui-show-tool-calls`
- `--ui-show-stats`
- `--agents-definition PATH`
- `--session-id <name>` / `--resume <name>`

## Adding a New UI Handler

1. Implement the `UIHandler` protocol in `src/yoker/ui/<name>.py`.
2. Add the implementation to `src/yoker/ui/__init__.py` exports.
3. Wire the handler in `src/yoker/__main__.py` `_create_ui()` if it should be selectable via `--ui-mode`.
4. Add an example under `examples/` showing usage.
5. Update this document and `README.md`.
