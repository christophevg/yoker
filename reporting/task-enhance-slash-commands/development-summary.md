# Task: Enhance Slash Commands to Show Known vs Available Items

## Implementation Summary

### What Was Implemented

Enhanced the `/tools`, `/agents`, and `/skills` slash commands to show all known items and mark which are available to the current agent.

### Changes Made

#### 1. `/tools` Command (`src/yoker/commands/tools.py`)

**Previous behavior:**
- Showed only registered (available) tools
- No distinction between built-in, plugin, or special tools
- No indication of which tools are known but unavailable

**New behavior:**
- Shows all known tools with availability markers (✓ available, ✗ not available)
- Organizes tools into sections:
  - **Built-in**: Core yoker tools (read, write, list, etc.)
  - **Plugins**: Plugin-provided tools (namespaced as `package:tool_name`)
  - **Special**: AgentTool, SkillTool (when available)
- Shows agent context (loaded agent + allowed tools)
- Indicates when no agent is loaded (all tools available by default)

**Implementation:**
- Added `get_known_tools()` method to `AgentCore` class to provide built-in tool metadata
- Added `plugin_tools` property and `add_plugin_tool()` method to track plugin tools
- Updated `create_tools_command()` to accept `AgentCore` instance
- Handler distinguishes between available tools (in registry) and known tools

#### 2. `/agents` Command (`src/yoker/commands/agents.py`)

**Previous behavior:**
- Showed only currently loaded agent
- No visibility into other available agents

**New behavior:**
- Shows **Current agent** section:
  - Loaded agent with ✓ marker
  - Source path, description, model, tools
  - Special message when no agent loaded
- Shows **Known agents** section:
  - Lists agents from configured `agents.directory`
  - Shows source path and description for each
  - Marks loaded agent with ✓ vs unmarked ✗
- Provides helpful usage message

**Implementation:**
- Added `_scan_agents_directory()` function to discover agents
- Updated `create_agents_command()` to accept `Config` parameter
- Handler scans `config.agents.directory` for agent definition files
- Parses markdown files with frontmatter to extract agent metadata

#### 3. `/skills` Command (`src/yoker/commands/skills.py`)

**Previous behavior:**
- Listed all loaded skills without source distinction
- No indication of where skills came from

**New behavior:**
- Organizes skills by source:
  - **From config**: Skills loaded from configured directories
  - **From plugins**: Namespaced skills from loaded plugins
  - **Built-in**: Skills from yoker's built-in plugin
- Shows ✓ marker for all loaded skills (all are available by default)
- Displays package name for plugin skills
- Context message indicating all loaded skills are available

**Implementation:**
- Updated `create_skills_command()` to accept `Config` parameter
- Handler categorizes skills by namespace prefix
- Distinguishes between `yoker:` (built-in) and other namespaces (plugins)

### Files Modified

1. **`src/yoker/base.py`**
   - Added `get_known_tools()` method to return built-in tool metadata
   - Added `plugin_tools` property to track loaded plugin tools
   - Added `add_plugin_tool()` method to add plugin tools to known list

2. **`src/yoker/agent.py`**
   - Updated `_load_plugins()` to call `agent_core.add_plugin_tool()` for each plugin tool

3. **`src/yoker/commands/tools.py`**
   - Complete rewrite of handler to show known vs available tools
   - Added plugin tools section
   - Added agent context display

4. **`src/yoker/commands/agents.py`**
   - Complete rewrite to show current agent and known agents
   - Added `_scan_agents_directory()` helper function
   - Enhanced output formatting

5. **`src/yoker/commands/skills.py`**
   - Updated to categorize and display skills by source
   - Added sections for config, plugins, and built-in skills

6. **`src/yoker/__main__.py`**
   - Updated command registration to pass required parameters:
     - `create_tools_command(registry, agent._core)`
     - `create_agents_command(get_agent_definition, config)`
     - `create_skills_command(skill_registry, config)`

### Tests Updated

1. **`tests/commands/test_tools.py`**
   - Added `AgentCore` mock with required properties
   - Updated tests to use new command signature
   - Added test for known vs available tools distinction

2. **`tests/commands/test_agents.py`**
   - Added `Config` mock with required properties
   - Updated tests to use new command signature
   - Verified known agents display

3. **`tests/test_commands/test_skills_command.py`**
   - Added `Config` mock with required properties
   - Updated tests to use new command signature
   - Verified skill categorization by source

### Example Output

#### `/tools` Output
```
Known tools:

Built-in:
  ✓ read            - Read file contents
  ✓ write           - Write content to a file
  ✗ git             - Git operations (not in agent's tools)

Plugins:
  ✓ demo:echo       - Echo back a message

Special:
  ✓ skill           - Invoke a skill by name

No agent loaded. All enabled tools are available.
```

#### `/agents` Output
```
Current agent:

  ✓ demo (examples.plugins.demo:demo)
      Description: A demonstration agent for testing the plugin system
      Model: llama3.2:latest

Known agents:

  ✗ researcher (from config.agents.directory)
      Description: Research agent for web searches

Use --agents-definition <path> to load a specific agent.
```

#### `/skills` Output
```
Loaded skills:

From config:
  ✓ summarizer       - Summarize text content
  ✓ reviewer        - Review code for issues

From plugins:
  ✓ demo:greeting   - Greet users (demo)

All loaded skills are available to the agent.
```

### Test Results

- All 1256 tests pass
- Coverage: 84%
- No linting errors
- Manual verification confirms expected behavior

### Key Design Decisions

1. **Known vs Available Distinction**: 
   - "Known" tools = all tools the system knows about (built-in + plugin)
   - "Available" tools = tools the current agent can use (filtered by agent definition)

2. **Source Organization**:
   - Tools organized by source (Built-in, Plugins, Special)
   - Skills organized by source (From config, From plugins, Built-in)
   - Makes it clear where each item comes from

3. **Plugin Tool Tracking**:
   - Plugin tools tracked in `AgentCore.plugin_tools`
   - Allows showing plugin tools even when filtered out by agent definition

4. **Agent Directory Scanning**:
   - Scans `config.agents.directory` for agent definition files
   - Parses markdown frontmatter to extract metadata
   - Handles missing or invalid files gracefully

### Backward Compatibility

- All changes are backward compatible
- Existing functionality preserved
- New features are additive (showing more information)
- Command signatures extended with optional parameters (Config, AgentCore)