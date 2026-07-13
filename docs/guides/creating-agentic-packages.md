# Creating Agentic Packages

A yoker agentic package is a source (Python module, GitHub repository, local
folder, or zip file) that contains an `agent.toml` manifest declaring which
agent to use and what initial prompt to send. The package is run with
`yoker run <source>`, which loads the source, applies the manifest, and
executes the agent non-interactively.

This guide covers the `agent.toml` manifest format, the two manifest types
(file-based and Python-based), the configuration override layer, and the trust
model.

## The `agent.toml` Manifest

The manifest lives in the **source root** (the top-level directory of the
folder, GitHub repo, or zip file) and is named `agent.toml` — not `yoker.toml`
— to avoid collision with the project-level configuration file.

It has three parts:

### `[run]` — Source-Specific Run Config

Specifies which agent definition to use and what initial prompt to send.

```toml
[run]
agent = "researcher"
prompt = "Analyze the codebase and identify potential improvements."
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent` | string | none | Agent definition name to use |
| `prompt` | string | none | Initial prompt for the agent |

Both fields are optional. If neither is set, you must provide `--agent` and
`--prompt` on the command line. The prompt is capped at 10 KB.

### `[plugin]` — Source-Specific Plugin Config

Declares where skills, agent definitions, and tools are located within the
source.

```toml
[plugin]
skills_dir = "skills"
agents_dir = "agents"
tools_module = "my_plugin.tools"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `skills_dir` | string | `"skills"` | Directory containing skill definition files |
| `agents_dir` | string | `"agents"` | Directory containing agent definition files |
| `tools_module` | string | none | Python module to import tools from (dotted name) |

The `tools_module` is imported only after the source passes the trust gate.
It must be a dotted Python module name (e.g. `my_plugin.tools`), not a
filesystem path. The module can expose tools via `__YOKER_TOOLS__` (a list of
callables) or a `tools` list attribute.

Path traversal is blocked: `skills_dir` and `agents_dir` must be relative
paths that stay within the source root. Absolute paths and `..` components
are rejected.

### Config Overrides — Any Other Tables

All tables and keys outside `[run]` and `[plugin]` are treated as **config
overrides** — any `Config` field can be overridden. These overrides are
deep-merged into the base configuration between the project TOML and CLI
arguments.

```toml
[run]
agent = "researcher"
prompt = "Analyze the codebase."

[plugin]
tools_module = "my_plugin.tools"

# Config overrides — any Config field can be set here.
[backend.ollama]
model = "qwen3.5:cloud"

[tools.git]
enabled = false
```

## Configuration Cascade

The full priority order (lowest to highest):

1. **Dataclass defaults** — built-in defaults from the `Config` dataclass
2. **User TOML** — `~/.yoker.toml`
3. **Project TOML** — `./yoker.toml`
4. **Manifest overrides** — `<source>/agent.toml` (this layer)
5. **CLI arguments** — `yoker run --backend-ollama-model X` (highest priority)

Nested table overrides are deep-merged (e.g. `[backend.ollama] model = "X"`
merges into the existing `[backend.ollama]` table). TOML arrays replace
tuple-typed fields entirely.

## Python-Based Manifest (Alternative)

For Python packages that export `__YOKER_MANIFEST__`, the `PluginManifest`
dataclass has two convenience fields that serve as fallbacks when no
`agent.toml` is present:

```python
# In my_package/yoker/__init__.py
from yoker.plugins import PluginManifest

__YOKER_MANIFEST__ = PluginManifest(
  tools=[my_tool],
  skills_dir="skills",
  agents_dir="agents",
  agent="researcher",     # convenience fallback
  prompt="Analyze the codebase.",  # convenience fallback
)
```

When both a Python manifest and an `agent.toml` file exist, the `agent.toml`
takes precedence for `agent` and `prompt` values.

## Source Types

`yoker run` accepts four source types, auto-detected from the input string:

| Source type | Example | Detection |
|-------------|---------|-----------|
| Module | `pkgq` | Fallback (not a URL, zip, or folder) |
| GitHub URL | `https://github.com/owner/repo` | Starts with `http://` or `https://` |
| Folder | `./my-folder` | `Path(source).is_dir()` is true |
| Zip file | `./my-package.zip` | Ends with `.zip` and is a file |

### GitHub URLs

GitHub URLs are cloned with `git clone --depth 1` to a secure temp directory.
The URL must use HTTPS (`http://`, `git://`, `ssh://`, `file://` are rejected).
Embedded credentials (`https://user:pass@...`) are rejected. An SSRF check
blocks private IPs and cloud metadata endpoints. The resolved commit SHA is
recorded for audit and reproducibility.

### Zip Files

Zip files are extracted to a secure temp directory with path-traversal,
symlink, and zip-bomb defenses: absolute paths, `..` entries, and symlink
entries are rejected. Max total uncompressed size is 100 MB, max entries is
10,000, and max compression ratio is 100:1.

## Trust Model

Sources must pass the **trust gate** before any code is executed. This is a
security invariant: the two-phase design ensures that `resolve_source()`
(phase 1 — metadata only, no imports) runs first, and `load_source()` (phase 2
— imports, code execution) is called only after the trust gate passes.

The trust gate uses your own config, not the source's manifest overrides, so a
source cannot influence its own trust decision.

### Trusting a Source

Add the source's trust key to your `yoker.toml`:

```toml
[plugins]
enabled = true

[plugins.trusted]
pkgq = true                                    # module
"github:owner/repo@abc1234" = true              # GitHub (with SHA)
"folder:/abs/path/to/folder" = true             # folder
"zip:abc123...def456" = true                    # zip (SHA-256 of file)
```

To find the trust key for a source, run `yoker inspect <source>` — it prints
the trust key in the report. You can also run `yoker run <source> --dry-run`
to see the trust key without executing the source.

### Inspecting Before Trusting

`yoker inspect <source>` is safe to run on untrusted sources. It resolves the
source (phase 1 only — metadata, no imports, no code execution) and displays a
read-only report. For module sources, the Python `__YOKER_MANIFEST__` cannot
be discovered without importing the package, so the report notes that trust is
required to inspect it further.

## Example: A Minimal Agentic Package

Create a folder with this structure:

```
my-package/
  agent.toml
  agents/
    researcher.md
  skills/
    analyze/
      SKILL.md
```

`agent.toml`:

```toml
[run]
agent = "researcher"
prompt = "Analyze the project structure and suggest improvements."

[plugin]
skills_dir = "skills"
agents_dir = "agents"
```

`agents/researcher.md`:

```markdown
---
name: researcher
description: A research agent that analyzes code and suggests improvements
tools:
  - read
  - list
  - search
---

You are a research agent. Analyze the given codebase and provide
actionable improvement suggestions.
```

Run it:

```bash
yoker run ./my-package
```

Or from GitHub:

```bash
# Push to GitHub, then:
yoker run https://github.com/you/my-package
```

## Example: A Python Package with `agent.toml`

For Python packages that are installable via `pip`, the `agent.toml` provides
the run config while the Python manifest provides tools:

```
my-pkg/
  pyproject.toml
  agent.toml
  my_pkg/
    __init__.py          # exports __YOKER_MANIFEST__
    tools.py             # tool functions
    agents/
      researcher.md
```

`agent.toml`:

```toml
[run]
agent = "researcher"
prompt = "Find and document all public APIs."

[plugin]
tools_module = "my_pkg.tools"
agents_dir = "my_pkg/agents"
```

`my_pkg/__init__.py`:

```python
from yoker.plugins import PluginManifest
from my_pkg.tools import find_apis, document_api

__YOKER_MANIFEST__ = PluginManifest(
  tools=[find_apis, document_api],
)
```

Run it:

```bash
pip install my-pkg
yoker run my-pkg
```