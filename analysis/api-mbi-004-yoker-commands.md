# API Architecture Review: MBI-004 yoker Commands

**Date**: 2026-07-08
**Reviewer**: API Architect Agent
**Task**: Review design for tasks 4.1 (CLI Subcommand Dispatcher) and 4.5 (Extended Manifest), with a brief outline for 4.6 (Source Resolution).
**Design source of truth**: `analysis/mbi-004-yoker-commands.md`
**Task breakdown**: `TODO.md` (section "## Active: MBI-004: yoker Commands")

## Summary

The MBI-004 design is internally coherent and well-scoped. The functional analysis already resolves most of the hard product questions (six subcommands, backward-compat default to `chat`, source type detection, manifest extension fields). This review focuses on the architectural decisions that the functional analysis leaves open or underspecifies, and makes concrete recommendations for:

1. **4.1 CLI dispatcher** — a lightweight manual dispatcher sitting *in front of* Clevis, not replacing it. Clevis continues to generate the `Config`-derived CLI args for the subcommands that need a `Config` (`chat`, `run`, `loop`, `config`); subcommands that don't (`init`, `container`) bypass Clevis entirely. This preserves the existing annotation-driven CLI generation pattern and avoids a hard dependency on a new framework (click/typer).
2. **4.5 Extended manifest** — extend `PluginManifest` with `agent` and `prompt` fields (additive, backward compatible). Introduce a parallel file-based manifest (`yoker.toml`) that deserializes into the same `PluginManifest` shape, with a clearly documented precedence rule (Python `__YOKER_MANIFEST__` wins for tools/skills/agents; the file manifest is the *only* way to declare `agent`/`prompt` for non-Package sources). Add a `ResolvedSource` carrier dataclass so the manifest travels with `PluginComponents` into the run path.
3. **4.6 Source resolution** — a `resolve_source()` function returning a `ResolvedSource` with a `cleanup` hook, with security considerations for zip path traversal and GitHub clone hygiene.

One key architectural concern: the functional analysis proposes merging Python-manifest and file-manifest fields with "Python manifest takes precedence for tools/skills/agents; file manifest can supplement with agent/prompt." This is sound, but the loader currently keys everything off `importlib.import_module(package_name)`, which cannot resolve a folder or zip. The source-resolution layer must produce something the existing `load_plugin` machinery can consume, or `load_plugin` must be generalized. The recommendation below is to **generalize the loader** with a `Source` abstraction rather than threading folder/zip special cases through `load_plugin`.

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

## 2. Recommended Design for 4.1 — CLI Subcommand Dispatcher

### 2.1 Alternatives considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **A. argparse subparsers for everything** | Replace Clevis with argparse; hand-port every `Config` field to an argparse argument. | Rejected — rewrites the entire config CLI surface, loses annotation-driven generation, enormous regression risk. |
| **B. click / typer** | Adopt a third-party CLI framework; use it for subcommand dispatch and either drop Clevis or wrap it. | Rejected — introduces a new hard dependency for a thin dispatch layer; the project has no existing click/typer usage; the win over a manual dispatcher is small. The functional analysis does not request a framework swap. |
| **C. Clevis-only (no subcommands)** | Keep Clevis as the sole parser; encode the subcommand as a `Config` field. | Rejected — `init` and `container` don't need a `Config` and shouldn't be forced to load one. Also makes the CLI surface (`--chat`, `--run`) read as flags rather than subcommands, which is UX-hostile. |
| **D. Lightweight manual dispatcher in front of Clevis (recommended)** | A small dispatcher peels off the subcommand and `--with` args, then hands the remaining `argv` to Clevis for the subcommands that need a `Config`. Subcommands that don't need a `Config` never invoke Clevis. | **Recommended** — minimal change to existing patterns, preserves Clevis for `Config` args, lets `init`/`container` bypass config loading entirely. |

### 2.2 Recommended design: manual dispatcher + Clevis per-subcommand

**Structure:**

```
src/yoker/
  __main__.py            # thin: calls cli.dispatch()
  cli/
    __init__.py           # exports dispatch()
    dispatcher.py         # parse subcommand + --with, route to subcommand
    shared.py             # shared setup: load_config(), configure_logging, bootstrap gate
    chat.py               # async def run(args, config, plugin_packages) -> None
    run.py                # async def run(args, config, plugin_packages) -> None
    loop.py
    init.py               # def run(args) -> None  (no config)
    config_cmd.py         # def run(args, config) -> None
    container.py          # def run(args) -> None  (no config)
    sources.py            # 4.6
```

**Dispatch algorithm** (in `cli/dispatcher.py`):

```python
SUBCOMMANDS = {"chat", "run", "loop", "init", "config", "container"}

def dispatch(argv: list[str] | None = None) -> None:
  if argv is None:
    argv = sys.argv

  # 1. Strip --with <pkg> globally (shared across all subcommands).
  plugin_packages, argv = _parse_plugin_args(argv)

  # 2. Peel off the subcommand: first non-flag positional.
  subcommand, subcommand_argv = _peel_subcommand(argv, SUBCOMMANDS)

  # 3. Default to chat for backward compatibility (no subcommand given).
  if subcommand is None:
    subcommand = "chat"
    subcommand_argv = argv  # all remaining args belong to chat

  # 4. Route. Subcommands that need a Config go through shared.load_config(cli=True)
  #    (which calls Clevis on subcommand_argv). Subcommands that don't bypass Clevis.
  if subcommand in {"chat", "run", "loop", "config"}:
    config = shared.load_config(subcommand_argv)  # Clevis parses Config args
    shared.configure_logging(config)
    if subcommand == "chat":
      shared.maybe_bootstrap(config)  # pre-flight wizard, chat-only
    _run_async(subcommand, config, plugin_packages, subcommand_argv)
  else:  # init, container — no Config
    _run_sync(subcommand, plugin_packages, subcommand_argv)
```

**`_peel_subcommand`** scans `argv` for the first positional that is in `SUBCOMMANDS` and is not the value of a preceding flag. To keep this robust without re-implementing a parser, the simplest rule is: the first positional argument that is in `SUBCOMMANDS`. This matches user expectation (`yoker run pkgq`) and avoids ambiguity with Clevis flags (which are all `--`-prefixed). The `--with <pkg>` values are already stripped in step 1, so a package named `run` passed via `--with run` won't be misread as a subcommand.

**Backward compatibility:** `python -m yoker` (no args) → `subcommand is None` → defaults to `chat`. `python -m yoker --ui-mode batch` → no positional subcommand → defaults to `chat`, `--ui-mode batch` flows to Clevis. This is the exact current behavior.

**Unknown subcommand:** if the first positional is not in `SUBCOMMANDS` and is not a flag, print an error listing valid subcommands and exit non-zero. (Distinguish from "no subcommand" by checking whether any positional was present.)

### 2.3 How `--with` interacts with subcommands

`--with <pkg>` is a **global** flag: it is stripped in step 1, before subcommand dispatch, and the resulting `plugin_packages` list is passed to every subcommand. This means:

- `yoker chat --with pkgq` → `chat` receives `plugin_packages=["pkgq"]`
- `yoker run pkgq --with other` → `run` receives `source="pkgq"`, `plugin_packages=["other"]`
- `yoker run --with other pkgq` → same as above (order-independent because `--with` is stripped first)

The functional analysis says `--with` "still works across all subcommands." This design satisfies that. Note: for `yoker run <source>`, the `<source>` is *not* the same as `--with <pkg>` — `source` is the agentic package being run (with its extended manifest), while `--with` adds *additional* plugins. The dispatcher must treat `<source>` as a positional belonging to the `run`/`loop`/`container` subcommand, not as a global flag. This is handled by peeling the subcommand *before* parsing the subcommand's own positionals.

### 2.4 Shared setup (`cli/shared.py`)

Extract from the current `main()`:

- `load_config(argv) -> Config` — wraps `get_yoker_config(cli=True)`, passing `argv` so Clevis parses only the subcommand's args. (Clevis reads `sys.argv` by default; the dispatcher must either set `sys.argv = subcommand_argv` before calling Clevis, or pass `argv` through if Clevis supports it. Verify Clevis's `get_config` signature; if it only reads `sys.argv`, the dispatcher temporarily replaces `sys.argv` around the Clevis call. This mirrors the existing `_parse_plugin_args` pattern which already mutates `sys.argv`.)
- `configure_logging(config)` — current logging setup.
- `maybe_bootstrap(config)` — the pre-flight wizard gate, **chat-only.** `run`/`loop`/`container` skip it (they specify what to run; if no backend is configured they error clearly rather than launching a wizard). `init` has its own flow.
- `_create_ui(config)` — current UI selection.

### 2.5 Subcommand function contract

Each subcommand module exports a single entry point with a consistent signature. Two shapes:

- **Config-backed** (`chat`, `run`, `loop`, `config`): `async def run(args: list[str], config: Config, plugin_packages: list[str]) -> None` (or `def run(...)` for `config`, which is synchronous).
- **Config-free** (`init`, `container`): `def run(args: list[str], plugin_packages: list[str]) -> None`.

`args` is the subcommand's remaining `argv` (after subcommand peel and `--with` strip), which the subcommand parses with a small local argparse for its own flags (`--agent`, `--prompt`, `--persist`, `--session-id`, `--no-interactive`, `--path`, `--force`, `--json`, `--engine`, `--output-dir`, `--interval`, `--max-iterations`). These are subcommand-specific and not part of `Config`, so they do not go through Clevis.

### 2.6 Architectural concerns for 4.1

1. **`sys.argv` mutation.** The existing code already mutates `sys.argv` (via `_parse_plugin_args` reassigning the return). The dispatcher must do this carefully and restore `sys.argv` if a subcommand needs to call Clevis (Clevis reads `sys.argv`). The cleanest approach: the dispatcher never calls Clevis itself; `shared.load_config(subcommand_argv)` sets `sys.argv = subcommand_argv` for the duration of the Clevis call. This is the established pattern in the file.

2. **`yoker config` naming collision.** The subcommand is `config`, but `yoker.config` is the Python module. Name the subcommand module `cli/config_cmd.py` (as the TODO already specifies) to avoid an import shadow. The subcommand string remains `config` for the user.

3. **Help text.** `yoker --help` should list subcommands. Since Clevis generates the top-level help for `Config` args, the dispatcher should intercept `--help`/`-h` *before* subcommand peel and print a combined help (subcommands + pointer to `yoker chat --help` for Config args). This is a small, self-contained help formatter in the dispatcher. Per-subcommand `--help` is handled by the subcommand's local argparse.

4. **Don't over-abstract.** The dispatcher is ~50 lines. Resist adding a "subcommand registry" abstraction with decorators; a plain dict mapping name → function is enough and easier to read. Six subcommands do not justify a plugin system for the CLI itself.

---

## 3. Recommended Design for 4.5 — Extended Manifest

### 3.1 `PluginManifest` dataclass changes

Add two fields, both optional and defaulting to `None` (fully backward compatible — every existing `PluginManifest(...)` call site is unchanged):

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

  # New: agentic-executable fields (MBI-004)
  agent: str | None = None   # Which agent definition name to use for `yoker run`
  prompt: str | None = None  # Initial prompt injected when running via `yoker run`
```

**Semantics:**
- `agent` is a *name* (string), resolved against the union of the plugin's own agent definitions and the built-in agent registry at run time. It is not a path and not an `AgentDefinition` instance — keeping it a name lets the file-based manifest reference it and lets `--agent <name>` override it uniformly.
- `prompt` is the literal initial user message. No template substitution in MBI-004 (defer to a future MBI; if needed later, document a `[run]` table extension).
- Both default to `None`. `yoker run` requires both to be set (after CLI overrides) and errors clearly if either is missing.

### 3.2 Carrying the manifest into the run path

`PluginComponents` currently carries `tools`, `skills`, `agents`, `source`. Add the manifest's run fields to a new carrier rather than overloading `PluginComponents`:

```python
@dataclass
class ResolvedSource:
  """Result of resolving a `yoker run <source>` argument.

  Carries the loaded plugin components plus the extended manifest's run
  configuration (agent/prompt) and an optional cleanup hook for temp
  resources (GitHub clones, zip extractions).
  """
  components: PluginComponents
  agent: str | None = None
  prompt: str | None = None
  cleanup: Callable[[], None] | None = None
```

**Why a new dataclass and not extending `PluginComponents`:** `PluginComponents` is consumed by `ToolRegistry.register_plugin_tools`, `SkillRegistry.register_plugin_skills`, `AgentRegistry.register_plugin_agents` — all of which should not need to know about `agent`/`prompt`/`cleanup`. Keeping the run-config fields in `ResolvedSource` preserves the single-responsibility boundary: `PluginComponents` is registry food; `ResolvedSource` is run-command food.

### 3.3 File-based manifest (`yoker.toml`)

Introduce `src/yoker/plugins/file_manifest.py` with `load_file_manifest(path: Path) -> PluginManifest | None`.

**Format** — a `yoker.toml` at the source root with two optional tables:

```toml
# yoker.toml — file-based yoker manifest for a folder/zip source

[run]
agent = "researcher"                              # Agent definition name to use
prompt = "Analyze the codebase and create a PACKAGE.md"  # Initial prompt

[plugin]
skills_dir = "skills"     # Directory containing skill definition files
agents_dir = "agents"      # Directory containing agent definition files
tools_module = "my_plugin.tools"  # Optional: Python module to import tools from
```

**Parsing rules:**
- `[run]` is optional. If present, `agent` and `prompt` are strings; both default to `None` if omitted.
- `[plugin]` is optional. `skills_dir`/`agents_dir` default to `"skills"`/`"agents"` (matching `PluginManifest` defaults). `tools_module` is optional.
- If neither table is present, the file is effectively a no-op manifest (returns a `PluginManifest()` with all defaults) — but `load_file_manifest` should return `None` when the file doesn't exist, so the caller can distinguish "no manifest" from "empty manifest."
- Malformed TOML raises a clear `PluginError` (reuse the existing exception) with the file path and parse error.

**Why a `PluginManifest` return type (not a separate dataclass):** the file manifest deserializes into the *same shape* as the Python manifest. This means the run path has one type to consume (`PluginManifest` / `ResolvedSource`), regardless of whether the source was a Python package or a folder. The only difference is that a file-based manifest cannot inline tool callables (tools are Python functions); it declares `tools_module` instead, which the loader imports.

### 3.4 Precedence and merging

The functional analysis says: "Python manifest takes precedence for tools/skills/agents; file manifest can supplement with agent/prompt." This is the right call. Concretely, when a source provides *both* a `__YOKER_MANIFEST__` and a `yoker.toml` (rare, but possible for a Python package that also ships a file manifest):

| Field | Source of truth |
|-------|-----------------|
| `tools` | Python `__YOKER_MANIFEST__` (file manifest's `tools_module` is ignored if Python manifest exists) |
| `skills` | Python manifest (file manifest's `skills_dir` ignored if Python manifest exists) |
| `agents` | Python manifest (file manifest's `agents_dir` ignored) |
| `agent` | File manifest `[run].agent` wins; Python manifest's `agent` field is a fallback. Rationale: the file manifest is the "run configuration" surface; the Python manifest is the "component declaration" surface. |
| `prompt` | File manifest `[run].prompt` wins; Python manifest's `prompt` is a fallback. |

**Simpler rule for the common case:** if the source is a pure folder/zip (no Python package), only the file manifest applies — no merge needed. If the source is a Python package, the Python manifest is the primary; the file manifest's `[run]` section (if present) overrides `agent`/`prompt` only. Document this as: "the file manifest's `[run]` section is the authoritative run configuration; the Python manifest's `agent`/`prompt` fields are a convenience for packages that want to be runnable without a separate `yoker.toml`."

### 3.5 Loader integration

The current `load_plugin(package_name)` is hardwired to `importlib.import_module`. Generalize it with a `Source` abstraction rather than threading folder/zip special cases through:

```python
# src/yoker/plugins/loader.py (extended)

@dataclass
class Source:
  """A resolved source location to load plugin components from."""
  kind: Literal["package", "folder"]
  package: str | None = None       # for kind="package"
  path: Path | None = None         # for kind="folder"
  file_manifest: PluginManifest | None = None  # from yoker.toml, for kind="folder"

def load_plugin_from_source(source: Source) -> PluginComponents:
  if source.kind == "package":
    return load_plugin(source.package)  # existing path
  # folder path: load skills/agents from source.path / skills_dir / agents_dir,
  # import tools from source.file_manifest.tools_module if set,
  # return PluginComponents with source=<str(source.path)>
```

`resolve_source(source_arg: str) -> ResolvedSource` (task 4.6) builds a `Source`, calls `load_plugin_from_source`, then reads `agent`/`prompt` from the file manifest (folder) or the Python manifest (package) and constructs a `ResolvedSource`.

**Why generalize rather than special-case:** the existing `load_plugin` has well-tested skill/agent loading via `find_package_subdirectory`. A folder source needs the *same* loading logic but from a filesystem path instead of a package resource. Factor the shared loading into a helper that accepts either a package name or a `Path`, and have both `load_plugin` and the folder path call it. This avoids duplicating skill/agent loading code and keeps the trust gate (`check_plugin_allowed`) applied uniformly.

### 3.6 Backward compatibility

- Existing `PluginManifest(...)` call sites (notably `src/yoker/builtin/__init__.py`) are unchanged — the new fields default to `None`.
- Existing `load_plugin("yoker")` / `load_plugin("pkgq")` paths are unchanged — they still return `PluginComponents` without `agent`/`prompt`. The run fields are accessed only by `yoker run` via `ResolvedSource`, not by the chat/registry paths.
- `load_plugins(config, extra_plugins)` (the generator consumed by registries) is unchanged. `ResolvedSource` is a *run-command* construct; the chat path never sees it.
- No existing tests should break from the dataclass change (additive fields with defaults).

### 3.7 Architectural concerns for 4.5

1. **`tools_module` imports arbitrary Python code.** The file manifest's `tools_module` field triggers `importlib.import_module` on a module inside the source. This is the same trust model as `--with <package>` (the user explicitly chose to run the source), but it should be documented as such. The trust gate (`check_plugin_allowed`) should apply to file-manifest-sourced plugins too — the `source` identifier for a folder source should be the folder path (or a stable name) so it can be allow-listed. Decide and document whether folder sources require `[plugins] enabled = true` + trust, or whether `yoker run <source>` is an explicit opt-in that bypasses the global plugin gate (recommended: `yoker run` is explicit, so it bypasses `plugins.enabled` but still logs a warning for untrusted sources). **This needs an explicit decision from the user** — see open question below.

2. **`agent` name resolution scope.** `agent = "researcher"` in a manifest — resolved against which registry? Recommendation: resolve against the union of (a) the source's own loaded agent definitions and (b) the built-in agent registry loaded via `config.agents.directories`. If the name is ambiguous (same name in source and built-in), source wins (the source is the agentic package being run). Document this.

3. **No `config_class` for file manifests.** The existing `config_class` field on `PluginManifest` lets a plugin declare a config section that Clevis wires into `Config`. File manifests cannot declare a `config_class` (they can't reference a Python type by name safely). This is an acceptable limitation for MBI-004; document that `config_class` is Python-manifest-only.

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
- **folder**: `Source(kind="folder", path=Path(source))` → load `yoker.toml` via `load_file_manifest` → `load_plugin_from_source`. Cleanup: `None`.
- **url**: `git clone --depth 1 <url>` into `tempfile.TemporaryDirectory()` → resolve as folder. Cleanup: `tmpdir.cleanup()`.
- **zip**: validate `zipfile.is_zipfile()`, extract with safe extraction (reject `..` and absolute paths) into a `tempfile.TemporaryDirectory()` → resolve as folder. Cleanup: `tmpdir.cleanup()`.

### 4.3 `ResolvedSource` cleanup contract

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

### 4.4 Security considerations

1. **Zip path traversal.** Use a safe extraction helper that rejects any entry whose resolved path escapes the extraction root. Reject absolute paths and `..` components. There is prior art in Python's stdlib docs (`zipfile` extraction examples) — implement the documented safe pattern.
2. **GitHub clone.** Use `git clone --depth 1` (shallow). Do not pass credentials through yoker; rely on git's native credential helpers / SSH keys. Clone into a temp dir with a predictable prefix (`yoker-source-*`) for debuggability. Do not execute any code from the repo during clone (code execution happens only when `tools_module` is imported, which is an explicit manifest opt-in).
3. **No auto-install of `pyproject.toml`.** The functional analysis mentions optionally installing a folder's `pyproject.toml` as a package. Recommendation: **defer this.** For MBI-004, folder/zip sources load via the file manifest + `tools_module` import; full package installation is a larger surface (needs a venv, pip/uv invocation, security review). Document the deferral.
4. **Trust gate.** As noted in 3.7, decide whether `yoker run <source>` bypasses `config.plugins.enabled`. Recommendation: `yoker run` is an explicit user action naming the source, so it should bypass the global `plugins.enabled` gate (the user opted in by typing the source), but it should still respect the per-plugin trust table for *additional* `--with` plugins. Log a warning for the run-source if it's not in the trust table.

---

## 5. Architectural Recommendations (cross-cutting)

1. **Reuse the Python API in `run`.** The `run` subcommand should delegate to the same config/agent construction path as `yoker.api.process` / `yoker.api.session` rather than reimplementing Session+Agent wiring. Specifically, `yoker run <source>` is close to `yoker.process(prompt, plugins=(source,))` with the agent resolved from the manifest. Factor a shared helper (or call `yoker.api` internals) so the CLI and the Python API don't diverge.

2. **Keep the dispatcher dumb.** The dispatcher's only job is: peel subcommand, strip `--with`, route. It should not know about `Config` fields, manifest fields, or source types. Each subcommand owns its own argument parsing (local argparse for subcommand-specific flags) and its own Clevis invocation (via `shared.load_config`).

3. **One async entry point per config-backed subcommand.** `chat`, `run`, `loop` are async; `init`, `config`, `container` are sync. The dispatcher calls `asyncio.run(...)` for the async ones. Don't make all subcommands async — `init` and `container` have no async work and shouldn't pay the event-loop overhead.

4. **Test the dispatcher with table-driven tests.** The dispatcher is pure argv routing; test it with a matrix of `(argv, expected_subcommand, expected_plugin_packages, expected_subcommand_argv)`. This is the highest-ROI test in MBI-004 and should land in 4.10.1.

5. **Document the manifest as a contract.** The extended `PluginManifest` (`agent`/`prompt`) is effectively the interface between an agentic package author and yoker. Document it as a versioned contract: fields, types, precedence, and what happens when fields are missing. This is the surface third-party package authors will rely on, and it deserves the same care as the Python API.

---

## 6. Open Questions for the User

1. **Trust gate for `yoker run <source>`:** should naming a source on the command line bypass `config.plugins.enabled` (recommended — explicit opt-in), or should the user also have to set `plugins.enabled = true`? This affects whether `yoker run pkgq` works out of the box on a fresh config.

2. **`agent` name resolution scope:** confirm that the manifest's `agent` name resolves against the source's own agent definitions first, then the built-in registry, with source winning on conflict (recommended).

3. **File-manifest filename:** `yoker.toml` collides with the user/project config filename (`./yoker.toml` is currently the project config). For a folder source, `yoker run ./my-folder` would look for `./my-folder/yoker.toml` — no collision because it's inside the source folder. But for a GitHub clone landing in the current directory's `yoker.toml` location, there's potential confusion. Confirm `yoker.toml` is acceptable, or prefer `yoker-manifest.toml` to disambiguate. Recommendation: `yoker.toml` inside the source root is fine (the path scoping removes ambiguity), but document it clearly.

---

## 7. Action Items

- [ ] Confirm the three open questions in section 6 with the user before implementing 4.5/4.6.
- [ ] 4.1: implement the manual dispatcher + `cli/` package per section 2.2.
- [ ] 4.1: verify Clevis's `get_config` argv-handling (does it accept an `argv` param, or only read `sys.argv`?) — this determines whether the dispatcher mutates `sys.argv` or passes `argv` through.
- [ ] 4.5.1: add `agent`/`prompt` fields to `PluginManifest` (additive, default `None`).
- [ ] 4.5.2: implement `load_file_manifest` returning `PluginManifest | None`.
- [ ] 4.5.3: introduce `ResolvedSource` + `Source` abstraction; generalize `load_plugin` into `load_plugin_from_source`.
- [ ] 4.6: implement `resolve_source` with the detection order in section 4.1 and safe zip/url handling.
- [ ] 4.10: dispatcher tests (table-driven) + extended manifest tests + source resolution tests.
- [ ] 4.11: document the extended manifest as a versioned contract for package authors.