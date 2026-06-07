# Skill Discovery Fix - Development Summary

## Issue

Skills were loaded into the `skill_registry` but never shown to the agent. When asked "list loaded skills", the agent only showed tools because the skill discovery block was not being added to the agent's context during initialization.

## Root Cause

Two places where skills are loaded:

1. **Agent.__init__** - Skills loaded from `YOKER_SKILLS_PATH` environment variable
2. **create_command_registry in __main__.py** - Skills loaded from configuration directories

Neither location was adding the skill discovery block to the agent's context.

## Solution

Added skill discovery block injection in both locations:

### 1. Agent.__init__ (src/yoker/agent.py)

After loading skills from environment variable, inject the discovery block:

```python
# Load skills from YOKER_SKILLS_PATH environment variable
skills = load_skills_from_env()
if skills:
  self._core.skill_registry = SkillRegistry()
  self._core.skill_registry.update(skills)
  log.info("skills_loaded", count=len(skills), names=list(skills.keys()))

# Add skill discovery block to context if skills are loaded
if self._core.skill_registry and self._core.skill_registry.count > 0:
  from yoker.skills import format_discovery_block

  skill_list = self._core.skill_registry.list_skills()
  discovery_block = format_discovery_block(skill_list)
  # Add as system message before any agent definition
  # This ensures skills are visible to the agent
  self.context.add_message("system", discovery_block)
  log.info("skill_discovery_added", skill_count=len(skill_list))
```

### 2. create_command_registry (src/yoker/__main__.py)

After loading skills from configuration directories, inject the discovery block:

```python
# Load skills from configuration and environment
skill_registry = SkillRegistry()

# Load from configured directories
for directory in config.skills.directories:
  skills = load_skills(directory)
  for skill_name, skill in skills.items():
    skill_registry.register(skill)
    log.info("skill_loaded", name=skill_name, source=directory)

# Load from environment variable
env_skills = load_skills_from_env()
for skill_name, skill in env_skills.items():
  skill_registry.register(skill)
  log.info("skill_loaded_from_env", name=skill_name)

# Set skill registry on agent
agent._core.skill_registry = skill_registry

# Add skill discovery block to context if skills are loaded
if skill_registry.count > 0:
  from yoker.skills import format_discovery_block

  skill_list = skill_registry.list_skills()
  discovery_block = format_discovery_block(skill_list)
  # Add as system message so the agent knows about available skills
  agent.context.add_message("system", discovery_block)
  log.info("skill_discovery_added", skill_count=len(skill_list))
```

## Files Modified

1. **src/yoker/agent.py** - Added skill discovery injection after environment variable skill loading
2. **src/yoker/__main__.py** - Added skill discovery injection after configuration directory skill loading
3. **src/yoker/config/__init__.py** - Exported `SkillsConfig` for external use

## Testing

All tests pass (1206 passed):
- Type checking: ✓
- Linting: ✓
- Unit tests: ✓
- Integration tests: ✓

### Manual Verification

Created test scripts to verify:

1. **test_skill_discovery.py** - Verified skills loaded from `YOKER_SKILLS_PATH` are injected into context
2. **test_skill_discovery_cli.py** - Verified skills loaded from config directories are injected into context
3. **test_skill_question.py** - Verified agent can see skills in context

All tests confirmed that the skill discovery block is properly injected as a system message.

## Expected Behavior

**Before:**
```
> what skills do you have loaded?
[I can only see tools, not skills]
```

**After:**
```
> what skills do you have loaded?
[Agent sees <system-reminder> with skill list and can respond:]
You have the following skill loaded:
- example-skill: An example skill for demonstration
```

## Implementation Notes

### Timing

The skill discovery block is added:
- **After** agent initialization (for env var skills)
- **After** command registry creation (for config directory skills)
- **Before** the first user message

This ensures the agent always has skill visibility from the start of the session.

### Discovery Block Format

The discovery block uses the existing `format_discovery_block()` function from `yoker.skills.injection`:

```
<system-reminder>
The following skills are available for use:
- skill-name: skill description
- another-skill: another description
</system-reminder>
```

This is the same format used during skill invocation, ensuring consistency.

### Why Two Locations?

1. **Agent.__init__** - Handles skills from `YOKER_SKILLS_PATH` environment variable (library usage)
2. **create_command_registry** - Handles skills from configuration file directories (CLI usage)

Both paths are needed to support:
- Direct library usage (Agent() constructor)
- CLI usage (python -m yoker)

## Future Considerations

1. **Skill Updates** - If skills are loaded dynamically during a session, re-injection of the discovery block may be needed
2. **Context Size** - Large skill lists will consume context window; consider pagination or filtering
3. **Skill Visibility** - Consider adding a `/skills` command to show loaded skills without invoking them

## Related

- Skill invocation flow: `/skill-name args` → `format_invocation_block()` → full skill content injected
- Skill discovery flow: Agent init → `format_discovery_block()` → skill list injected