# API Architecture Review: MBI-004 yoker Commands

**Date**: 2026-07-08 (revised 2026-07-08 per owner feedback on PR #46)
**Reviewer**: API Architect Agent
**Task**: Review design for tasks 4.1 (CLI Subcommand Dispatcher) and 4.5 (Extended Manifest), with a brief outline for 4.6 (Source Resolution).
**Design source of truth**: `analysis/mbi-004-yoker-commands.md`
**Task breakdown**: `TODO.md` (section "## Active: MBI-004: yoker Commands")

## Summary

The MBI-004 design is internally coherent and well-scoped. The functional analysis already resolves most of the hard product questions (seven subcommands including `inspect`, backward-compat default to `chat`, source type detection, manifest as config-override layer). This review focuses on the architectural decisions that the functional analysis leaves open or underspecifies, and makes concrete recommendations for:

1. **4.1 CLI dispatcher** — use Clevis's built-in command/subcommand support (`@configclass(cmd=...)`, `get_cmd()`) instead of a manual dispatcher. Clevis generates subparsers from decorated dataclass config classes. Each subcommand gets its own auto-generated CLI args. Subcommands that don't need a `Config` (`init`, `container`, `inspect`) use minimal config classes or bypass config loading. Backward compatibility is maintained by defaulting to `chat` when no subcommand is given.
2. **4.5 Extended manifest** — the manifest is a **generic config-override layer**, not additive fields on `PluginManifest`. Layering: base TOML config (`~/.yoker.toml`, `./yoker.toml`) → manifest overrides (`agent.toml` in the source root) → CLI overrides. The manifest can override any `Config` field, not just `agent`/`prompt`. Source-specific fields (`[run]`, `[plugin]`) are extracted separately. The file-based manifest uses the filename `agent.toml` to avoid collision with the project-level `yoker.toml`. A `ResolvedSource` carrier dataclass carries the run-config and plugin-config alongside `PluginComponents` into the run path.
3. **4.6 Source resolution** — a `resolve_source()` function returning a `ResolvedSource` with a `cleanup` hook, with security considerations for zip path traversal and GitHub clone hygiene. Trust gates reuse the existing `check_plugin_allowed()` — no parallel tracks, no bypass for named sources.

One key architectural concern: the loader currently keys everything off `importlib.import_module(package_name)`, which cannot resolve a folder or zip. The source-resolution layer must produce something the existing `load_plugin` machinery can consume, or `load_plugin` must be generalized. The recommendation below is to **generalize the loader** with a `Source` abstraction rather than threading folder/zip special cases through `load_plugin`.

---

## 1. Current Architecture Summary

### 1.1 CLI entry point (`src/yoker/__main__.py`)

`main()` is a single linear function:

1. `_parse_plugin_args()` strips `--with <pkg>` from `sys.argv` *before* Clevis runs (Clevis doesn't know about `--with`).
2. Pre-flight bootstrap check: if no config is found and stdin is a TTY, run `BootstrapWizard`; otherwise abort.
3. `get_yoker_config(cli=True)` — Clevis loads TOML + env + CLI args into a `Config`.
4. `configure_logging(...)`.
5. `_create_ui(config)` selects `InteractiveUIHandler` or `BatchUIHandler`.
6. `asyncio.run(_run_with_session(...))` constructs a `Session`, wires `UIBridge`, runs `_run_repl`.

Key constraint: **Clevis owns CLI parsing for `Config`-derived args.** Every flag the user passes (`--backend-ollama-model`, `--ui-mode`, `--tools-read-enabled`, ...) is auto-generated from the `Config` dataclass fields by Clevis. `--with` is the only flag handled manually, and it is stripped from `sys.argv` before Clevis sees it.

### 1.2 Config and Clevis (`src/yoker/config/__init__.py`)

`Config` is a deeply nested dataclass tree. `get_yoker_config(cli=True)` delegates to `clevis.get_config(Config, name="yoker", cli=True, ...)`. Clevis:
- discovers `~/.yoker.toml` and `./yoker.toml`,
- interpolates `${ENV}` vars,
- parses CLI args generated from the dataclass field names (dotted → dashed, e.g. `backend.ollama.model` → `--backend-ollama-model`),
- merges layers (CLI > project > user).

This is a **load-bearing architectural pattern.** Any dispatcher design must keep Clevis as the `Config`-arg parser; replacing it with argparse subparsers for `Config` fields would be a rewrite of the entire config CLI surface and is out of scope for MBI-004.

### 1.3 Plugin manifest and loader

`PluginManifest` (`src/yoker/plugins/manifest.py`) is a dataclass with `tools`, `skills`, `agents`, `config_class`, `skills_dir`, `agents_dir`. It is instantiated in a plugin package's `__init__.py` as `__YOKER_MANIFEST__`.

`load_plugin(package_name)` in `src/yoker/plugins/loader.py`:
1. `importlib.import_module(package_name)`,
2. reads `package.__YOKER_MANIFEST__`,
3. loads skills from `manifest.skills_dir` via `find_package_subdirectory`,
4. loads agents from `manifest.agents_dir` similarly,
5. returns `PluginComponents(tools, skills, agents, source=package_name)`.

`load_plugins(config, extra_plugins)` is the single entry point: it always loads `yoker` (trusted builtin), then adds `config.plugins.packages` and `extra_plugins` when `config.plugins.enabled` is True, and applies the per-plugin trust gate (`check_plugin_allowed`).

The loader is **package-name-oriented.** It cannot currently load from a folder path or a zip — there is no `importlib.import_module` target for those. This is the core reason 4.6 (source resolution) needs a new abstraction rather than a small extension.

### 1.4 Python API facade (`src/yoker/api.py`)

`yoker.agent()`, `yoker.process()`, `yoker.do()`, `yoker.session()` are the programmatic surface. `yoker.run_sync(coro)` is the single sync bridge. The CLI `run` subcommand is essentially `yoker.process(prompt, plugins=(source,))` with the agent/prompt sourced from the manifest — there is strong reuse potential here, and the `run` subcommand should delegate to the same `_build_config_and_definition` + `Session` path rather than reimplementing it.

---

## 2. Recommended Design for 4.1 — CLI Subcommands via Clevis Commands

### 2.1 Clevis command support (v0.3.3)

Clevis has built-in subcommand support. The key mechanisms are:

- **`@configclass(cmd="name", help="...", aliases=[...])`** — decorator that registers a dataclass as a subcommand. Clevis creates a subparser (via `argparse.add_subparsers(dest="cmd")`) and auto-generates CLI args from the dataclass fields, scoped to that subparser.
- **`get_cmd(parser, args) -> str | None`** — returns the active subcommand name from parsed arguments.
- **`Factory.cmd` / `Factory.config`** — the `cmd` field sets the subcommand name; the `config` field sets a TOML extraction key (defaults to `cmd` if not set). When a `[cmd]` section exists in TOML, Clevis extracts it; otherwise root-level TOML is used as-is (backward compatible).
- **`get_sub_parser(parser)`** — creates or retrieves the subparser manager. Sets `required = True` by default; we set it to `False` for backward compatibility (no subcommand = default to `chat`).

**TOML extraction behavior:** when `@configclass(cmd="chat")` is applied to a config class, `get_config()` looks for a `[chat]` section in the TOML. If found, it extracts it and clears root-level fields. If NOT found, root-level TOML fields are used as-is. This means existing `~/.yoker.toml` files with root-level fields continue to work — they are treated as the default (chat) config. Users can optionally organize config into `[chat]`, `[run]`, etc. sections.

### 2.2 Alternatives considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **A. Manual dispatcher in front of Clevis** | A custom dispatcher peels off the subcommand and routes to per-subcommand Clevis calls. | Rejected — the owner explicitly pushed back: "Clevis has support for commands." Building a parallel manual dispatcher when Clevis already has subcommand support is unnecessary complexity. |
| **B. Clevis commands (`@configclass(cmd=...)`)** | Use Clevis's built-in subcommand mechanism. Each subcommand is a `@configclass(cmd="X")` dataclass with its own auto-generated CLI args. | **Recommended** — uses the framework's native capability, no parallel dispatcher, auto-generated help per subcommand, TOML extraction per subcommand. |
| **C. click / typer** | Adopt a third-party CLI framework. | Rejected — introduces a new dependency; Clevis already provides what we need. |
| **D. argparse subparsers for everything** | Replace Clevis with manual argparse. | Rejected — loses annotation-driven CLI generation. |

### 2.3 Recommended design: Clevis subcommand config classes

**Structure:**

```
src/yoker/
  __main__.py            # thin: strips --with, defaults subcommand, calls get_cmd()
  cli/
    __init__.py           # exports dispatch()
    commands.py           # subcommand config classes (@configclass(cmd=...))
    shared.py             # shared setup: load_config(), configure_logging, bootstrap gate
    chat.py               # async def run(config, plugin_packages) -> None
    run.py                # async def run(config, run_config, plugin_packages) -> None
    loop.py
    inspect.py            # def run(inspect_config, plugin_packages) -> None  (read-only)
    init.py               # def run(init_config, plugin_packages) -> None  (no base config)
    config_cmd.py         # def run(config) -> None
    container.py          # def run(container_config, plugin_packages) -> None
    sources.py            # 4.6
```

**Subcommand config classes** (in `cli/commands.py`):

The existing `Config` class becomes the base config shared by config-backed subcommands. We use dataclass inheritance to create subcommand-specific config classes that add their own fields:

```python
from clevis import configclass

# The existing Config class (no cmd) — loaded for all config-backed subcommands.
# It remains the base config with backend, tools, ui, context, session, plugins, etc.

@configclass(cmd="chat", help="Start the interactive REPL")
class ChatConfig(Config):
  """Config for yoker chat. Same fields as Config; no additions needed."""
  pass

@configclass(cmd="run", help="Run an agentic package non-interactively")
class RunConfig(Config):
  """Config for yoker run. Extends Config with run-specific fields."""
  source: str = ""                    # Source to run (module, URL, folder, zip)
  # Note: agent and prompt are NOT here — they come from the manifest (agent.toml)
  # CLI overrides: --agent and --prompt are handled as subcommand-specific args
  # via a local argparse, not via Clevis (they are not Config fields).
  persist: bool = False               # Enable context persistence
  session_id: str | None = None       # Session ID for persistence
  dry_run: bool = False               # Resolve and print without executing

@configclass(cmd="loop", help="Run an agentic package at intervals")
class LoopConfig(RunConfig):
  """Config for yoker loop. Extends RunConfig with loop fields."""
  interval: int = 300                 # Seconds between runs
  max_iterations: int = 100           # Default finite (not unlimited)
  max_duration: int | None = None     # Max total duration in seconds

@configclass(cmd="inspect", help="Dump a report about a source without executing it")
class InspectConfig:
  """Config for yoker inspect. No base Config needed — read-only."""
  source: str = ""                    # Source to inspect

@configclass(cmd="init", help="Generate a default configuration file")
class InitConfig:
  """Config for yoker init. No base Config needed."""
  no_interactive: bool = False
  path: str | None = None
  force: bool = False

@configclass(cmd="config", help="Display the effective configuration")
class ConfigCmdConfig(Config):
  """Config for yoker config. Same fields as Config; display only."""
  json: bool = False                  # Output as JSON instead of TOML
  show_path: bool = False             # Show config file paths
  reveal: bool = False                # Reveal masked secrets

@configclass(cmd="container", help="Generate container setup for an agentic package")
class ContainerConfig:
  """Config for yoker container. No base Config needed."""
  source: str = ""
  engine: str = "docker"              # docker or podman
  output_dir: str = "."               # Where to write files
```

**Key design decisions:**

1. **`ChatConfig` extends `Config`** — this preserves all existing CLI args (`--backend-ollama-model`, `--ui-mode`, etc.) under the `chat` subcommand. Since `Config` has all fields with defaults, the subclass can be empty. The `@configclass(cmd="chat")` decorator applies `@dataclass` and registers with Clevis.

2. **`RunConfig` extends `Config`** — `run` needs backend settings, tool configs, etc. (same as chat) plus run-specific fields. The `source` field is a Clevis-generated CLI arg (`--source`). `agent` and `prompt` are NOT Config fields — they come from the manifest. CLI overrides for `--agent` and `--prompt` are handled by a local argparse in the `run` subcommand module (these are not part of the Config tree; they override manifest values).

3. **`InspectConfig`, `InitConfig`, `ContainerConfig` are standalone** — these subcommands don't need the full `Config` tree. They have only their own fields. This means `yoker init`, `yoker inspect`, and `yoker container` bypass config loading entirely — Clevis generates their args from their own minimal config classes.

4. **`ConfigCmdConfig` extends `Config`** — `yoker config` needs to load and display the full config, so it extends `Config` and adds display-specific flags.

**Important: dataclass inheritance constraint.** All fields in `Config` have defaults (either default values or `default_factory`). Python dataclasses require that fields with defaults in the base class are followed by fields with defaults in the subclass. Since all `Config` fields have defaults, the subclasses can add fields with defaults too. This is valid.

### 2.4 Dispatch flow (in `__main__.py`)

```python
from clevis import get_cmd, get_config
from clevis import _sub_parsers  # internal, but needed to set required=False

# Register subcommand config classes (importing commands.py triggers @configclass)
from yoker.cli import commands  # noqa: F401

def main() -> None:
  # 1. Strip --with <pkg> globally (before Clevis, same as today).
  plugin_packages, sys.argv = _parse_plugin_args()

  # 2. Set subparsers to not required (for backward compat: no subcommand = chat).
  #    Clevis sets required=True by default in get_sub_parser().
  #    We override after registration, before any get_cmd() or get_config() call.
  for sub_parser in _sub_parsers.values():
    sub_parser.required = False

  # 3. Detect the subcommand via Clevis.
  cmd = get_cmd()
  if cmd is None:
    cmd = "chat"  # backward compatibility: no subcommand = chat

  # 4. Route to the appropriate subcommand.
  #    Each config-backed subcommand calls get_config() with its own class.
  #    Config-free subcommands parse their minimal config and skip base config loading.
  if cmd == "chat":
    config = get_yoker_config(cli=True)  # loads ChatConfig via Clevis
    ...  # run chat
  elif cmd == "run":
    run_config = get_config(RunConfig, name="yoker", cli=True, security=...)
    ...  # run with config
  elif cmd == "inspect":
    inspect_config = get_config(InspectConfig, name="yoker", cli=True, security=...)
    ...  # inspect source (read-only, no base config)
  elif cmd == "init":
    init_config = get_config(InitConfig, name="yoker", cli=True, security=...)
    ...  # init (no base config)
  # etc.
```

**Backward compatibility:** `python -m yoker` (no args) → `get_cmd()` returns `None` → defaults to `"chat"` → `get_config(ChatConfig, ...)` → Clevis parses with the chat subparser. Since no `[chat]` section exists in existing `~/.yoker.toml`, root-level TOML is used as-is. All existing CLI args work under `chat`.

**`yoker --backend-ollama-model X` (no subcommand):** This is the tricky case. With Clevis subparsers, `--backend-ollama-model` is a chat-subparser arg, not a top-level arg. Argparse would reject it at the top level. **Solution:** when no subcommand is detected, insert `"chat"` into `sys.argv` before Clevis parses. This is NOT a manual dispatcher — it's a one-line default-subcommand insertion, which is a common pattern for CLIs with a default command:

```python
# After stripping --with, before get_cmd():
if not _has_subcommand(sys.argv):
  sys.argv.insert(1, "chat")
```

Where `_has_subcommand` checks if any known subcommand name appears as the first positional arg. This preserves `yoker --backend-ollama-model X` → `yoker chat --backend-ollama-model X`.

### 2.5 How `--with` interacts with subcommands

`--with <pkg>` continues to be stripped before Clevis runs (same as the existing `_parse_plugin_args` pattern). Clevis doesn't know about `--with` — it's not a Config field. The stripped `plugin_packages` list is passed to every subcommand.

- `yoker chat --with pkgq` → `chat` receives `plugin_packages=["pkgq"]`
- `yoker run pkgq --with other` → `run` receives `source="pkgq"`, `plugin_packages=["other"]`
- `yoker run --with other pkgq` → same as above (order-independent because `--with` is stripped first)

For `yoker run <source>`, the `<source>` is *not* the same as `--with <pkg>` — `source` is the agentic package being run (with its manifest), while `--with` adds *additional* plugins. `source` is a Clevis-generated CLI arg (`--source`) on the `run` subparser, or a positional handled by the `run` subcommand's local argparse.

### 2.6 Subcommand function contract

Each subcommand module exports a single entry point:

- **Config-backed** (`chat`, `run`, `loop`, `config`): receives the loaded config (which is their specific config class instance, e.g. `RunConfig`). `async def run(config: RunConfig, plugin_packages: list[str]) -> None`.
- **Config-free** (`init`, `container`, `inspect`): receives their minimal config (e.g. `InspectConfig`). `def run(config: InspectConfig, plugin_packages: list[str]) -> None`.

Subcommand-specific args that are NOT part of `Config` (like `--agent`, `--prompt` for `run`) are parsed with a small local argparse in the subcommand module. These are not Config fields and don't go through Clevis.

### 2.7 Architectural concerns for 4.1

1. **Clevis internal access.** Setting `sub_parsers.required = False` requires accessing Clevis's internal `_sub_parsers` dict. This is a mild coupling to Clevis internals. Alternative: after the first `get_cmd()` call (which triggers `_ensure_configured`), iterate `_sub_parsers.values()`. If Clevis adds a public API for this in the future, we switch to it. Document this coupling.

2. **`yoker config` naming collision.** The subcommand is `config`, but `yoker.config` is the Python module. Name the subcommand module `cli/config_cmd.py` (as the TODO already specifies) to avoid an import shadow. The subcommand string remains `config` for the user.

3. **Dataclass inheritance and `@configclass`.** `@configclass` applies `@dataclass` to the class. When a subclass like `RunConfig(Config)` is decorated with `@configclass(cmd="run")`, Clevis re-applies `@dataclass`. Python dataclass re-decoration on a subclass is safe — it processes the subclass's own fields plus inherited fields. Verify that `Factory.list_fields()` correctly traverses inherited fields (it uses `fields(clz)` which includes inherited fields).

4. **Help text.** Clevis generates per-subcommand help via `yoker chat --help`, `yoker run --help`, etc. The top-level `yoker --help` shows the subcommand list (argparse's default behavior with subparsers). This is cleaner than the manual dispatcher's custom help formatter.

5. **`get_yoker_config` adaptation.** The existing `get_yoker_config(cli=True)` calls `get_config(Config, name="yoker", cli=True)`. For subcommands, we need `get_config(ChatConfig, ...)` or `get_config(RunConfig, ...)`. Add a `get_yoker_config_for(cmd: str, cli: bool = True)` helper, or have each subcommand call `get_config()` directly with its config class. The security bypass logic (YOKER_DEV_MODE, PYTEST_CURRENT_TEST) should be factored into a shared helper.

---

## 3. Recommended Design for 4.5 — Manifest as Config-Override Layer

### 3.1 Owner's vision: generic config overrides

The owner's feedback redefines the manifest from "additive fields on PluginManifest" to a **generic config-override layer**. The key insight: the manifest should work just like CLI args override config values — the manifest can override ANY `Config` field, not just `agent` and `prompt`.

**Layering (precedence low to high):**

1. Dataclass defaults
2. User-level TOML (`~/.yoker.toml`)
3. Project-level TOML (`./yoker.toml`)
4. **Manifest overrides** (`<source>/agent.toml`) — NEW layer
5. CLI arguments (highest priority)

This means a source's manifest can override the backend model, disable tools, change UI mode, set the agent, define the prompt, and more — all through the same TOML syntax that `~/.yoker.toml` uses. The manifest is not a separate schema; it's another config layer.

### 3.2 File-based manifest: `agent.toml`

The manifest file is named `agent.toml` (not `yoker.toml`) to avoid collision with the project-level configuration file `yoker.toml`. The owner raised this collision concern explicitly: "for the file-based manifest: don't use yoker.toml, that is already used for our project-level configuration."

`agent.toml` lives in the **source root** (the package/folder/zip being run). Its location is naturally separate from the user's `~/.yoker.toml` and the project's `./yoker.toml`:

```
~/.yoker.toml                  # User config (backend, plugins, etc.)
./yoker.toml                   # Project config (overrides user)
./my-agent-package/            # The source being run
  agent.toml                   # Source manifest (overrides project config when running this source)
  skills/                      # Skills provided by the source
  agents/                      # Agent definitions provided by the source
```

**Format:**

```toml
# agent.toml — source manifest for a yoker-based agentic package

# Run configuration (source-specific, extracted before config merge)
[run]
agent = "researcher"                              # Agent definition name to use
prompt = "Analyze the codebase and create a PACKAGE.md"  # Initial prompt

# Plugin configuration (source-specific, extracted before config merge)
[plugin]
skills_dir = "skills"     # Directory containing skill definition files
agents_dir = "agents"      # Directory containing agent definition files
tools_module = "my_plugin.tools"  # Optional: Python module to import tools from

# Config overrides (any Config field can be overridden here)
# These are merged into the base Config between project TOML and CLI args.
[backend.ollama]
model = "llama3.2"         # Use a specific model for this source

[tools.git]
enabled = false            # Disable git tools for this source

[ui]
mode = "batch"             # Force batch mode for non-interactive execution
```

**Parsing rules:**
- `[run]` is optional. Contains `agent` (str) and `prompt` (str). Both default to `None` if omitted.
- `[plugin]` is optional. Contains `skills_dir` (str, default "skills"), `agents_dir` (str, default "agents"), `tools_module` (str, optional).
- All other tables/keys are treated as **config overrides** — they are merged into the base config dict using the same `apply_to_dict` mechanism that Clevis uses for CLI args.
- If neither `[run]` nor `[plugin]` is present and there are no config overrides, the file is effectively a no-op.
- Malformed TOML raises a clear `PluginError` with the file path and parse error.
- If `agent.toml` doesn't exist, the source is treated as a plain plugin (no run configuration — `yoker run` requires at least `prompt` to be set via CLI or manifest).

### 3.3 Config loading with manifest overrides

The config loading path is extended to accept a manifest:

```python
# src/yoker/config/__init__.py (extended)

def get_yoker_config_with_manifest(
  manifest_path: Path | None = None,
  cli: bool = False,
) -> tuple[Config, RunConfig, PluginManifestConfig]:
  """Load config with manifest overrides.

  Returns (config, run_config, plugin_manifest_config) where:
  - config: the full Config with manifest overrides applied
  - run_config: the [run] section from the manifest (agent, prompt)
  - plugin_manifest_config: the [plugin] section (skills_dir, agents_dir, tools_module)
  """
  # 1. Load base config from TOML (same as Clevis does: ~/.yoker.toml, ./yoker.toml)
  #    We use Clevis's get_config with cli=False to get the base config dict.
  # 2. Load manifest TOML (if manifest_path and file exists)
  # 3. Extract [run] and [plugin] sections from manifest
  # 4. Remaining manifest keys are config overrides — deep-merge into base config dict
  # 5. Apply CLI args (if cli=True) on top — Clevis's apply_to_dict
  # 6. Convert to Config via dacite.from_dict
```

**Implementation approach:** Since Clevis's `get_config()` doesn't support an extra config layer, we implement the manifest merge in yoker's config module. We use Clevis's internal functions (`_load_toml`, `apply_to_dict`) and `dacite.from_dict` directly. This is a clean separation — we're not modifying Clevis, just adding a layer in yoker's config module that uses Clevis's building blocks.

Alternatively, the manifest overrides can be written to a temporary TOML file and passed as a third Clevis config source. But the direct-merge approach is simpler and avoids temp file management.

### 3.4 Python manifest (`__YOKER_MANIFEST__`)

The Python `__YOKER_MANIFEST__` object in a package's `__init__.py` continues to declare tools, skills, and agents (the existing mechanism). For `yoker run`, the Python manifest's `agent` and `prompt` fields (if set) serve as a fallback when no `agent.toml` exists:

```python
# In a Python package's __init__.py
__YOKER_MANIFEST__ = PluginManifest(
  tools=[...],
  skills=[...],
  agents=[...],
  agent="researcher",     # NEW: optional, fallback for yoker run
  prompt="Analyze...",    # NEW: optional, fallback for yoker run
)
```

**Precedence for `agent`/`prompt`:**
1. CLI override (`--agent`, `--prompt`) — highest
2. `agent.toml` `[run]` section — if file manifest exists
3. Python `__YOKER_MANIFEST__.agent`/`.prompt` — fallback for packages without `agent.toml`
4. Error if none of the above provide both `agent` and `prompt`

**`PluginManifest` changes:** add `agent` and `prompt` fields (optional, default `None`). These are NOT config overrides — they are convenience fields for Python packages that want to be runnable without a separate `agent.toml`:

```python
@dataclass
class PluginManifest:
  # Existing fields
  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list["Skill"] = field(default_factory=list)
  agents: list["AgentDefinition"] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"

  # New: convenience fields for yoker run (fallback when no agent.toml exists)
  agent: str | None = None
  prompt: str | None = None
```

### 3.5 Carrying the manifest into the run path

```python
@dataclass
class ResolvedSource:
  """Result of resolving a `yoker run <source>` argument.

  Carries the loaded plugin components, the run configuration (agent/prompt),
  the plugin manifest config (skills_dir, agents_dir, tools_module), and an
  optional cleanup hook for temp resources.
  """
  components: PluginComponents
  agent: str | None = None          # From agent.toml [run] or Python manifest
  prompt: str | None = None         # From agent.toml [run] or Python manifest
  skills_dir: str = "skills"        # From agent.toml [plugin]
  agents_dir: str = "agents"        # From agent.toml [plugin]
  tools_module: str | None = None   # From agent.toml [plugin]
  cleanup: Callable[[], None] | None = None
```

**Why a new dataclass and not extending `PluginComponents`:** `PluginComponents` is consumed by `ToolRegistry.register_plugin_tools`, `SkillRegistry.register_plugin_skills`, `AgentRegistry.register_plugin_agents` — all of which should not need to know about run-config or cleanup. Keeping the run fields in `ResolvedSource` preserves the single-responsibility boundary.

### 3.6 Loader integration

The current `load_plugin(package_name)` is hardwired to `importlib.import_module`. Generalize it with a `Source` abstraction:

```python
# src/yoker/plugins/loader.py (extended)

@dataclass
class Source:
  """A resolved source location to load plugin components from."""
  kind: Literal["package", "folder"]
  package: str | None = None       # for kind="package"
  path: Path | None = None         # for kind="folder"
  # File manifest data (from agent.toml, for kind="folder")
  skills_dir: str = "skills"
  agents_dir: str = "agents"
  tools_module: str | None = None

def load_plugin_from_source(source: Source) -> PluginComponents:
  if source.kind == "package":
    return load_plugin(source.package)  # existing path
  # folder path: load skills/agents from source.path / skills_dir / agents_dir,
  # import tools from source.tools_module if set,
  # return PluginComponents with source=<str(source.path)>
```

`resolve_source(source_arg: str) -> ResolvedSource` (task 4.6) builds a `Source`, calls `load_plugin_from_source`, reads `agent`/`prompt` from the file manifest or Python manifest, and constructs a `ResolvedSource`.

### 3.7 Backward compatibility

- Existing `PluginManifest(...)` call sites (notably `src/yoker/builtin/__init__.py`) are unchanged — the new `agent`/`prompt` fields default to `None`.
- Existing `load_plugin("yoker")` / `load_plugin("pkgq")` paths are unchanged — they still return `PluginComponents` without `agent`/`prompt`. The run fields are accessed only by `yoker run` via `ResolvedSource`, not by the chat/registry paths.
- `load_plugins(config, extra_plugins)` (the generator consumed by registries) is unchanged. `ResolvedSource` is a *run-command* construct; the chat path never sees it.
- Existing `~/.yoker.toml` and `./yoker.toml` files are unchanged — the manifest is an additional layer that only applies when running a source.
- No existing tests should break from the dataclass change (additive fields with defaults).

### 3.8 Architectural concerns for 4.5

1. **`tools_module` imports arbitrary Python code.** The manifest's `tools_module` field triggers `importlib.import_module` on a module within the source. This is the same trust model as `--with <package>`. The trust gate (`check_plugin_allowed`) MUST apply — the source must pass the trust check before `tools_module` is imported. The `source` identifier for a folder source is the folder path (or a stable hash) so it can be allow-listed. Per the owner's feedback, `yoker run <source>` goes through the same trust gate as `--with <source>` — no bypass, no parallel tracks.

2. **`agent` name resolution scope.** `agent = "researcher"` in a manifest — resolved against the union of (a) the source's own loaded agent definitions and (b) the built-in agent registry loaded via `config.agents.directories`. If the name is ambiguous (same name in source and built-in), **source wins** (the source is the agentic package being run). The owner confirmed: "source-based named items 'override' existing ones (although given namespacing, I don't expect that to happen quickly)."

3. **No `config_class` for file manifests.** The existing `config_class` field on `PluginManifest` lets a plugin declare a config section that Clevis wires into `Config`. File manifests cannot declare a `config_class` (they can't reference a Python type by name safely). This is an acceptable limitation for MBI-004; document that `config_class` is Python-manifest-only.

4. **Manifest config overrides vs. plugin config_class.** If a Python plugin has a `config_class` (wired into Config via Clevis), and the source's `agent.toml` also overrides that same config section, the manifest override takes precedence (it's a higher layer). This is consistent with the layering rules.

---

## 4. Brief Outline for 4.6 — Source Resolution

`resolve_source(source: str) -> ResolvedSource` lives in `src/yoker/cli/sources.py`.

### 4.1 Detection

```python
def detect_kind(source: str) -> Literal["url", "zip", "folder", "module"]:
  if source.startswith(("http://", "https://")):
    return "url"
  if source.endswith(".zip") and not Path(source).is_dir():
    return "zip"
  if Path(source).is_dir():
    return "folder"
  return "module"
```

**Order matters:** check URL first (a URL is never a local path), then zip (by extension), then folder (filesystem check), then fall back to module name. A `.zip` that happens to be a directory name is vanishingly unlikely; the `not Path(source).is_dir()` guard handles it.

### 4.2 Resolution per kind

- **module**: `Source(kind="package", package=source)` → `load_plugin_from_source` → read `agent`/`prompt` from the Python manifest. Cleanup: `None`.
- **folder**: `Source(kind="folder", path=Path(source))` → load `agent.toml` via `load_file_manifest` → `load_plugin_from_source`. Cleanup: `None`.
- **url**: `git clone --depth 1 <url>` into `tempfile.TemporaryDirectory()` → resolve as folder. Cleanup: `tmpdir.cleanup()`.
- **zip**: validate `zipfile.is_zipfile()`, extract with safe extraction (reject `..` and absolute paths) into a `tempfile.TemporaryDirectory()` → resolve as folder. Cleanup: `tmpdir.cleanup()`.

### 4.3 Two-phase resolve/load (trust gate)

Per the owner's feedback, `yoker run <source>` goes through the **same trust gate** as `--with <source>`. No bypass, no parallel tracks. The existing `check_plugin_allowed()` is reused.

`resolve_source()` is split into two phases:

1. **`resolve_source(source: str) -> ResolvedSourceMetadata`** — resolves the source type, reads the manifest (agent.toml or `__YOKER_MANIFEST__`), returns metadata only. NO imports, NO `tools_module` execution, NO `pip install`. This is safe to call without trust.

2. **`load_source(metadata: ResolvedSourceMetadata, config: Config) -> ResolvedSource`** — performs the actual imports (`importlib.import_module` for packages, `tools_module` import for folders), loads skills/agents, and returns the full `ResolvedSource`. This is called ONLY after `check_plugin_allowed()` returns True.

For `yoker inspect <source>`, only phase 1 is needed — it reads the manifest and displays a report without executing any code. No trust gate needed for inspect (read-only, no code execution). `tools_module` is listed but NOT imported.

### 4.4 `ResolvedSource` cleanup contract

`ResolvedSource.cleanup` is an optional callable. The `run` subcommand calls it in a `finally` block:

```python
resolved = resolve_source(source_arg)
try:
  await _run_resolved(resolved, config, ...)
finally:
  if resolved.cleanup is not None:
    resolved.cleanup()
```

For `loop`, cleanup runs *between* iterations only if the source is re-resolved each iteration. Recommendation: re-resolve each iteration (GitHub sources may update between runs; a fresh clone is the correct semantics for a loop). Cleanup runs at the end of each iteration.

### 4.5 Security considerations

1. **Zip path traversal.** Use a safe extraction helper that rejects any entry whose resolved path escapes the extraction root. Reject absolute paths and `..` components. There is prior art in Python's stdlib docs (`zipfile` extraction examples) — implement the documented safe pattern.

2. **GitHub clone.** Use `git clone --depth 1` (shallow). Do not pass credentials through yoker; rely on git's native credential helpers / SSH keys. Clone into a temp dir with a predictable prefix (`yoker-source-*`) for debuggability. Do not execute any code from the repo during clone (code execution happens only when `tools_module` is imported, which is gated by trust).

3. **No auto-install of `pyproject.toml` — clarified.** When loading a folder source that contains a `pyproject.toml`, the question is whether to automatically `pip install` it. Auto-installing runs build hooks (setup.py, PEP 517 build backend) — this is **arbitrary code execution** (CWE-494). The recommendation is to **NOT auto-install by default**. For MBI-004, folder/zip sources load via the file manifest + `tools_module` import; full package installation requires an explicit `--install` flag (deferred to a future MBI). If a folder has a `pyproject.toml` but no `agent.toml`, yoker does not install it — it either loads from the folder structure directly or errors with a message explaining that `--install` is needed (future MBI).

4. **Trust gate — reuses existing guardrails.** Per the owner's feedback: "Currently when issuing `--with <pkg>` we don't consider this an explicit opt-in. So, I wouldn't change that behaviour. Let's keep these guardrails in place and reuse them, not creating parallel tracks." `yoker run <source>` goes through `check_plugin_allowed()` — the same gate as `--with`. The source must be either in `[plugins.trusted]`, confirmed interactively, or rejected in non-interactive mode. No bypass for named sources.

5. **`yoker inspect <source>` — no trust gate needed.** Inspect is read-only: it resolves the source, reads the manifest, and displays a report. It does NOT import `tools_module`, does NOT execute any code, and does NOT call `load_source()`. Only `resolve_source()` (phase 1, metadata only) is called. The `tools_module` field is listed in the report but NOT imported. This makes inspect safe without a trust gate.

---

## 5. Architectural Recommendations (cross-cutting)

1. **Reuse the Python API in `run`.** The `run` subcommand should delegate to the same config/agent construction path as `yoker.api.process` / `yoker.api.session` rather than reimplementing Session+Agent wiring. Specifically, `yoker run <source>` is close to `yoker.process(prompt, plugins=(source,))` with the agent resolved from the manifest. Factor a shared helper (or call `yoker.api` internals) so the CLI and the Python API don't diverge.

2. **Let Clevis handle command dispatch.** The `__main__.py` entry point strips `--with`, defaults the subcommand to `chat` when none is given, then calls `get_cmd()` and routes. Each subcommand owns its config class and calls `get_config()` with it. No manual dispatcher, no parallel routing — Clevis's `@configclass(cmd=...)` handles subparser creation and arg generation.

3. **One async entry point per config-backed subcommand.** `chat`, `run`, `loop` are async; `init`, `config`, `container`, `inspect` are sync. `__main__.py` calls `asyncio.run(...)` for the async ones. Don't make all subcommands async — `init` and `container` have no async work and shouldn't pay the event-loop overhead.

4. **Test Clevis command dispatch with table-driven tests.** Test that `get_cmd()` correctly detects each subcommand, that the default-to-chat logic works, and that `--with` is stripped before Clevis runs. Test that each subcommand's CLI args are generated correctly.

5. **Document the manifest as a contract.** The `agent.toml` format is the interface between an agentic package author and yoker. Document it as a versioned contract: `[run]` and `[plugin]` sections, config override syntax, precedence rules, and what happens when fields are missing. This is the surface third-party package authors will rely on, and it deserves the same care as the Python API.

6. **`yoker inspect` as a dry-run companion.** Inspect is essentially a safe, read-only `--dry-run` that shows the source's contents without executing anything. It's useful for understanding what a source contains before running it, and for debugging manifest issues. No trust gate needed because no code is executed.

---

## 6. Resolved Questions (Owner Feedback on PR #46)

All three open questions from the original review have been resolved by the owner:

1. **Trust gate for `yoker run <source>`** — RESOLVED. The owner said: "Currently when issuing `--with <pkg>` we don't consider this an explicit opt-in. So, I wouldn't change that behaviour. Let's keep these guardrails in place and reuse them, not creating parallel tracks." `yoker run <source>` goes through `check_plugin_allowed()` — same gate as `--with`. No bypass.

2. **`agent` name resolution scope** — RESOLVED. The owner confirmed: "source-based named items 'override' existing ones (although given namespacing, I don't expect that to happen quickly)." Source agent definitions override built-in ones.

3. **File-manifest filename** — RESOLVED. The owner said: "don't use yoker.toml, that is already used for our project-level configuration." We use `agent.toml` as the filename, which avoids the collision entirely.

**New requirements from owner feedback:**

4. **Clevis commands** — The owner pushed back on the manual dispatcher: "Clevis has support for commands." The design now uses `@configclass(cmd=...)` and `get_cmd()`.

5. **Manifest as config-override layer** — The owner said: "Can't we create a generic way to override the existing configuration? Just like the CLI arguments can override. We would have: 2 levels of TOML config → Manifest overrides → CLI overrides." The manifest is now a generic config-override layer, not additive fields.

6. **`yoker inspect <source>`** — New subcommand added by the owner: "add an additional subcommand: `yoker inspect <source>` that dumps a report about the source, explaining what it contains, what it uses, what it does."

7. **"Defer auto-installing pyproject.toml"** — The owner asked for clarification. This means: when loading a folder source containing `pyproject.toml`, do NOT automatically `pip install` it (build hooks = arbitrary code execution). Require an explicit `--install` flag (deferred to a future MBI).

---

## 7. Action Items

- [x] Confirm the three open questions in section 6 with the user — all resolved via PR #46 feedback.
- [ ] 4.1: implement Clevis subcommand config classes (`@configclass(cmd=...)`) per section 2.3.
- [ ] 4.1: implement default-to-chat logic (insert "chat" when no subcommand detected) per section 2.4.
- [ ] 4.1: set `_sub_parsers.required = False` for backward compatibility.
- [ ] 4.5.1: add `agent`/`prompt` fields to `PluginManifest` (additive, default `None`).
- [ ] 4.5.2: implement `load_file_manifest` for `agent.toml` (parse, extract `[run]`/`[plugin]`, return config overrides + run config + plugin config).
- [ ] 4.5.3: implement `get_yoker_config_with_manifest()` — config loading with manifest as override layer.
- [ ] 4.5.4: introduce `ResolvedSource` + `Source` abstraction; generalize `load_plugin` into `load_plugin_from_source`.
- [ ] 4.6: implement two-phase `resolve_source()` (metadata only) + `load_source()` (imports, gated by trust).
- [ ] 4.6: implement `resolve_source` with the detection order in section 4.1 and safe zip/url handling.
- [ ] 4.12: implement `yoker inspect <source>` — read-only report, no trust gate, no code execution.
- [ ] 4.10: Clevis command dispatch tests + manifest tests + source resolution tests + inspect tests.
- [ ] 4.11: document `agent.toml` as a versioned contract for package authors.