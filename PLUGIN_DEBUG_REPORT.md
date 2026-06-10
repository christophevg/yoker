# Plugin Loading Debug Report

## Summary

The demo plugin infrastructure is working correctly. The debug output shows successful plugin loading with all components (tools, skills, agents) being properly discovered and registered.

## Issue Encountered

When running `yoker --with examples.plugins.demo`, the plugin failed to load because:

1. **Package Path Issue**: The `examples` directory is not a Python package in the import path
2. **Import Error**: Python could not import `examples.plugins.demo` because `examples` is not configured as an installable package

## Solution

The plugin requires `examples` to be in the Python path. Two approaches:

### Approach 1: Use PYTHONPATH (Recommended for development)

```bash
export PYTHONPATH=/Users/xtof/Workspace/agentic/yoker/examples:$PYTHONPATH
uv run yoker --with plugins.demo
```

Or use the provided script:
```bash
./run_with_demo_plugin.sh
```

### Approach 2: Install examples as a package (For production)

Add to `pyproject.toml`:
```toml
[tool.setuptools.packages]
packages = ["src/yoker", "examples"]
```

Then use:
```bash
uv run yoker --with plugins.demo
```

## Debug Output Analysis

### Successful Loading Process

When run with proper PYTHONPATH, the debug logs show:

```
[info] plugin_module_imported         package=plugins.demo
[info] plugin_components_extracted_initial tools_count=1 skills_count=0 agents_count=0
[info] plugin_manifest_found          has_manifest=True has_tools=1
[info] plugin_manifest_found          skills_dir=skills agents_dir=agents

# Skill Discovery
[info] loading_skills_from_dir        skills_dir=skills
[info] nested_skill_file_found        file=SKILL.md directory=greeting
[info] nested_skill_loaded            full_name=plugins.demo:greeting

# Agent Discovery
[info] loading_agents_from_dir        agents_dir=agents
[info] agents_discovered_from_dir     agent_names=['plugins.demo:demo']

# Final Count
[info] plugin_components_extracted    tools=1 skills=1 agents=1
```

### Components Loaded

1. **Tool**: `echo` → registered as `plugins.demo:echo`
   - EchoTool implementation
   - Returns input message with "Echo: " prefix

2. **Skill**: `greeting` → registered as `plugins.demo:greeting`
   - Located in `plugins.demo/yoker/skills/greeting/SKILL.md`
   - Loaded from nested skill directory structure

3. **Agent**: `demo` → registered as `plugins.demo:demo`
   - Located in `plugins.demo/agents/demo.md`
   - Agent definition with custom configuration

## Plugin Structure

```
examples/plugins/demo/
├── __init__.py              # Package marker with __YOKER_MANIFEST__
├── yoker/
│   ├── __init__.py          # Plugin manifest (alternative location)
│   └── tools.py             # EchoTool implementation
├── skills/
│   └── greeting/
│       └── SKILL.md         # Greeting skill definition
└── agents/
    └── demo.md              # Demo agent definition
```

## Registration Flow

1. **Tool Registration**:
   ```python
   register_tools(plugin.tools, tool_registry, namespace="plugins.demo")
   # Result: plugins.demo:echo
   ```

2. **Skill Registration**:
   ```python
   register_skills(plugin.skills, skill_registry, namespace="plugins.demo")
   # Result: plugins.demo:greeting
   ```

3. **Agent Registration**:
   ```python
   register_agents(plugin.agents, namespace="plugins.demo")
   # Result: plugins.demo:demo
   ```

## Key Findings

1. **Manifest Discovery**: The loader successfully finds `__YOKER_MANIFEST__` in the package's `__init__.py`

2. **Skill Directory Loading**: Skills are correctly loaded from `yoker/skills/` subdirectory using the nested structure (skill name/SKILL.md)

3. **Agent Loading**: Agents are properly loaded from the `agents/` directory

4. **Namespace Prefixing**: All components are correctly namespaced with the package name

## Recommendations

1. **Documentation Update**: The README should clarify:
   - Use package name `plugins.demo` (not `examples.plugins.demo`)
   - Ensure `examples` is in PYTHONPATH or installed as package
   - Provide the helper script for easy testing

2. **Plugin Discovery**: Consider adding plugin discovery from:
   - `~/.yoker/plugins/`
   - `./plugins/` (project-local)
   - Environment variable `YOKER_PLUGIN_PATH`

3. **Error Messages**: Improve error messages when plugin cannot be imported to suggest checking PYTHONPATH

## Test Verification

Run the test script to verify:
```bash
uv run python test_plugin_loading.py
```

Expected output shows:
- ✓ Plugin loaded successfully
- 1 tool, 1 skill, 1 agent discovered
- All components properly registered with namespace

## Next Steps

For the user to run yoker with the demo plugin:

```bash
# Option 1: Use the helper script
./run_with_demo_plugin.sh

# Option 2: Set PYTHONPATH manually
export PYTHONPATH=/Users/xtof/Workspace/agentic/yoker/examples:$PYTHONPATH
uv run yoker --with plugins.demo

# Inside yoker, type /skills to see:
#   - example: A simple example skill for demonstration
#   - sing: Use this skill when asked to sing or reply with a song.
```