# Yoker Package Split: Analysis & Design Document

> **Status**: Brainstorming / Pre-implementation
> **Date**: 2025-01-15
> **Depends on**: `yoker` (as SDK, `>=0.10.1`), `clevis` (to be extended)

## 1. Vision

Split the monolithic `yoker` package into several focused, independently
versioned packages. Each package provides a distinct capability (chat, run,
inspect, config, container, test) while sharing a common SDK foundation.

**Goals:**

- **Lean core**: `yoker` becomes a pure SDK — Agent, Session, backends,
  config, context, events, tools, plugins, built-in tools. No CLI
  subcommands, no interactive UI, no bootstrap wizard.
- **Fine-grained installation**: `uv add yoker[chat]` or `uv add yoker-chat`
  installs only what you need.
- **Independent versioning**: each package releases on its own cadence.
- **Reduced test scope**: each package has its own test suite, focused on its
  functionality.
- **Extensibility**: third-party packages can provide new `yoker` subcommands
  via an extended plugin manifest.

**Non-goals:**

- Backward compatibility — yoker is pre-1.0.0, this is a breaking change.
- A uv workspace — packages live in separate repos.
- A separate `yoker-ui` package — yoker-chat is the UI package.

### 1.1 The Split Is Timely

Yoker is pre-1.0.0 (`0.10.1`). Making the split now ensures all future
yoker-based implementations are well-founded. The cost of the split grows
with every feature added to the monolith. Doing it now avoids migration
path complexity (there is none — breaking change).

### 1.2 Phasing Strategy

**Drive the split from `yoker-test`.** yoker-test is the first new package
built with the new patterns (CommandSpec, config injection, plugin manifest
extension). It serves as the testbed and blueprint. After yoker-test is
proven, existing subcommands are extracted one by one using the same
pattern.

```
Phase 0  Clevis extension (discovered through yoker-test)
Phase 1  yoker-test (testbed for new patterns)
Phase 2  Extract yoker-chat
Phase 3  Extract yoker-run
Phase 4  Extract yoker-config
Phase 5  Extract yoker-inspect
Phase 6  Extract yoker-container
```

Each phase produces a working, independently installable package.

---

## 2. Package Overview

| # | Package | Purpose | Depends on | Key external deps |
|---|---|---|---|---|
| 1 | **yoker** | Core SDK: Agent, Session, backends, config, context, events, tools, plugins, built-in tools | — | litellm, ollama, httpx, structlog, clevis, dacite, pyyaml |
| 2 | **yoker-chat** | Interactive REPL, UI handlers, slash commands, demo/session SVG export | yoker | prompt_toolkit, rich, pyfiglet |
| 3 | **yoker-run** | Batch execution (`run` + `loop`), source resolution | yoker | — |
| 4 | **yoker-inspect** | Source inspection/reporting | yoker | — |
| 5 | **yoker-config** | First-run bootstrap wizard, `init`, `config` display | yoker | rich, pyfiglet |
| 6 | **yoker-container** | Container/Dockerfile generation | yoker | — |
| 7 | **yoker-test** | Model evaluation framework (new) | yoker | — |

### 2.1 Dependency Graph

```
                    yoker (core SDK)
                   /  |    |    |    \     \      \
          yoker-chat yoker-run yoker-inspect yoker-config yoker-container yoker-test
```

Each subcommand package:
- Depends on `yoker` (core)
- Has its own `pyproject.toml`, tests, CI, Makefile
- Declares a `__YOKER_MANIFEST__` with a `commands` entry
- Can be installed independently (`uv add yoker-chat`) or via extras
  (`uv add yoker[chat]`)

### 2.2 Extras Mechanism

The core `yoker` package declares optional-dependency extras:

```toml
[project.optional-dependencies]
chat = ["yoker-chat"]
run = ["yoker-run"]
inspect = ["yoker-inspect"]
config = ["yoker-config"]
container = ["yoker-container"]
test = ["yoker-test"]
all = ["yoker-chat", "yoker-run", "yoker-inspect", "yoker-config", "yoker-container", "yoker-test"]
```

Both `uv add yoker[chat]` and `uv add yoker-chat` converge: the former
pulls yoker-chat via the extra, the latter pulls yoker via yoker-chat's
dependency declaration.

### 2.3 Independent Versioning

Each package versions independently. yoker-test can release v0.1.0 while
yoker core is at v0.10.1. A yoker-* package declares a minimum yoker
version in its `pyproject.toml` dependencies. Breaking changes in yoker
core that affect subcommand packages are communicated via version bumps
and changelog entries.

### 2.4 No Migration Path

This is a breaking change. Pre-1.0.0 software. Users who currently
`pip install yoker` and get everything must switch to `pip install
yoker[all]` or `pip install yoker-chat` after the split. No compatibility
shims, no transition period.

---

## 3. Architecture

### 3.1 Layer Separation (after split)

```
Core SDK:         yoker          — Agent, Session, backends, config, tools, plugins
Command packages: yoker-chat     — InteractiveUIHandler, slash commands, demo
                  yoker-run      — run, loop, source resolution
                  yoker-inspect  — inspect
                  yoker-config   — init, config, bootstrap wizard
                  yoker-container— container generation
                  yoker-test     — model evaluation
```

### 3.2 The `yoker` Command Is a Router

With only the core SDK installed, the `yoker` command:
1. Discovers installed yoker-* packages (via plugin loader)
2. Collects `CommandSpec`s from their `__YOKER_MANIFEST__`
3. Builds the CLI dynamically
4. Dispatches to the matching handler

When no subcommand packages are installed, `yoker` prints available
subcommands (none) and suggests packages to install:

```
$ yoker
No yoker subcommands are installed.

Available packages:
  yoker-chat      Interactive REPL
  yoker-run       Batch execution
  yoker-inspect   Source inspection
  yoker-config    Configuration management
  yoker-container Container generation
  yoker-test      Model evaluation

Install with: pip install yoker-chat  (or: pip install yoker[chat])
```

### 3.3 Plugin Manifest Extension

The `PluginManifest` is extended with a `commands` field and a
`config_sections` field:

```python
@dataclass
class CommandSpec:
  """Declarative specification of a yoker subcommand."""
  name: str                          # subcommand name (e.g., "test")
  handler: Callable[..., Any]        # entry point function
  config_class: type | None = None   # optional Clevis configclass
  help: str = ""                     # help text
  default: bool = False              # is this the default subcommand?

@dataclass
class PluginManifest:
  # ... existing fields ...
  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list[Skill] = field(default_factory=list)
  agents: list[AgentDefinition] = field(default_factory=list)
  # NEW:
  commands: list[CommandSpec] = field(default_factory=list)
  config_sections: dict[str, type] = field(default_factory=dict)
```

- `commands`: declares subcommands the package provides
- `config_sections`: declares configuration classes to inject into the
  config hierarchy (see §5)

### 3.4 ConfigIsMissing Exception

Core yoker raises `ConfigIsMissing` when no config file is found. If
yoker-config is installed, it catches this exception and runs the bootstrap
wizard gracefully. If yoker-config is not installed (e.g., batch-only
installations), the error surfaces with guidance.

```python
# yoker core
class ConfigIsMissing(YokerError):
  """No yoker configuration file found."""
  def __init__(self) -> None:
    super().__init__(
      "enabled",
      "true",
      "No yoker configuration found. Run `yoker init` to create one, "
      "or see https://yoker.dev for documentation."
    )
```

```python
# yoker-config (catches ConfigIsMissing)
try:
  config = get_yoker_config()
except ConfigIsMissing:
  run_bootstrap_wizard()
```

### 3.5 Bootstrap Location

The bootstrap wizard (`bootstrap/`) moves to **yoker-config**. The core
SDK does not contain the wizard. When `Config()` cannot find a config
file, it raises `ConfigIsMissing`.

This keeps the core clean as an SDK. Batch-only installations (yoker +
yoker-run, no yoker-config) don't carry the wizard code or its
dependencies (rich, pyfiglet for wizard UI).

The wizard uses the `UIHandler` protocol from core. yoker-config
provides its own minimal `WizardUIHandler` using stdlib (`input()`,
`getpass()`) — no heavy dependencies, no dependency on yoker-chat.

---

## 4. UI Layer Split

### 4.1 The Coupling Problem

The current `ui/` module has cross-dependencies that prevent a naive
split:

| Module | Used by | Heavy deps? |
|---|---|---|
| `handler.py` (UIHandler protocol) | UIBridge, Interactive, Batch, all slash commands, bootstrap wizard, cli/run, cli/chat, cli/loop, cli/init | No |
| `bridge.py` (UIBridge) | cli/run, cli/chat, cli/loop | No |
| `batch.py` (BatchUIHandler) | cli/run, cli/chat (`--ui-mode batch`), cli/loop | No (just `sys`) |
| `formatting.py` | batch.py, interactive.py | No (just `json`) |
| `interactive.py` (InteractiveUIHandler) | cli/chat, cli/init (wizard) | **Yes** (prompt_toolkit, rich, pyfiglet) |
| `markdown.py` (MarkdownStreamer) | interactive.py | **Yes** (rich) |
| `commands/` (slash commands) | cli/chat only | No (but only useful in interactive REPL) |

### 4.2 `yoker chat --ui-mode batch` vs `yoker run`

These are different things:

| | `yoker chat --ui-mode batch` | `yoker run` |
|---|---|---|
| Execution model | Multi-turn REPL loop | Single-shot (one prompt → exit) |
| Input | stdin (line by line or piped) | Source manifest (`agent.toml`) + CLI `--agent`/`--prompt` |
| Source resolution | None | Resolves external sources (module, GitHub, folder, zip) with trust gate |
| Slash commands | Yes | No |
| Session persistence | `--session-id` / `--resume` | `--persist` / `--session-id` |
| UI | BatchUIHandler | Always BatchUIHandler |

Both need `BatchUIHandler`. Since it has no heavy dependencies (just
`sys`), it stays in core.

### 4.3 Resolved Split

**yoker core** (lightweight UI, no heavy deps):
```
src/yoker/ui/
├── handler.py        # UIHandler protocol
├── bridge.py         # UIBridge
├── batch.py          # BatchUIHandler
└── formatting.py     # format_tool_args, truncate_content_preview
```

**yoker-chat** (heavy UI):
```
src/yoker_chat/
├── interactive.py    # InteractiveUIHandler (deps: prompt_toolkit, rich, pyfiglet)
├── markdown.py       # MarkdownStreamer (deps: rich)
└── commands/         # Slash commands
```

**yoker-config** (wizard UI):
```
src/yoker_config/
├── wizard_ui.py      # Minimal WizardUIHandler using stdlib (input(), getpass())
└── bootstrap/        # Wizard logic
```

### 4.4 Per-Package UI Configuration

Instead of a shared `UIConfig` in core `Config`, each package has its own
UI-related config. This allows configuring display differently per
execution scope:

- `ChatUIConfig` in yoker-chat: `mode`, `show_thinking`, `show_tool_calls`,
  `show_stats` — for interactive/batch REPL display
- `RunUIConfig` in yoker-run: `show_thinking`, `show_tool_calls`,
  `show_stats` — for batch output display

`BatchUIHandler` in core is agnostic — it takes display settings as
constructor args. Each package passes its own UI config values.

The current `UIConfig` in core `Config` is removed (or reduced to
nothing). Each package owns its UI configuration.

### 4.5 Core Exports

Whatever is needed by subcommand packages is exported from yoker core:

```python
# yoker/__init__.py (additions)
from yoker.ui.handler import UIHandler
from yoker.ui.bridge import UIBridge
from yoker.ui.batch import BatchUIHandler
from yoker.ui.formatting import format_tool_args, truncate_content_preview
from yoker.plugins.manifest import CommandSpec
```

---

## 5. Configuration Injection

### 5.1 The Problem

The core `yoker` package holds the root `Config` class hierarchy and uses
Clevis to consolidate (TOML + CLI). Optional packages need to provide
additional configuration classes, specific to their functionality, and
these should be injected into the main yoker configuration hierarchy.

### 5.2 The Approach

A plugin provides its config classes along with an injection path — a
location in the existing config hierarchy where the class should be
attached.

```python
# yoker_test/__init__.py
__YOKER_MANIFEST__ = PluginManifest(
  commands=[CommandSpec(name="test", handler=run_test, config_class=TestConfig)],
  config_sections={
    "test": TestConfig,  # injected at config.test
  },
)
```

The injection path is the key name in the `config_sections` dict. The
core config loader discovers `config_sections` from installed packages'
manifests and attaches the config classes to the `Config` hierarchy at
the specified paths.

### 5.3 Subcommand Config (Subclassing)

For subcommand-specific config (CLI args, TOML sections), each package's
config class extends `yoker.Config`:

```python
# yoker_chat/config.py
from yoker.config import Config

class ChatConfig(Config):
  session_id: str | None = None
  resume: str | None = None
  ui: ChatUIConfig = field(default_factory=ChatUIConfig)
```

Clevis treats this as a subcommand config — extracts the `[chat]` section
from TOML, generates CLI args from the dataclass fields. This is the
existing pattern, preserved.

### 5.4 What Stays in Core Config

The core `Config` retains:

- `enabled`, `agent`, `harness`, `motd`
- `backend` (provider configs)
- `context` (context management)
- `permissions` (permission boundaries)
- `tools` (tool configurations — tools are in core)
- `tools_shared` (shared tool settings)
- `agents` (agent definition settings)
- `skills` (skills configuration)
- `plugins` (plugin configuration)
- `logging` (logging configuration)
- `session` (session management — Session is a core concept)

**Removed from core Config:**
- `ui` — moves to per-package UI configs

**Moved to yoker-config:**
- `config/writer.py` — TOML config writer (only used by `yoker init`)

### 5.5 Clevis Extension Needed

The config injection mechanism (attaching plugin config classes at
arbitrary paths in the config hierarchy) likely requires Clevis support
for dynamic config section injection. This need will be discovered and
refined through yoker-test implementation.

---

## 6. Clevis Extension

### 6.1 The Principle

Everything possible at import time via `@configclass` should also be
possible dynamically at runtime. The decorators should be syntactic sugar
over an imperative API.

### 6.2 What We Need

1. **Dynamic command registration**: register a config class as a
   subcommand at runtime (not just via `@configclass` decorator at import
   time). The router discovers installed packages and registers their
   commands after import.

2. **Build CLI from a list of specs**: construct an argparse parser from
   a list of dynamically discovered subcommands (name, config_class,
   help text, default flag).

3. **`get_cmd()` with dynamic subcommands**: the dispatch function works
   with subcommands registered at runtime, not just at import time.

4. **Subcommands without a base Config class**: lightweight commands
   like `inspect` that don't extend `Config` should still be
   registerable.

5. **Default subcommand designation**: one subcommand can be marked as
   default (runs when no subcommand is given). Currently `chat` is the
   default.

6. **Dynamic config section injection**: attaching plugin-provided config
   classes at specified paths in the config hierarchy (see §5).

### 6.3 Feature Request Strategy

We create feature requests to the Clevis project as we discover specific
needs through yoker-test implementation. Each request clearly states:
- What we need
- Why we need it (concrete use case from yoker)
- Optional ideas/concepts that would work

This avoids ivory tower design. We build first, request second.

### 6.4 Router Without Clevis?

The core `yoker` `__main__.py` router might not need Clevis at all for
top-level dispatch. If the router just discovers `CommandSpec`s and
dispatches to handlers via its own argparse-based mechanism, Clevis is
only used *inside* each subcommand (for config loading via
`get_config()`). This might avoid needing Clevis changes for the router
itself, while still needing Clevis changes for config injection. To be
discovered during implementation.

---

## 7. Package Contents (Detailed)

### 7.1 yoker (Core SDK)

```
yoker/
├── pyproject.toml          # deps: litellm, ollama, httpx, structlog, clevis, dacite, pyyaml
├── src/yoker/
│   ├── __init__.py         # Public API: Agent, Session, Config, process, do, agent, session, run_sync
│   │                       #   + UIHandler, UIBridge, BatchUIHandler, CommandSpec
│   ├── __main__.py         # Router: discovers CommandSpecs, dispatches
│   ├── api.py              # process(), do(), agent(), session(), run_sync()
│   ├── exceptions.py       # + ConfigIsMissing (NEW)
│   ├── logging.py
│   ├── resources.py
│   ├── schema.py
│   ├── cli_utils.py        # Shared CLI helpers: abort(), check_enabled(), get_security_config(),
│   │                       #   load_subcommand_config()
│   ├── py.typed
│   ├── core/               # Agent, processing, setup, thinking
│   ├── session/            # Session, tools (agent, send_message)
│   ├── backends/           # ModelBackend protocol, Ollama, LiteLLM, trust
│   ├── config/             # Config hierarchy, providers, validators (writer.py → yoker-config)
│   ├── context/            # Context managers, persistence
│   ├── events/             # Event types, session events, recorder
│   ├── agents/             # Agent definition schema, loader, registry, validator
│   ├── skills/             # Skill schema, loader, registry, injection
│   ├── tools/              # Tool framework, annotations, guardrails, web backends
│   ├── plugins/            # Plugin loader, manifest (+CommandSpec), security
│   ├── builtin/            # Built-in tools (read, write, update, git, github, make, etc.)
│   └── ui/                 # Lightweight UI only:
│       ├── handler.py       #   UIHandler protocol
│       ├── bridge.py        #   UIBridge
│       ├── batch.py         #   BatchUIHandler
│       └── formatting.py    #   format_tool_args, truncate_content_preview
├── docs/                   # One documentation site covering all yoker-owned sub-packages
└── tests/
```

**Removed from core (vs current monolith):**
- `bootstrap/` → yoker-config
- `cli/chat.py` → yoker-chat
- `cli/run.py`, `cli/loop.py`, `cli/sources.py` → yoker-run
- `cli/inspect.py` → yoker-inspect
- `cli/init.py`, `cli/config_cmd.py` → yoker-config
- `cli/container.py` → yoker-container
- `cli/commands.py` → split: each config class moves to its package
- `cli/shared.py` → split: generic helpers to `cli_utils.py` (core),
  run-specific to yoker-run
- `ui/interactive.py` → yoker-chat
- `ui/commands/` → yoker-chat
- `markdown.py` → yoker-chat
- `config/writer.py` → yoker-config

### 7.2 yoker-chat

```
yoker-chat/
├── pyproject.toml          # deps: yoker, prompt_toolkit, rich, pyfiglet
├── src/yoker_chat/
│   ├── __init__.py         # __YOKER_MANIFEST__ with CommandSpec(name="chat", default=True)
│   ├── chat.py             # run_chat() handler
│   ├── config.py           # ChatConfig (extends yoker.Config), ChatUIConfig
│   ├── interactive.py      # InteractiveUIHandler
│   ├── markdown.py         # MarkdownStreamer
│   ├── commands/           # Slash commands (/help, /agents, /skills, /tools, /think, /context, /config)
│   ├── demo.py             # Demo session runner + SVG export
│   └── demo_script.py      # DemoScript loader
├── demos/                  # Demo script files (.md) + yoker.toml
└── tests/
```

### 7.3 yoker-run

```
yoker-run/
├── pyproject.toml          # deps: yoker
├── src/yoker_run/
│   ├── __init__.py         # __YOKER_MANIFEST__ with CommandSpecs: "run", "loop"
│   ├── run.py              # run_run() handler
│   ├── loop.py             # run_loop() handler
│   ├── config.py           # RunConfig, LoopConfig (extend yoker.Config), RunUIConfig
│   ├── sources.py          # resolve_source(), load_source()
│   └── run_utils.py        # safe_cleanup(), parse_run_overrides(),
│                           #   resolve_agent_and_prompt(), register_source_agents()
└── tests/
```

### 7.4 yoker-inspect

```
yoker-inspect/
├── pyproject.toml          # deps: yoker
├── src/yoker_inspect/
│   ├── __init__.py         # __YOKER_MANIFEST__ with CommandSpec: "inspect"
│   ├── inspect.py          # run_inspect() handler
│   └── config.py           # InspectConfig
└── tests/
```

### 7.5 yoker-config

```
yoker-config/
├── pyproject.toml          # deps: yoker, rich, pyfiglet
├── src/yoker_config/
│   ├── __init__.py         # __YOKER_MANIFEST__ with CommandSpecs: "init", "config"
│   ├── init.py             # run_init() handler
│   ├── config_cmd.py       # run_config_cmd() handler
│   ├── writer.py           # TOML config writer (from yoker/config/writer.py)
│   ├── wizard_ui.py        # Minimal WizardUIHandler (stdlib: input(), getpass())
│   ├── bootstrap/          # Wizard
│   │   ├── wizard.py
│   │   ├── steps.py
│   │   ├── providers.py
│   │   ├── detect.py
│   │   └── modellist.py
│   └── config.py           # InitConfig, ConfigCmdConfig
└── tests/
```

**Special behavior:** When yoker core raises `ConfigIsMissing`,
yoker-config catches it and runs the bootstrap wizard.

### 7.6 yoker-container

```
yoker-container/
├── pyproject.toml          # deps: yoker
├── src/yoker_container/
│   ├── __init__.py         # __YOKER_MANIFEST__ with CommandSpec: "container"
│   ├── container.py        # run_container() handler
│   └── config.py           # ContainerConfig
└── tests/
```

### 7.7 yoker-test

```
yoker-test/
├── pyproject.toml          # deps: yoker
├── src/yoker_test/
│   ├── __init__.py         # Public API + __YOKER_MANIFEST__ with CommandSpec: "test"
│   ├── cli.py              # yoker-test CLI + yoker test handler
│   ├── schema.py           # TestTask, TestResult, TestReport, SuiteConfig
│   ├── runner.py           # EvalRunner
│   ├── scorers.py          # Built-in scorers
│   ├── loader.py           # Suite YAML loader, !function resolution
│   ├── report.py           # Aggregation, formatting, baseline comparison
│   ├── pricing.py           # Cost computation
│   └── config.py           # TestConfig (extends yoker.Config)
├── suites/
│   └── yoker_basic/
├── baselines/
└── tests/
```

---

## 8. Shared Utilities Split

### 8.1 Current `cli/shared.py` Functions

| Function | Used by | Goes to |
|---|---|---|
| `abort(msg, code)` | All subcommands | **yoker core** (`cli_utils.py`) |
| `check_enabled(config)` | chat, run, loop | **yoker core** (`cli_utils.py`) |
| `get_security_config()` | All config-loading subcommands | **yoker core** (`cli_utils.py`) |
| `load_subcommand_config(config_class)` | All config-backed subcommands | **yoker core** (`cli_utils.py`) |
| `load_subcommand_config_with_manifest(...)` | run, loop | **yoker-run** |
| `safe_cleanup(obj)` | run, loop | **yoker-run** (`run_utils.py`) |
| `parse_run_overrides(argv)` | run | **yoker-run** (`run_utils.py`) |
| `resolve_agent_and_prompt(...)` | run | **yoker-run** (`run_utils.py`) |
| `register_source_agents(...)` | run | **yoker-run** (`run_utils.py`) |
| `MAX_PROMPT_BYTES` | run | **yoker-run** (`run_utils.py`) |

### 8.2 SessionConfig

`SessionConfig` (max_agents, default_isolation_policy, event_aggregation)
stays in **yoker core** `Config`. Session is a core concept — it manages
the team of agents regardless of which subcommand is used.

`ChatConfig`'s `session_id`/`resume` fields go to **yoker-chat** as
chat-specific session management config.

---

## 9. Demo Functionality

### 9.1 Current State

The demo functionality is currently spread across:

- `scripts/demo_session.py` — demo session runner, generates SVG from
  scripted conversations using Rich's `Console(record=True)` + `save_svg()`
- `scripts/yoker_demo.py` — `DemoScript` dataclass, loads demo scripts
  from Markdown files with YAML frontmatter
- `scripts/analyze_session.py` — session JSONL analysis tool
- `demos/` — directory of demo script `.md` files + `yoker.toml`
- `tests/test_demo.py` — tests for `yoker_demo` module
- `tests/test_demo_session.py` — tests for demo session runner
  (also tests event serialization/deserialization)

### 9.2 Target State

All demo functionality moves to **yoker-chat**. The demo becomes an
option to dump a session as SVG, cleanly integrated into the chat
functionality — not a separate script.

```
yoker-chat/
├── src/yoker_chat/
│   ├── demo.py             # Demo session runner + SVG export
│   ├── demo_script.py      # DemoScript loader
│   └── analyze.py          # Session analysis (optional, utility)
├── demos/
│   ├── *.md
│   └── yoker.toml
└── tests/
    ├── test_demo.py
    └── test_demo_session.py
```

The event serialization tests in `test_demo_session.py` that test
`yoker.events` functionality (not demo-specific) stay in **yoker core**.

---

## 10. Test Distribution

### 10.1 Distribution Map

| Package | Tests from current suite |
|---|---|
| **yoker** | `test_api/`, `test_backends/`, `test_core/`, `test_config/`, `test_context*.py`, `test_events/`, `test_session/`, `test_skills/`, `test_tools/`, `test_plugins/`, `test_agent/`, `test_agent_loading.py`, `test_content_type*.py`, `test_exceptions_new.py`, `test_logging.py`, `test_network_error.py`, `test_tool_enabled_flag.py`, `test_plugin_*.py`, `test_issue_fixes.py`, `test_main.py` (router tests only), event serialization tests from `test_demo_session.py` |
| **yoker-chat** | `test_cli/` (chat-related), `test_ui/`, `test_ui_commands/`, `test_demo.py`, `test_demo_session.py` (demo-specific tests), `test_demo_plugin.py` |
| **yoker-run** | `test_cli/` (run/loop-related), `test_main*.py` (run/loop-related) |
| **yoker-inspect** | `test_cli/` (inspect-related) |
| **yoker-config** | `test_bootstrap/`, `test_cli/` (init/config-related) |
| **yoker-container** | `test_cli/` (container-related) |
| **yoker-test** | New test suite for the framework |

### 10.2 Shared Test Fixtures

Each package has its own test setup (`conftest.py`, `pytest.ini` or
`pyproject.toml [tool.pytest.ini_options]`). Shared fixtures may be
duplicated across packages — this is acceptable. Duplicated fixtures are
simpler than a shared test-utils package and keep packages independent.

### 10.3 `test_main.py` Restructuring

`test_main.py` currently tests the full `__main__.py` dispatch. After
the split:
- Router logic tests (discovery, dispatch) stay in **yoker core**
- Subcommand-specific dispatch tests move to the respective package

---

## 11. Documentation

### 11.1 Current State

One Sphinx documentation site in the yoker repo (`docs/`).

### 11.2 Target State

Documentation stays in the **yoker core** repo for now. One documentation
site covering all yoker-owned sub-packages. Contributors to yoker-chat
submit doc PRs to the yoker repo.

Future plan: move documentation completely to the https://yoker.dev site
(separate `yoker.dev` repo).

### 11.3 `docs/yoker-test-analysis.md`

Already lives as a separate analysis document. Moves to the yoker-test
repo when that repo is created.

---

## 12. Examples

### 12.1 Current State

```
examples/
├── agents/                 # Agent definition examples
├── skills/                 # Skill definition examples
├── plugins/demo/           # Demo plugin (uv workspace member)
├── python_api/             # SDK usage examples
├── batch_mode.py           # Batch mode example
├── custom_handler.py       # Custom UI handler example
├── session_demo.py         # Session demo
├── research_workflow.py    # Research workflow example
├── yoker.toml              # Example config
└── README.md
```

### 12.2 Target State

Examples are split across packages:

| Example | Goes to |
|---|---|
| `agents/` | **yoker** (SDK examples) |
| `skills/` | **yoker** (SDK examples) |
| `python_api/` | **yoker** (SDK examples) |
| `session_demo.py` | **yoker** (SDK examples) |
| `research_workflow.py` | **yoker** (SDK examples) |
| `batch_mode.py` | **yoker-run** (batch execution example) |
| `custom_handler.py` | **yoker-chat** (UI handler example) |
| `plugins/demo/` | **TBD** — may be dropped or split (deferred) |

---

## 13. CI Strategy

Each package lives independently with its own CI pipeline:

- **yoker core**: CI runs on every push/PR. Tests, lint, typecheck, build,
  publish.
- **yoker-* packages**: CI runs on every push/PR. Tests, lint, typecheck,
  build, publish. Depends on a pinned version of yoker (from PyPI or a
  specific commit).

A change in yoker core that passes CI can be published. Downstream
packages pick up the new version when they're ready. Breaking changes in
core that affect downstream packages are communicated via version bumps
and changelog entries.

There is no monorepo meta-CI that runs all packages together. Each
package is responsible for its own quality gates.

---

## 14. Phasing

### Phase 0 — Clevis Extension (discovered through Phase 1)

Not a separate phase — Clevis extensions are discovered and requested
as needed during Phase 1 (yoker-test) implementation.

### Phase 1 — yoker-test (testbed)

1. Create `yoker-test` repo/package depending on `yoker`
2. Implement yoker-test core: runner, scorers, loader, report, pricing
3. Implement yoker-test CLI as standalone `yoker-test` command
4. Extend `yoker` core with `CommandSpec` in `PluginManifest`
5. Extend `yoker` core `__main__.py` with dynamic command discovery
6. Add `ConfigIsMissing` exception to yoker core
7. Wire yoker-test as `yoker test` subcommand
8. Discover Clevis needs → create feature request(s)
9. Refine config injection based on real implementation needs
10. Verify: `yoker-test` standalone works, `yoker test` works, config
    injection works

**Outcome**: yoker-test is a complete, working package. The CommandSpec /
plugin manifest pattern is proven. Clevis extension needs are documented
and requested.

### Phase 2 — Extract yoker-chat

1. Move `ui/interactive.py`, `ui/commands/`, `markdown.py` to yoker-chat
2. Move `cli/chat.py` → `yoker_chat/chat.py`
3. Move demo functionality to yoker-chat
4. Create `ChatConfig(yoker.Config)`, `ChatUIConfig`
5. Core keeps `ui/handler.py`, `ui/bridge.py`, `ui/batch.py`,
   `ui/formatting.py`
6. Remove `UIConfig` from core `Config`
7. Verify: `yoker chat` works, `yoker chat --ui-mode batch` works
   (BatchUIHandler from core), slash commands work

### Phase 3 — Extract yoker-run

1. Move `cli/run.py`, `cli/loop.py`, `cli/sources.py` to yoker-run
2. Move run-specific shared utils to `yoker_run/run_utils.py`
3. Create `RunConfig(yoker.Config)`, `LoopConfig(RunConfig)`, `RunUIConfig`
4. Verify: `yoker run`, `yoker loop` work

### Phase 4 — Extract yoker-config

1. Move `bootstrap/` to yoker-config
2. Move `cli/init.py`, `cli/config_cmd.py` to yoker-config
3. Move `config/writer.py` to yoker-config
4. Create `WizardUIHandler` (stdlib only)
5. Wire `ConfigIsMissing` catch → bootstrap wizard
6. Verify: `yoker init`, `yoker config` work, wizard catches
   `ConfigIsMissing`

### Phase 5 — Extract yoker-inspect

1. Move `cli/inspect.py` to yoker-inspect
2. Create `InspectConfig`
3. Verify: `yoker inspect` works

### Phase 6 — Extract yoker-container

1. Move `cli/container.py` to yoker-container
2. Create `ContainerConfig`
3. Verify: `yoker container` works

---

## 15. Open Questions

### OQ-1: Clevis API for dynamic command registration

**Question**: What exactly should the Clevis API look like for runtime
command registration?

**Context**: Currently Clevis uses `@configclass(cmd="chat")` at import
time and `get_cmd()` to return the parsed subcommand. For dynamic
discovery, we need imperative registration.

**Options**:
- (a) `clevis.register_config_class(cls, cmd="chat", help="...", default=False)` — imperative registration
- (b) Keep `@configclass` but make it work with a registry that can be populated at import time *or* runtime
- (c) A new `clevis.build_cli(commands: list[CommandSpec])` that builds the argparse parser from a list of specs

**Strategy**: Discover through yoker-test implementation. Create specific
feature request once needs are concrete.

### OQ-2: Config injection mechanism — exact API

**Question**: How does config injection work concretely?

**Context**: The user said: "a plugin should provide a config class and a
path into the existing config, e.g., TestModelConfig which should be
available at 'plugins.test' in the config hierarchy."

**Current understanding**:
```python
PluginManifest(
  config_sections={
    "test": TestConfig,  # injected at config.test
  },
)
```

**Open**: Does Clevis support this? Does it need a Clevis extension? How
does TOML section extraction work for injected configs? How do CLI args
get generated for injected configs?

**Strategy**: Discover through yoker-test implementation.

### OQ-3: Does the `yoker` core `__main__.py` router need Clevis at all?

**Question**: Can the top-level router be a simple argparse-based
dispatcher that doesn't use Clevis's `get_cmd()`?

**Context**: If the router just discovers `CommandSpec`s and dispatches
to handlers, it could be yoker's own code. Clevis would still be used
*inside* each subcommand (for config loading via `get_config()`).

**Implication**: This might avoid needing Clevis changes for the router
itself, while still needing Clevis changes for config injection.

**Strategy**: Discover through yoker-test implementation. Start with a
simple router, see if Clevis is needed.

### OQ-4: yoker-test UI dependency

**Question**: Does yoker-test need UI at all?

**Context**: yoker-test runs evaluations — sends prompts, collects
responses, scores them, outputs a report. This could use `BatchUIHandler`
for progress output, or its own output mechanism (print/report).

**Options**:
- (a) Uses `BatchUIHandler` from core — consistent with other packages
- (b) Own output mechanism — no UI dependency, simpler

**Strategy**: Discover during implementation. Start with (b), switch to
(a) if consistency is needed.

### OQ-5: Demo plugin (`examples/plugins/demo`)

**Question**: Drop or split the demo plugin?

**Context**: Currently a uv workspace member. After the split (no
workspace), it becomes a standalone package or is dropped.

**Status**: Deferred. Decided later.

### OQ-6: Documentation site structure

**Question**: How does the single docs site work when packages are in
separate repos?

**Context**: Docs stay in yoker core repo for now. Future plan: move to
yoker.dev site (separate repo).

**Current decision**: Docs in yoker core repo. Contributors to yoker-*
packages submit doc PRs to the yoker repo. This is a workflow question,
not a technical blocker.

### OQ-7: `yoker run` uses BatchUIHandler with display settings — where do they come from?

**Question**: After `UIConfig` is removed from core, where does
`BatchUIHandler` get `show_thinking`, `show_tool_calls`, `show_stats`?

**Answer**: Each package passes its own UI config values to
`BatchUIHandler` as constructor args. `BatchUIHandler` is agnostic — it
just takes args. yoker-run's `RunConfig` has `RunUIConfig` with these
fields and passes them. yoker-chat's `ChatConfig` has `ChatUIConfig` and
passes them to whichever handler it creates.

**Status**: Resolved. No open question.

### OQ-8: yoker-config wizard interactive input

**Question**: How does yoker-config's wizard get interactive input without
depending on yoker-chat?

**Answer**: yoker-config provides its own `WizardUIHandler` using stdlib
(`input()`, `getpass()`). The wizard only needs `output_info`,
`output_step_title`, `get_input`, `get_secret_input` — all on the
`UIHandler` protocol. A minimal stdlib-based handler keeps yoker-config
independent of yoker-chat.

**Status**: Resolved. No open question.

---

## 16. Summary of Confirmed Decisions

| # | Decision |
|---|---|
| D1 | Bootstrap → yoker-config. Core raises `ConfigIsMissing` when no config found. |
| D2 | `PluginManifest` extended with `commands: list[CommandSpec]` and `config_sections: dict[str, type]`. |
| D3 | Clevis extended to support dynamic registration. Feature requests created as needs are discovered through yoker-test. |
| D4 | Separate repos, no uv workspace. |
| D5 | Config injection: plugin provides config class + injection path into config hierarchy. |
| D6 | Built-in tools stay in yoker core. |
| D7 | Demo/Session SVG → yoker-chat, integrated as a chat option. |
| D8 | No separate yoker-ui. yoker-chat is the UI package. |
| D9 | `yoker` command is a router. Shows help when no subcommands installed. |
| D10 | Extras: `yoker[chat]`, `yoker[run]`, ..., `yoker[all]`. |
| D11 | `markdown.py` → yoker-chat (only meaningful in UI context). |
| D12 | Examples split across packages. |
| D13 | Shared utils split by usage (generic → core, run-specific → yoker-run). |
| D14 | Each package has own Makefile. |
| D15 | Demo `yoker.toml` → yoker-chat. |
| D16 | One documentation site in yoker core repo. Future: yoker.dev site. |
| D17 | Independent versioning per package. |
| D18 | Breaking change, no migration path (pre-1.0.0). |
| D19 | Demo plugin: dropped or split — deferred. |
| D20 | Config writer (`config/writer.py`) → yoker-config. |
| D21 | Each package has own test setup (possibly with duplicated fixtures). |
| D22 | CI: packages depend on a version of yoker, live independently. |
| D23 | Phasing: drive from yoker-test first. yoker-test is the testbed and blueprint. |
| D24 | `UIHandler` protocol, `UIBridge`, `BatchUIHandler`, `formatting.py` stay in yoker core (no heavy deps). |
| D25 | `InteractiveUIHandler`, `markdown.py`, slash commands → yoker-chat. |
| D26 | Per-package UI config (`ChatUIConfig`, `RunUIConfig`). `UIConfig` removed from core `Config`. |
| D27 | `SessionConfig` stays in core `Config`. `ChatConfig`'s session_id/resume → yoker-chat. |
| D28 | Core exports what packages need (`UIHandler`, `UIBridge`, `BatchUIHandler`, `CommandSpec`, etc.). |
| D29 | Subcommand name is `test` — `yoker test`, not `yoker eval`. |
| D30 | yoker-config provides `WizardUIHandler` (stdlib) — no dependency on yoker-chat. |