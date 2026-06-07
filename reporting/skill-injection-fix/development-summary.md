# Skill Command Injection Fix - Development Summary

## What was implemented

Fixed the skill command to properly inject skill content into the agent's context as a system message, making the skill content invisible to the user.

### Problem

Previously, when a user typed `/skill-name`, the skill content was being printed directly to the user, showing the raw skill content including `<command-message>` blocks and the skill's markdown content. This was not the desired behavior.

### Correct Behavior

1. User types `/example`
2. Skill content is injected into agent's context as a system message (invisible to user)
3. Agent processes the skill context and responds naturally
4. User sees ONLY the agent's response, not the skill content

### Changes Made

#### 1. `src/yoker/commands/skill.py`

Added a special marker system to signal skill injection:

- **`SKILL_INJECTION_MARKER`**: Special string prefix (`__SKILL_INJECTION__`) to identify skill content
- **`is_skill_injection()`**: Function to check if a command result is a skill injection marker
- **`extract_skill_content()`**: Function to extract the skill content from the injection marker
- Modified `_skill_handler()` to return the marker + skill content instead of printing it

The skill handler now returns:
```python
f"{SKILL_INJECTION_MARKER}{invocation_block}"
```

This allows the main loop to detect skill injections and handle them specially.

#### 2. `src/yoker/__main__.py`

Updated the command dispatch logic to detect and handle skill injections:

- Import skill injection detection functions
- When a skill injection is detected:
  1. Extract skill content from the marker
  2. Inject it as a system message into agent context
  3. Log the skill injection
  4. Process with agent using appropriate prompt:
     - If args provided: send args as user message
     - If no args: send minimal prompt "Execute the skill as requested."
  5. Agent responds based on skill context
- User never sees the raw skill content

#### 3. `scripts/demo_session.py`

Updated the demo session script to handle skill injections the same way as `__main__.py`:

- Import skill injection detection functions
- When a skill injection is detected:
  1. Inject skill content as system message
  2. Log the skill injection event
  3. Process with agent using appropriate prompt
  4. Regular commands are printed normally

#### 4. `demos/skills/yoker.toml`

Created configuration file for the skills demo:

```toml
[skills]
directories = ["demos/skills"]
```

This allows the demo to properly load the example skill from the `demos/skills/` directory.

## Files Modified

- `src/yoker/commands/skill.py` - Added skill injection marker system
- `src/yoker/__main__.py` - Updated command dispatch to handle skill injections
- `scripts/demo_session.py` - Updated demo to handle skill injections
- `demos/skills/yoker.toml` - Created demo configuration

## Testing

### Test Results

- **All 1190 tests pass**
- **Type checking: Success** (no issues in 58 source files)
- **Linting: All checks pass**

### Manual Testing

Ran the skills demo script to verify the fix:

```bash
uv run python scripts/demo_session.py --script demos/skills.md --skills-dir demos/skills --log
```

**Result:**
- User types `/example`
- Agent responds based on skill content (without showing skill content)
- Agent correctly follows skill instructions: "When invoked, briefly explain what skills are and how they help. Keep the response under 3 sentences."
- User can ask follow-up questions about the skill
- Skill content remains invisible to user throughout the session

## Implementation Details

### Skill Injection Flow

1. **User Input**: User types `/example args`
2. **Command Dispatch**: Command registry dispatches to skill command handler
3. **Skill Handler**: Returns `__SKILL_INJECTION__<skill_content>`
4. **Detection**: Main loop detects injection marker
5. **Context Injection**: Skill content added as system message to agent context
6. **Agent Processing**:
   - If args provided: `agent.process(args)`
   - If no args: `agent.process("Execute the skill as requested.")`
7. **Agent Response**: Agent responds based on skill context
8. **User sees**: Only the agent's response, not the skill content

### Design Decision

The skill injection uses a special marker (`__SKILL_INJECTION__`) to signal to the main loop that this is a skill command. This allows:

- Clean separation between command handling and skill injection
- No changes to the Command base class or other commands
- Easy detection and special handling
- Future extensibility for other types of injections

### What the User Sees

**Before fix:**
```
> /example
<command-message>
<command-name>example</command-name>
<command-args></command-args>
</command-message>

Base directory for this skill:

# Example Skill
... (full skill content shown)
```

**After fix:**
```
> /example
Skills are specialized capabilities that can be invoked to perform
specific tasks or provide focused expertise. They help by organizing
functionality into modular, reusable components...
```

## Decisions Made

1. **Marker-based detection**: Using a special marker string for skill injection detection rather than modifying the Command class or adding new return types. This keeps the implementation simple and backward-compatible.

2. **System message injection**: Injecting skill content as a system message rather than a user message. This makes it clear to the LLM that this is context/instruction rather than user input.

3. **Dynamic prompt**: Sending different prompts based on whether args are provided:
   - With args: The args are what the user wants
   - Without args: Minimal prompt to trigger skill execution

4. **Demo script update**: Ensured the demo script handles skill injections the same way as the main CLI for consistency.

## Verification

All acceptance criteria met:

✅ Skill content is NOT shown to user
✅ Skill content is injected into agent context as system message
✅ Agent responds based on skill instructions
✅ User sees only the agent's response
✅ Works for both `/example` and `/example args` invocations
✅ All tests pass
✅ Type checking passes
✅ Linting passes
✅ Demo works correctly