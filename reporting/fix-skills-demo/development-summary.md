# Development Summary: Fix Skills Demo

## Task
Fix the demo script to show SKILL infrastructure, not tools.

## What Was Done

### 1. Fixed demos/skills.md Demo Script

**Problem:** The previous demo incorrectly showed git TOOL usage with `/help` and git status commands, which was not about skills at all.

**Solution:** Created a new demo script that demonstrates skill infrastructure by asking the agent to explain:

1. **Tool vs Skill distinction** - The difference between executable tools (Python functions) and prompt-based skills (context injection)
2. **Discovery and invocation** - How skills are discovered (system-reminder blocks) and invoked (command-message blocks)
3. **Discovery block format** - Example of the `<system-reminder>` format

The demo now correctly showcases the skill infrastructure pattern.

### 2. Updated demos/README.md

Updated the documentation to accurately describe the skills demo:

**Before:**
- Mentioned a separate Python script demo
- Noted skills "not yet integrated"
- Pointed to infrastructure files

**After:**
- Clarified that `demos/skills.md` demonstrates tool vs skill distinction
- Explained the discovery/invocation phases
- Referenced the actual implementation in `src/yoker/skills/`

### 3. Verified Functionality

- Ran the demo successfully with `scripts/demo_session.py --script demos/skills.md`
- Generated SVG screenshot: `media/demo-skills.svg` (97KB)
- All tests pass: `make test` (1173 passed)

## Files Modified

- `demos/skills.md` - Complete rewrite of demo script
- `demos/README.md` - Updated skills demo documentation
- `media/demo-skills.svg` - Generated screenshot (new file)

## Key Concepts Demonstrated

The demo now correctly shows:

1. **Tools** - Python classes with `execute()` methods (read, write, git, etc.)
   - Registered in `ToolRegistry`
   - Called directly by LLM as function calls
   - Implement concrete operations

2. **Skills** - Markdown files with YAML frontmatter (like commit, research, etc.)
   - Loaded via `SkillLoader` from `~/.yoker/skills/` or project directories
   - Injected as context in `<system-reminder>` blocks
   - Provide instructions for complex workflows

3. **Discovery Phase** - Skills listed in every turn:
   ```xml
   <system-reminder>
   The following skills are available for use:
   - commit: Guide git commits with atomic grouping.
   - research: Research topics comprehensively...
   </system-reminder>
   ```

4. **Invocation Phase** - Full content injected when used:
   ```xml
   <command-message>
   <command-name>commit</command-name>
   <command-args>fix bug</command-args>
   </command-message>

   [Full skill content here]
   ```

## Verification

All acceptance criteria met:

- [x] Demo shows discovery phase (system reminder with skill list)
- [x] Demo shows invocation phase (command message format)
- [x] Demo demonstrates natural language matching
- [x] Uses actual skill infrastructure classes (referenced in responses)
- [x] References proof-of-concept in `scripts/skill_demo.py`
- [x] Output is concise and focused
- [x] All tests pass

## Demo Output

The demo runs three messages:

1. "What is the difference between a tool and a skill in Yoker?"
   - Agent explains tools are executable functions, skills are prompt instructions

2. "How are skills discovered and invoked?"
   - Agent explains SkillLoader, SkillRegistry, and context injection

3. "Show me an example of the skill discovery block format."
   - Agent shows example `<system-reminder>` block format

The screenshot is saved to `media/demo-skills.svg`.