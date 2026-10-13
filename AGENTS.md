# Yoker Agent Guide

Essential context for working on the Yoker codebase. For user-facing documentation, see [README.md](README.md).

## Ecosystem (Release Checklist Inputs)

Satellite projects and channels to keep in sync with each release
(release process R8 — see c3:release):

- **Consumer projects** (upgrade + verify after each release):
  - `../yoker-assistant`
  - `../yoker-writing-assistant`
- **Website**: `../yoker.dev` (Jekyll site — version references + feature mentions)
- **Announcement post**: `../yoker.dev/_posts/` — draft post for the upcoming
  release, updated at R8, owner-reviewed before publishing

## Makefile — Yoker-Specific Targets

Standard targets (`build`, `check`, `clean`, `format`, `install`, `lint`, `publish`, `run`, `test`, `test-all`, `test-cov`, `typecheck`, ...) are described in `AGENTS.global.md` — run `make help` for the full list. These are the targets unique to this project:

```
check-all       Run all quality checks and test all
clean-sessions  Delete session .jsonl files older than $(SESSION_MAX_AGE_DAYS) days
demo            Generate main session screenshot (media/session.svg)
demos           Generate all demo screenshots
demos-to-docs   Copy generated demo files to docs/_static folder
docs-view       Build and open documentation
docs            Build HTML documentation
format-check    Run all quality checks
install-pythons Install Python 3.11, 3.12, 3.13, 3.14
publish-test    Publish to TestPyPI
upload          Upload to PyPI only (DON'T USE DIRECTLY — use `publish` target)
```

!!! IMPORTANT !!!
There are a lot of tests!
When  doing tests (`make(test)`, `make(check)`), set a higher `timeout_ms`, e.g. 300000.

## Known Issues

### Known cosmetic stderr noise (do not investigate)

`make test` on Python 3.11 emits a `RuntimeError: Event loop is closed` traceback in **stderr** from `asyncio/base_subprocess.py`. This is a known CPython 3.11 bug: subprocess transports are garbage-collected after the event loop is already closed, and their `__del__` calls `call_soon` on the dead loop. It is triggered by tests that spawn subprocesses (git, make tool tests).

**This is not a test failure.** All tests pass (exit code 0). Do not investigate or attempt to fix this — it is a Python stdlib issue, not a yoker bug.

## Module Structure

```text
src/yoker/
├── __init__.py, __main__.py, api.py   # public API facade (process/do/agent/session), CLI dispatch
├── exceptions.py, logging.py, resources.py, schema.py   # exceptions, structlog, def-file locations, NameSpaced base
├── py.typed                           # PEP 561 marker
├── core/                              # Agent layer: async event-emitting Agent, processing loop, thinking mode
├── agents/                            # agent-definition parsing/registry (Markdown+frontmatter, primary.md, validator)
├── backends/                          # provider-neutral model backends (protocol/factory; ollama, litellm) + trust validation
├── bootstrap/                         # first-run wizard (steps, providers, config detection)
├── builtin/                           # built-in tools registered via __YOKER_MANIFEST__ (read/write/update/git/github/make/web/…)
├── config/                            # Clevis-based configuration (providers, validators, TOML writer)
├── context/                           # context managers + JSONL persistence (protocol/manager/basic/persisted/factory)
├── events/                            # event types, SessionEvent envelope, JSONL recorder
├── plugins/                           # plugin discovery/manifest/trust (__YOKER_MANIFEST__, agent.toml)
├── skills/                            # skill schema/loader/registry + injection
├── tools/                             # tool framework: annotations, spec/registry, guardrails (env, path), web backends
├── session/                           # Session: team-of-agents coordinator (spawn/release/send) + injected agent tools
├── cli/                               # Clevis subcommand configs + handlers (chat/run/init/config/inspect/loop/container)
└── ui/                                # UI layer, strictly separated: handlers (interactive/batch) + slash commands
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

**Agent** is async-only and emits `Event` objects via `Agent.on_event()`. It has no direct UI dependency. **Session** owns the team of agents — registry, spawning, backend sharing, event aggregation, and inter-agent messaging.

### Event Flow

```
Backend.chat_stream() → ChatChunk → Agent._consume_stream() → Event → UIBridge → UIHandler
```

For multi-agent sessions, sub-agent events are wrapped in `SessionEvent(agent_id, event)`
envelopes before forwarding to session-level handlers.

### Trust Gate (Security Invariant)

`yoker run` loads agentic packages from external sources. The trust gate is a **security invariant**: `load_source()` is NEVER called before `check_source_allowed()` returns True. Non-interactive mode rejects untrusted sources by default (`YOKER_TRUST_SOURCE=1` env var overrides). This ordering must be preserved in all code paths.

### Tool Framework

Tools are plain functions or callable classes. Guardrail metadata comes from `yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`). `ToolRegistry` stores `ToolSpec` objects built via `build_tool_spec()` which introspects the function signature.

Built-in tools are registered via the plugin loader from `yoker.builtin.__YOKER_MANIFEST__`. The `agent` and `send_message` tools are session-injected (need runtime dependencies not available to the static manifest). The `skill` tool is added via the `make_skill_tool` factory.

### Protected Files Guardrail

`PathGuardrail` enforces a `blocked_write_paths` denylist (default: `**/Makefile`, `**/pyproject.toml`, `**/yoker.toml`, `**/.git/config`, `**/.git/hooks/*`, `**/.github/workflows/*.yml`, `**/uv.lock`, etc. — the `**/` prefix protects these names at any depth, so a scratch subdirectory does not bypass the denylist). The `write` and `update` tools are blocked. In interactive mode, an approval handler can render a diff and prompt y/N. In batch mode, always blocked (fail-safe). An empty tuple disables all protections (explicit opt-out).

### Git Tool Permission Model

Git operations use an `auto_permission` allowlist:
- `allowed_commands` — all commands the tool may execute
- `auto_permission` — subset auto-approved without asking (default: status, log, diff, branch, show, add)
- Operations in `allowed_commands` but NOT in `auto_permission` (e.g. commit, push) require interactive approval
- In batch mode (no handler), blocked — fail-safe

### Context Persistence

`Persisted` wraps a `BaseContextManager` and writes conversation history to JSONL. On resume (`fresh=False`), the `Persisted.agent` setter detects pre-loaded conversation history and preserves it — it does NOT call `clear()` when resuming. This is important: calling `clear()` would wipe loaded history.

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

CLI arguments are auto-generated by Clevis from the `Config` dataclass. Subcommands: `chat` (default), `run`, `init`, `config`, `inspect`, `loop`, `container`. Config-backed subcommands extend `Config`; standalone subcommands have their own fields.

Common UI-related flags:
- `--ui-mode {interactive,batch}`
- `--ui-show-thinking`
- `--ui-show-tool-calls`
- `--ui-show-stats`
- `--agents-definition PATH`
- `--session-id <name>` / `--resume <name>`

## Conventions

- **Entry point**: `python -m yoker` is the application entry point.
- **Version source of truth**: `src/yoker/__init__.py` must match `pyproject.toml`.
- **Fully qualified imports**: `from yoker.backends.protocol import ChatChunk` — not `from yoker.backends import ChatChunk`.

## Adding a New UI Handler

1. Implement the `UIHandler` protocol in `src/yoker/ui/<name>.py`.
2. Add the implementation to `src/yoker/ui/__init__.py` exports.
3. Wire the handler in `src/yoker/__main__.py` `_create_ui()` if it should be selectable via `--ui-mode`.
4. Add an example under `examples/` showing usage.
5. Update this document and `README.md`.
