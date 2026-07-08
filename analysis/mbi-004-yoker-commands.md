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

### 6. `yoker container <source>`

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

### Current PluginManifest

```python
@dataclass
class PluginManifest:
  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list[Skill] = field(default_factory=list)
  agents: list[AgentDefinition] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"
```

### Extended PluginManifest

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

  # New fields for yoker run
  agent: str | None = None        # Which agent definition to use
  prompt: str | None = None       # Initial prompt to inject
```

**Rationale**: `agent` specifies which agent definition (from the plugin's
own agents or the built-in agents) to use for this run. `prompt` is the
initial prompt that gets processed immediately. Together they make a plugin
into an "agentic executable package" — running `yoker run <package>` executes
the agent with the prompt, no interactive input needed.

### File-Based Manifest

Currently, manifests are Python objects (`__YOKER_MANIFEST__` in a package's
`__init__.py`). For folder/zip sources that aren't Python packages, we need
a file-based manifest.

**Format**: `yoker.toml` (or `yoker-manifest.toml`) in the source root.

```toml
# yoker.toml — file-based yoker manifest

[run]
agent = "researcher"       # Agent definition to use
prompt = "Analyze the codebase and create a PACKAGE.md"  # Initial prompt

[plugin]
skills_dir = "skills"      # Directory containing skill definitions
agents_dir = "agents"       # Directory containing agent definitions
# tools are Python callables — file-based manifest cannot declare tools
# directly; instead, a companion Python module can be specified:
tools_module = "my_plugin.tools"  # Optional: import tools from this module
```

**Resolution order**: When loading a source, yoker checks:
1. Python `__YOKER_MANIFEST__` (if the source is a Python package)
2. `yoker.toml` file in the source root (if the source is a folder/zip)
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

### 2. GitHub URL (e.g., `https://github.com/christophevg/pkgq`)

- Clones the repository to a temporary directory
- Looks for `yoker.toml` in the repo root
- If the repo is a Python package (has `pyproject.toml` or `setup.py`),
  installs it into a temporary virtualenv and loads it as a module
- If the repo has a `yoker.toml` but no package structure, loads from the
  folder path (see #3)
- Cleans up the temporary directory on exit

### 3. Folder Path (e.g., `./my-agent`)

- Looks for `yoker.toml` in the folder root
- Loads skills from `<folder>/<skills_dir>` (default: `skills/`)
- Loads agent definitions from `<folder>/<agents_dir>` (default: `agents/`)
- If `tools_module` is specified in the manifest, imports that module and
  loads tools from it
- If the folder contains a Python package (`pyproject.toml`), installs it
  and loads as a module

### 4. Zip File (e.g., `./my-agent.zip`)

- Extracts to a temporary directory
- Proceeds as folder path (#3)
- Cleans up on exit

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
4.1 (CLI dispatcher) ──► 4.2 (chat) ──► 4.3 (init)
                   │
                   ├──► 4.4 (config)
                   │
                   └──► 4.7 (run) ◄── 4.5 (extended manifest)
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

9. **File-based manifest security**: `yoker.toml` is trusted the same way
   `~/.yoker.toml` is trusted — it's a configuration file, not code.
   The `tools_module` field imports Python code, which is the same trust
   model as `--with <package>` (the user explicitly chose to load it).

10. **Config precedence for `yoker run`**: The base config still loads from
    `~/.yoker.toml` (for backend settings etc.), and the source's manifest
    adds agent + prompt on top. CLI flags override both.