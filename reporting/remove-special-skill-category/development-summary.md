# Development Summary: Remove "Special" Category for Skill Tool

## What was implemented

Removed the "Special" category for the `skill` tool and treated it as a regular built-in tool in the `/tools` command output.

### Changes Made

1. **`src/yoker/base.py`** - Modified `get_known_tools()` to include `SkillTool`:
   - Added import for `SkillTool` alongside other built-in tools
   - Created a list of built-in tools that includes `ReadTool`, `ListTool`, `WriteTool`, `UpdateTool`, `SearchTool`, `ExistenceTool`, `MkdirTool`
   - Added `SkillTool` to the list when `config.tools.skill.enabled` is True and `skill_registry` exists
   - This ensures the `skill` tool appears in the "Built-in" section of `/tools` output

2. **`src/yoker/commands/tools.py`** - Removed "Special" section:
   - Deleted the code block that created a "Special" section for `agent` and `skill` tools
   - The `skill` tool now naturally appears in the "Built-in" section alongside other built-in tools

3. **`tests/commands/test_tools.py`** - Added new test:
   - Added `test_tools_command_skill_in_builtin()` to verify that the skill tool appears in the Built-in section
   - Verified that no "Special" section exists in the output

## Files Modified

- `/Users/xtof/Workspace/agentic/yoker/src/yoker/base.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/commands/tools.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/commands/test_tools.py`

## Tests

All tests pass:
- **Test run**: `make test`
- **Result**: 1260 tests passed, 0 failures
- **Coverage**: 84%

Type checking and linting also pass:
- **Type check**: `make typecheck` - Success
- **Lint**: `make lint` - All checks passed

## Expected Behavior

Before:
```
Known tools:

Built-in:
  ✓ read           - Read file contents
  ✗ write          - Write content to a file
  ...

Special:
  ✓ skill          - Invoke a skill by name
```

After:
```
Known tools:

Built-in:
  ✗ existence       - Check if a file or folder exists
  ✗ list            - List files and directories
  ✓ skill           - Invoke a skill by name
  ✗ read            - Read the contents of a file
  ...

Plugins:
  ✓ plugins.demo:echo   - Echo back the input message

Agent: plugins.demo:demo
  Allowed tools: plugins.demo:echo
```

The `skill` tool is now categorized as a built-in tool, eliminating the artificial "Special" category.

## Decisions Made

1. **Approach**: Chose Option B from the requirements - kept the current registration logic (in `Agent.__init__`) but changed categorization in `/tools` command display. This is cleaner than passing the skill registry through `_build_tool_registry()`.

2. **Conditional inclusion**: `SkillTool` is only added to `get_known_tools()` when:
   - `config.tools.skill.enabled` is True (user has enabled skills)
   - `skill_registry` is not None (skills have been loaded)
   
   This ensures we don't show the skill tool in the built-in list if skills are disabled or not loaded.

3. **No "Special" section**: Completely removed the "Special" section code, as it was only used for `agent` and `skill` tools. The `agent` tool remains registered through the normal tool registry mechanism, so it will appear in the "Built-in" section if available.