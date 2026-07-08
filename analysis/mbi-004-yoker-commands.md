# MBI-004: yoker Commands — Functional Analysis

## Overview

MBI-004 transforms yoker from a single interactive command into a proper CLI
with subcommands. The flagship new capability is `yoker run`, which creates
"yoker-based agentic executable packages" — sources (modules, GitHub URLs,
folders, zip files) containing an extended yoker manifest that specifies which
agent to use and injects an initial prompt.

## User Clarification (Source of Truth)

The user clarified the semantics as follows:

> Currently we are able to start yoker (cli), dropping us in an interactive
> shell-like environment. There we can start issuing prompts. These prompts
> are processed using an agent definition. That agent definition is loaded
> according to the configuration. An agent has access to skills and tools,
> also made available after loading from the configuration. We are also
> currently able to load additional agent definitions, tools and skills from
> a module (--with modulename). This is what the new "chat" command will
> simply continue to do.

> The "run" command will accept a series of different sources: a module
> (like --with), a github url, a folder-path or a zip file. All basically
> lead to the same content, just in a different format/access scheme, like
> we know from the module-support we already have. For the "run" command we
> will extend the manifest. Optionally we will create a filebased version
> of the manifest, to not only rely on Python module code that contains the
> manifest. We will extend the manifest with configuration options, to
> enable the definition of which agent to use and inject an initial prompt.
> This way, such a manifest will create a yoker-based/agentic executable
> package that can be run.

### Concrete Examples

Today (interactive):
```
% uvx --with pkgq yoker --with pkgq
> if there is no PACKAGE.md, create one.
```

Tomorrow (run):
```
% uvx --with pkgq yoker run pkgq
```

Or:
```
% uvx yoker run https://github.com/christophevg/pkgq
```

## Command Specifications

### 1. `yoker chat` (extracted from current behavior)

**Purpose**: Start the interactive REPL environment — the current default
behavior of `python -m yoker`.

**Behavior**:
- Loads configuration from TOML files + CLI args (via Clevis)
- Loads agent definitions, skills, and tools from config + `--with` plugins
- Starts the interactive REPL (or batch mode if stdin is not a TTY)
- Bootstrap wizard triggers on first run with no config (interactive only)

**CLI flags**: All current flags (`--with`, `--ui-mode`, `--backend-*`, etc.)
remain available under `yoker chat`.

**Backward compatibility**: `yoker` with no subcommand defaults to `yoker chat`
to preserve existing user workflows.

### 2. `yoker init`

**Purpose**: Generate a default configuration file, optionally with bootstrap
questions.

**Behavior**:
- Interactive mode: runs the bootstrap wizard (reuses existing
  `BootstrapWizard` from `yoker/bootstrap/`)
- Non-interactive mode (`--no-interactive`): writes a default `~/.yoker.toml`
  with all defaults commented out (using the existing annotation-driven
  `render_config_toml` from `yoker/config/writer.py`)
- `--path <path>`: write to a custom location instead of `~/.yoker.toml`
- `--force`: overwrite an existing config file

**Difference from bootstrap**: `yoker init` is an explicit, on-demand command.
Bootstrap is the automatic first-run trigger; `yoker init` gives the user
control over when and where to generate config.

### 3. `yoker config`

**Purpose**: Display the effective configuration.

**Behavior**:
- Loads config from TOML + CLI args (same as chat)
- Prints the resolved config as TOML to stdout
- `--json` flag: output as JSON instead of TOML
- `--path`: show the path(s) config was loaded from
- Useful for debugging "which config is yoker using?"

### 4. `yoker run <source>`

**Purpose**: Load a source (module, GitHub URL, folder, zip) containing an
extended yoker manifest, and run the specified agent with the initial prompt.

**Behavior**:
1. Resolve the source to a loadable plugin (see Source Resolution below)
2. Load the extended manifest from the resolved plugin
3. Read the manifest's `agent` field (which agent to use) and `prompt` field
   (initial prompt to inject)
4. Construct a Session with the resolved plugin loaded
5. Process the initial prompt through the specified agent
6. Exit after the agent completes (non-interactive — one-shot execution)

**CLI flags**:
- `--agent <name>`: override the manifest's agent selection
- `--prompt <text>`: override the manifest's initial prompt
- `--with <package>`: additional plugins (same as chat)
- `--persist`: persist the session (enable context persistence)
- `--session-id <id>`: specify a session ID for persistence

**Output**: The agent's response goes to stdout (batch-style output). In
interactive mode (TTY), streaming output is shown. The process exits after
the agent completes processing the initial prompt.

**Error handling**:
- Source not found → clear error message, exit non-zero
- Manifest missing `agent` or `prompt` → error message listing what's
  missing, exit non-zero
- Agent definition not found in the loaded plugin → error message, exit
  non-zero

### 5. `yoker loop <source> [--interval <seconds>]`

**Purpose**: Run `yoker run` at a specified interval.

**Behavior**:
- Reuses the `yoker run` execution path
- `--interval <seconds>`: time between runs (default: 300 = 5 minutes)
- `--max-iterations <n>`: stop after N iterations (default: unlimited)
- Each iteration creates a fresh session (or persists if `--persist`)
- `--session-id <id>`: reuse the same session across iterations (with
  persistence enabled, the agent retains context between runs)
- Ctrl+C stops the loop cleanly

**Use case**: Periodic agentic tasks — e.g. "check for new issues every 5
minutes and summarize them."

### 6. `yoker inspect <source>`

**Purpose**: Dump a report about a source, explaining what it contains, what
it uses, and what it does — without executing anything.

**Behavior**:
- Resolves the source (same detection as `yoker run`: module, URL, folder, zip)
- Reads the manifest (`agent.toml` or `__YOKER_MANIFEST__`) — metadata only, NO imports
- Displays a human-readable report:
  - **What it contains**: skills (names, descriptions), agent definitions (names, models), tools (names from `tools_module` — listed but NOT imported)
  - **What it uses**: dependencies (from `pyproject.toml` if present), `tools_module` declaration, config overrides from the manifest
  - **What it does**: the `agent` and `prompt` from `[run]`, any config overrides
- No trust gate needed (read-only, no code execution)
- `tools_module` is listed in the report but NOT imported — just shown as a declaration
- For GitHub URLs: clones the repo (same as `run`), reads the manifest, cleans up
- For zip files: extracts to temp dir, reads the manifest, cleans up

**Output**: A formatted report to stdout. Exit after displaying.

**Use case**: Understanding what a source contains before running it. A safe
"what would this do?" preview. Essentially a read-only `--dry-run` that shows
the source's contents without executing anything.

### 7. `yoker container <source>`

**Purpose**: Generate a container setup (Dockerfile, Containerfile) for
running a yoker-based agentic package.

**Behavior**:
- Takes the same source argument as `yoker run`
- Resolves the source and loads the extended manifest
- Generates:
  - A `Dockerfile` (or `Containerfile` with `--engine podman`)
  - A `.containerignore` file
  - An entrypoint script that runs `yoker run <source>`
- `--engine {docker,podman}`: choose container engine (default: docker)
- `--output-dir <path>`: where to write files (default: current directory)
- The generated container runs `yoker run` with the source, making the
  agentic package portable and deployable

**Generated Dockerfile structure**:
```dockerfile
FROM python:3.12-slim
RUN pip install uv yoker
# If source is a module: pip install <module>
# If source is a GitHub URL: clone and install
# If source is a folder/zip: COPY and install
ENTRYPOINT ["yoker", "run", "<source>"]
```

## Extended Manifest Design

### Manifest as a Config-Override Layer (Owner Feedback PR #46)

The owner redefined the manifest from additive fields on `PluginManifest` to
a **generic config-override layer**. The manifest can override ANY `Config`
field, not just `agent` and `prompt`.

**Layering (precedence low to high):**

1. Dataclass defaults
2. User-level TOML (`~/.yoker.toml`)
3. Project-level TOML (`./yoker.toml`)
4. **Manifest overrides** (`<source>/agent.toml`) — NEW layer
5. CLI arguments (highest priority)

### File-Based Manifest: `agent.toml`

The manifest file is named `agent.toml` (not `yoker.toml`) to avoid collision
with the project-level configuration file `yoker.toml`. The owner raised this
explicitly: "for the file-based manifest: don't use yoker.toml, that is
already used for our project-level configuration."

```toml
# agent.toml — source manifest for a yoker-based agentic package

# Run configuration (source-specific)
[run]
agent = "researcher"       # Agent definition to use
prompt = "Analyze the codebase and create a PACKAGE.md"  # Initial prompt

# Plugin configuration (source-specific)
[plugin]
skills_dir = "skills"      # Directory containing skill definitions
agents_dir = "agents"       # Directory containing agent definitions
tools_module = "my_plugin.tools"  # Optional: import tools from this module

# Config overrides (any Config field can be overridden)
[backend.ollama]
model = "llama3.2"         # Use a specific model for this source

[tools.git]
enabled = false            # Disable git tools for this source

[ui]
mode = "batch"             # Force batch mode for non-interactive execution
```

**Parsing rules:**
- `[run]` is optional. Contains `agent` (str) and `prompt` (str).
- `[plugin]` is optional. Contains `skills_dir`, `agents_dir`, `tools_module`.
- All other tables/keys are treated as **config overrides** — merged into the
  base config dict between project TOML and CLI args.
- If `agent.toml` doesn't exist, the source is treated as a plain plugin.

### Python Manifest (`__YOKER_MANIFEST__`)

The Python `__YOKER_MANIFEST__` object continues to declare tools, skills, and
agents. For `yoker run`, the Python manifest's `agent` and `prompt` fields
(optional, default `None`) serve as a fallback when no `agent.toml` exists:

```python
@dataclass
class PluginManifest:
  # Existing fields
  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list[Skill] = field(default_factory=list)
  agents: list[AgentDefinition] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"

  # New: convenience fields for yoker run (fallback when no agent.toml exists)
  agent: str | None = None        # Which agent definition to use
  prompt: str | None = None       # Initial prompt to inject
```

**Precedence for `agent`/`prompt`:**
1. CLI override (`--agent`, `--prompt`) — highest
2. `agent.toml` `[run]` section — if file manifest exists
3. Python `__YOKER_MANIFEST__.agent`/`.prompt` — fallback for packages
4. Error if none of the above provide both `agent` and `prompt`

**Resolution order**: When loading a source, yoker checks:
1. `agent.toml` file in the source root (if the source is a folder/zip)
2. Python `__YOKER_MANIFEST__` (if the source is a Python package)
3. If neither exists, the source is treated as a plain plugin (no run
   configuration — `yoker run` requires at least `prompt` to be set)

## Source Resolution Design

`yoker run <source>` accepts four source types, all resolving to the same
internal representation (a loaded plugin with components + manifest):

### 1. Module Name (e.g., `pkgq`)

- Uses the existing plugin loading infrastructure (`load_plugin(package_name)`)
- The package must be installed (via `uvx --with`, pip, or already available)
- `__YOKER_MANIFEST__` is read from the package
- This is the simplest case — identical to `--with <module>`
- Goes through `check_plugin_allowed()` — same trust gate as `--with`

### 2. GitHub URL (e.g., `https://github.com/christophevg/pkgq`)

- Clones the repository to a temporary directory
- Looks for `agent.toml` in the repo root
- If the repo has an `agent.toml`, loads from the folder path (see #3)
- If the repo is a Python package (has `pyproject.toml` or `setup.py`),
  does NOT auto-install it (see "pyproject.toml auto-install" below)
- Cleans up the temporary directory on exit
- Goes through `check_plugin_allowed()` — same trust gate as `--with`

### 3. Folder Path (e.g., `./my-agent`)

- Looks for `agent.toml` in the folder root
- Loads skills from `<folder>/<skills_dir>` (default: `skills/`)
- Loads agent definitions from `<folder>/<agents_dir>` (default: `agents/`)
- If `tools_module` is specified in the manifest, imports that module and
  loads tools from it (ONLY after passing the trust gate)
- Does NOT auto-install `pyproject.toml` if present (deferred to future MBI;
  requires explicit `--install` flag)
- Goes through `check_plugin_allowed()` — same trust gate as `--with`

### 4. Zip File (e.g., `./my-agent.zip`)

- Extracts to a temporary directory
- Proceeds as folder path (#3)
- Cleans up on exit
- Goes through `check_plugin_allowed()` — same trust gate as `--with`

### Trust Gate (Owner Feedback PR #46)

The owner confirmed: "Currently when issuing `--with <pkg>` we don't consider
this an explicit opt-in. So, I wouldn't change that behaviour. Let's keep
these guardrails in place and reuse them, not creating parallel tracks."

`yoker run <source>` goes through the same `check_plugin_allowed()` trust
gate as `--with <source>`. No bypass for named sources. The source must be
either in `[plugins.trusted]`, confirmed interactively, or rejected in
non-interactive mode.

### `yoker inspect <source>` — No Trust Gate

`yoker inspect` is read-only: it resolves the source, reads the manifest, and
displays a report. It does NOT import `tools_module`, does NOT execute any
code. Only the manifest metadata is read. No trust gate needed.

### "Defer auto-installing pyproject.toml" — Clarified (Owner Feedback PR #46)

The owner asked "what do you mean by this?" when the API architect recommended
deferring auto-installation of a folder's `pyproject.toml`. Here is the
clarification:

When loading a folder source that contains a `pyproject.toml`, the question
is whether to automatically `pip install` it. Auto-installing runs build
hooks (setup.py, PEP 517 build backend) — this is **arbitrary code execution**
(CWE-494). A malicious `pyproject.toml` could run arbitrary code during the
build step, before any trust gate could intervene.

The recommendation is to **NOT auto-install by default**. For MBI-004,
folder/zip sources load via the file manifest (`agent.toml`) + `tools_module`
import; full package installation requires an explicit `--install` flag
(deferred to a future MBI). If a folder has a `pyproject.toml` but no
`agent.toml`, yoker does not install it — it either loads from the folder
structure directly or errors with a message explaining that `--install` is
needed (future MBI).

### Resolution Function

```python
def resolve_source(source: str) -> ResolvedSource:
  """Resolve a source string to a loadable plugin.

  Detects source type:
  - Starts with 'http://' or 'https://' → GitHub URL
  - Ends with '.zip' → Zip file
  - Path exists and is a directory → Folder path
  - Otherwise → Module name (installed Python package)

  Returns a ResolvedSource containing:
  - plugin_components: PluginComponents (tools, skills, agents)
  - manifest: Extended PluginManifest (with agent + prompt)
  - cleanup: Optional callable to clean up temp files
  """
```

## Dependency Graph

```
4.1 (CLI subcommands via Clevis) ──► 4.2 (chat) ──► 4.3 (init)
                   │
                   ├──► 4.4 (config)
                   │
                   ├──► 4.12 (inspect) ◄── 4.6 (source resolution)
                   │
                   └──► 4.7 (run) ◄── 4.5 (manifest as config-override)
                                  ◄── 4.6 (source resolution)
                                       │
                                       ▼
                                    4.8 (loop)
                                       │
                                       ▼
                                    4.9 (container)
                                       │
                                       ▼
                              4.10 (tests)
                                       │
                                       ▼
                              4.11 (docs)
```

## Edge Cases and Considerations

1. **Backward compatibility**: `yoker` with no subcommand must still work
   as before (default to `chat`). Existing scripts and muscle memory are
   preserved.

2. **`yoker run` without manifest**: If a source has no extended manifest
   fields (`agent`/`prompt`), `yoker run` should error with a clear message.
   The source is loadable as a plugin, but not runnable as an agentic
   executable without knowing which agent to use and what prompt to send.

3. **`yoker run` with CLI overrides**: `--agent` and `--prompt` flags
   override the manifest's fields. This lets users run any plugin with a
   custom prompt without modifying the manifest.

4. **GitHub URL authentication**: Private repos require authentication.
   Use `git clone` which respects SSH keys and git credential helpers.
   No yoker-specific auth needed.

5. **Zip file security**: Zip extraction should use safe extraction
   (prevent path traversal via `..` entries). Use
   `zipfile.is_zipfile()` validation and check each entry path.

6. **Temp directory cleanup**: GitHub URL clones and zip extractions use
   temporary directories that must be cleaned up via `try/finally` or
   context managers, even on error/exit.

7. **`yoker loop` and session persistence**: With `--persist` and a fixed
   `--session-id`, the agent retains context across loop iterations. Without
   persistence, each iteration is a fresh start.

8. **`yoker container` and source embedding**: The generated Dockerfile
   should handle each source type appropriately:
   - Module: `pip install <module>`
   - GitHub URL: `git clone` in the build step
   - Folder: `COPY` the folder into the image
   - Zip: `COPY` and extract in the build step

9. **File-based manifest security**: `agent.toml` is a manifest file that
   can declare a `tools_module` field. When `tools_module` is specified,
   the manifest triggers `importlib.import_module()` of a Python module
   within the source — this is **code execution**, not pure configuration.
   It must pass the same trust gate as `--with <package>`
   (`check_plugin_allowed()`) before the import happens. Manifests without
   `tools_module` are config-only and represent a lower trust tier. The
   config override sections of `agent.toml` (anything outside `[run]` and
   `[plugin]`) are pure configuration — they override Config fields but do
   not execute code.

10. **Config precedence for `yoker run`**: The base config loads from
    `~/.yoker.toml` and `./yoker.toml` (for backend settings etc.). The
    source's `agent.toml` provides config overrides on top of the base config.
    CLI flags override both. Full layering: defaults -> user TOML -> project
    TOML -> manifest overrides -> CLI args.

11. **`yoker inspect` is safe without trust**: Inspect reads the manifest
    metadata only. It does NOT import `tools_module`, does NOT execute any
    code, and does NOT call `load_source()`. The `tools_module` is listed
    in the report but NOT imported. This makes inspect safe to run on
    untrusted sources — it's a "what would this do?" preview.

12. **Agent name resolution (owner confirmed)**: source-based named items
    override existing ones. The manifest's `agent` name resolves against
    the source's own agent definitions first, then the built-in registry.
    On conflict, source wins. (The owner noted: "given namespacing, I don't
    expect that to happen quickly.")