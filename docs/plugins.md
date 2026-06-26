# Using Plugins

Yoker can load tools, skills, and agents from external Python packages via the plugin system. This guide covers the complete workflow for using plugins safely.

## Overview

Plugins extend Yoker's capabilities by providing:

- **Tools** - New functions the agent can call
- **Skills** - Predefined prompts loaded via `/skill` commands
- **Agents** - Custom agent definitions

Plugins are Python packages that declare their components through a `__YOKER_MANIFEST__` object. When you load a plugin with `--with`, Yoker discovers and registers all components the package provides.

## Enabling Plugins

**Important**: Plugins are disabled by default for security. You must explicitly enable them in your configuration.

### Step 1: Create or Update Configuration

Create a `yoker.toml` file in your project directory or home directory:

```toml
[plugins]
enabled = true
```

Without this configuration, attempting to load a plugin will show:

```
Error: Plugins are disabled. To enable, add to your config:

  [plugins]
  enabled = true
```

### Step 2: Secure File Permissions

Yoker requires configuration files to be readable only by the owner (mode `600`). This prevents other users on shared systems from reading sensitive configuration.

If your configuration file has incorrect permissions, you'll see:

```
Error: Configuration file /Users/you/yoker.toml is readable by group/other (mode 0o644). Use 'chmod 600 /Users/you/yoker.toml' to fix.
```

Fix it with:

```bash
chmod 600 yoker.toml
# or for home directory config
chmod 600 ~/.yoker.toml
```

## Loading Plugins

### Basic Usage

Install the plugin package (if not already installed), then run Yoker with `--with`:

```bash
# Using uvx (recommended for one-time use)
uvx --with pkgq yoker --with pkgq

# Or install first, then run
pip install pkgq
python -m yoker --with pkgq
```

### Multiple Plugins

Load multiple plugins by repeating the `--with` argument:

```bash
python -m yoker --with plugin-one --with plugin-two --with plugin-three
```

### Plugin Confirmation Dialog

When you load a plugin for the first time, Yoker displays a confirmation dialog:

```
╭─────────────────────────────────────────────── Plugin: pkgq ───────────────────────────────────────────────╮
│ Plugin: pkgq                                                                                               │
│                                                                                                            │
│ Tools:     pkgq:find                                                                                       │
│ Skills:    pkgq:create, pkgq:update                                                                        │
│ Agents:    (none)                                                                                          │
│                                                                                                            │
│ Plugins can execute code on your system.                                                                   │
│ Only load plugins you trust.                                                                               │
│                                                                                                            │
│ Load this plugin? [y/N]:                                                                                   │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**Important**: Plugins can execute arbitrary code on your system. Only load plugins from sources you trust.

Type `y` and press Enter to load the plugin, or `N` (or just Enter) to decline.

### Trusting Plugins Permanently

After accepting a plugin, Yoker shows how to trust it permanently:

```
To trust this plugin permanently, add to your yoker.toml:

  [plugins.trusted]
  pkgq = true
```

Add this to your configuration file to skip the confirmation dialog in future sessions:

```toml
[plugins]
enabled = true

[plugins.trusted]
pkgq = true
another-plugin = true
```

## Verifying Loaded Components

After Yoker starts, verify that plugin components are available.

### Check Skills

Use the `/skills` command to see all loaded skills, including those from plugins:

```
> /skills
Loaded skills:

From plugins:
  ✓ pkgq:create          - Generate a PACKAGE.md file for a Python project. Analyzes the project structure,
extracts key components, patterns, and creates agent-ready documentation.
Use when creating documentation for your own packages. (pkgq)
  ✓ pkgq:update          - Update existing package documentation for a new version.
Fetches changelog, extracts changes, and updates PACKAGE.md and HISTORY.md.
Use when planning upgrades or when new versions are released. (pkgq)

All loaded skills are available to the agent.
```

### Check Tools

Use the `/tools` command to see all available tools:

```
> /tools
Known tools:

Built-in:
  ✗ yoker:existence - Check if a file or folder exists at the given path.
  ✗ yoker:git       - Execute a Git operation on a repository.
  ✗ yoker:list      - List files and directories.
  ✗ yoker:mkdir     - Create a directory at the given path.
  ✗ yoker:read      - Read the contents of a file.
  ✗ yoker:search    - Search for patterns in files.
  ✗ yoker:skill     - Invoke a skill by name to get its full instructions.
  ✗ yoker:update    - Update an existing file by replacing, inserting, or delet...
  ✗ yoker:write     - Write content to a file.

Plugins:
  ✗ pkgq:find       - Find Python package documentation.

Agent: default
  Allowed tools:

>
```

### Using Plugin Skills

Invoke plugin skills by name with the `/` prefix:

```
> /pkgq:create
```

Or ask the agent to use a plugin tool:

```
> Use the pkgq:find tool to look up documentation for requests
```

## Security Best Practices

### 1. Review Plugin Components

Before loading a plugin, review what it provides (shown in the confirmation dialog). Tools can execute arbitrary code, so understand what each tool does.

### 2. Trust Selectively

Only trust plugins from reputable sources. Check the plugin's:

- Source code repository
- Documentation
- Changelog
- Security policy

### 3. Use Per-Project Configuration

Create project-specific `yoker.toml` files rather than trusting all plugins globally:

```bash
# Project-specific config
./my-project/yoker.toml

# Home config for trusted plugins only
~/.yoker.toml
```

### 4. Audit Regularly

Review your trusted plugins periodically:

```bash
# Check your trusted plugins
cat ~/.yoker.toml | grep -A 10 "\[plugins.trusted\]"
```

## Configuration Reference

### Plugin Settings

```toml
[plugins]
enabled = true  # Required to load any plugins

[plugins.trusted]
# List of plugins that don't require confirmation
plugin-name = true
another-plugin = true
```

### Configuration File Locations

Yoker searches for configuration files in this order:

1. `./yoker.toml` - Current directory (highest priority)
2. `~/.yoker.toml` - User home directory
3. Built-in defaults

Use the project-local config for project-specific plugins, and the home config for plugins you use across all projects.

## Example: Using pkgq Plugin

The `pkgq` package is the first PyPI-published Yoker plugin. Here's the complete workflow:

### Install and Run

```bash
# One-time use with uvx
uvx --with pkgq yoker --with pkgq

# Or install first
pip install pkgq
python -m yoker --with pkgq
```

### First-Time Setup

1. **Enable plugins** in `yoker.toml`:

   ```toml
   [plugins]
   enabled = true
   ```

2. **Secure the file**:

   ```bash
   chmod 600 yoker.toml
   ```

3. **Load the plugin** and accept the confirmation dialog

4. **Trust permanently** (optional):

   ```toml
   [plugins.trusted]
   pkgq = true
   ```

### Available Components

After loading, `pkgq` provides:

- **Tool**: `pkgq:find` - Find Python package documentation
- **Skills**:
  - `pkgq:create` - Generate PACKAGE.md for a project
  - `pkgq:update` - Update package documentation for new versions

### Usage Examples

```
# Use the skill directly
> /pkgq:create

# Ask the agent to use the tool
> Use pkgq:find to get documentation for the requests library

# Update documentation for a new version
> /pkgq:update
```

## Developing Plugins

For information on creating your own plugins, see:

- `examples/plugins/demo/README.md` - Complete plugin development guide
- `examples/plugins/demo/` - Reference implementation

### Plugin Manifest Structure

Plugins declare components through a `PluginManifest` instance in their `__init__.py`:

```python
from yoker.plugins import PluginManifest

from .tools import echo

__YOKER_MANIFEST__ = PluginManifest(
  tools=[echo],
  skills_dir="skills",
  agents_dir="agents",
)
```

### PluginManifest Attributes

- `tools: list[Callable]` - List of functions or callable classes provided by the plugin
- `skills: list[Skill]` - List of Skill instances (or use `skills_dir` for auto-discovery)
- `agents: list[AgentDefinition]` - List of AgentDefinition instances (or use `agents_dir` for auto-discovery)
- `config_class: type | None` - Optional configuration class for plugin tools
- `skills_dir: str` - Directory name for skill files (default: "skills")
- `agents_dir: str` - Directory name for agent files (default: "agents")

### Component Discovery

When using `skills_dir` or `agents_dir`, Yoker automatically discovers:

- **Skills**: Markdown files named `SKILL.md` in `skills_dir` subdirectories
- **Agents**: Markdown files with `.md` extension in `agents_dir`

See the demo plugin at `examples/plugins/demo/` for a complete reference implementation.

## Troubleshooting

### Plugin Not Found

```
Error: Plugin 'plugin-name' not found
```

**Solution**: Install the plugin package before loading it:

```bash
pip install plugin-name
# or with uvx
uvx --with plugin-name yoker --with plugin-name
```

### Permission Denied on Config

```
Error: Configuration file is readable by group/other
```

**Solution**: Fix permissions:

```bash
chmod 600 yoker.toml
# or
chmod 600 ~/.yoker.toml
```

### Plugin Disabled

```
Error: Plugins are disabled
```

**Solution**: Enable plugins in your configuration:

```toml
[plugins]
enabled = true
```

### Trusted Plugin Not Loading

If a plugin you've trusted isn't loading:

1. **Check configuration location**: Ensure you're using the correct config file (project vs. home)
2. **Verify plugin installation**: `pip list | grep plugin-name`
3. **Check manifest**: The plugin must declare `__YOKER_MANIFEST__` in `__init__.py`

## Summary

The plugin workflow follows these steps:

1. **Enable plugins** in `yoker.toml` (`[plugins] enabled = true`)
2. **Secure configuration** with `chmod 600 yoker.toml`
3. **Load plugin** with `--with package-name`
4. **Review and accept** the confirmation dialog
5. **Trust permanently** (optional) in `[plugins.trusted]`
6. **Verify components** with `/skills` and `/tools`
7. **Use plugin** skills and tools in your session

Plugins extend Yoker's capabilities while maintaining security through explicit enablement and trust management. Always review plugin components before loading them, and only trust plugins from sources you trust.