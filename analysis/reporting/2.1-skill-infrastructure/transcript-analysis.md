# Skill Infrastructure Transcript Analysis

Analysis of how skills are introduced and used in Claude Code conversations.

**Source:** `inbox/recording.jsonl` (70-line HTTP recording)
**Skill Example:** `inbox/commit/SKILL.md`
**Date:** 2026-05-27

## Executive Summary

Skills are introduced through a two-phase mechanism:

1. **Discovery Phase:** Skills are listed in `<system-reminder>` blocks at the start of conversations
2. **Invocation Phase:** When invoked via slash command, the full skill content is injected in a subsequent message

The system uses XML-style tags to mark skill invocations and provides a base directory context for file operations.

## 1. Skill Discovery - System Context

### Format

Skills are introduced in the **first user message** as part of a `<system-reminder>` block:

```xml
<system-reminder>
The following skills are available for use with the Skill tool:

- {skill-name}: {skill-description}. Use when {trigger-conditions}. {additional-info}.
- {skill-name}: {skill-description}. ...
</system-reminder>
```

### Example from Transcript

```xml
<system-reminder>
The following skills are available for use with the Skill tool:

- commit: Guide git commit operations with atomic commits and conventional format. Use when committing changes, creating commits, or when user says "/commit", "commit these changes", "create a commit". Analyzes changes, groups by functionality, detects sensitive files, and waits for user verification.
- update-config: Use this skill to configure the Claude Code harness via settings.json. Automated behaviors ("from now on when X", "each time X", "whenever X", "before/after X") require hooks configured in settings.json - the harness executes these, not Claude, so memory/preferences cannot fulfill them. Also use for: permissions ("allow X", "add permission", "move permission to"), env vars ("set X=Y"), hook troubleshooting, or any changes to settings.json/settings.local.json files. Examples: "allow npm commands", "add bq permission to global settings", "move permission to user settings", "set DEBUG=true", "when claude stops show X". For simple settings like theme/model, suggest the /config command.
- keybindings-help: Use when the user wants to customize keyboard shortcuts, rebind keys, add chord bindings, or modify ~/.claude/keybindings.json. Examples: "rebind ctrl+s", "add a chord shortcut", "change the submit key", "customize keybindings".
- verify: Verify that a code change actually does what it's supposed to by running the app and observing behavior. Use when asked to verify a PR, confirm a fix works, test a change manually, check that a feature works, or validate local changes before pushing.
...
</system-reminder>
```

### Key Observations

1. **Single Block:** All available skills are listed in ONE `<system-reminder>` block
2. **Consistent Format:** Each skill follows the pattern:
   - Skill name (e.g., `commit`)
   - Colon separator
   - Brief description
   - `Use when` clause with trigger conditions
   - Optional additional details/examples
3. **Discovery Phase:** This block appears in EVERY conversation turn (in each request), ensuring the model always knows available skills
4. **No Content:** Only names and descriptions are provided - the full skill content is NOT included here

## 2. Skill Invocation - Content Injection

### Invocation Trigger

When a user types a slash command (e.g., `/commit`), the system creates a two-part message:

#### Part 1: Command Metadata

```xml
<command-message>commit</command-message>
<command-name>/commit</command-name>
<command-args>test.txt</command-args>
```

**Tags:**
- `<command-message>` - The skill name (without slash)
- `<command-name>` - The full slash command (with slash)
- `<command-args>` - Arguments passed to the command

#### Part 2: Skill Content

A separate text block containing the full SKILL.md content:

```markdown
Base directory for this skill: /Users/xtof/Workspace/agentic/http-proxy-logger/.claude/skills/commit

# commit

Guide git commit operations with atomic commits, functionality-based grouping, and conventional commit format.

## Overview

| Capability | Description |
|------------|-------------|
| Git safety protocol | Enforce safe git operations, prevent destructive actions |
| Atomic commits | Group changes by logical functionality |
| Conventional format | Apply type/scope/description format |
| Sensitive file detection | Block .env, *.key, credentials files |
| User verification | Wait for approval before committing |

## When to Use This Skill

Use this skill when:
- User wants to commit changes
- User invokes "/c3:commit" command
- User says "commit these changes" or "create a commit"
- Multiple changes need grouping analysis

## Git Safety Protocol

**CRITICAL:** Follow these rules without exception unless user explicitly requests otherwise.

| Rule | Reason |
|------|--------|
| NEVER commit directly to master/main in project mode | User acceptance happens on PRs |
| NEVER update git config | Preserves user's configuration |
...
```

### Message Structure

The invocation creates a user message with **TWO text blocks**:

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "<command-message>commit</command-message>\n<command-name>/commit</command-name>\n<command-args>test.txt</command-args>\n"
    },
    {
      "type": "text",
      "text": "Base directory for this skill: /Users/xtof/Workspace/agentic/http-proxy-logger/.claude/skills/commit\n\n# commit\n\nGuide git commit operations with atomic commits, functionality-based grouping, and conventional commit format.\n\n## Overview\n\n| Capability | Description |\n|------------|-------------|\n| Git safety protocol | Enforce safe git operations, prevent destructive actions |\n...\n"
    }
  ]
}
```

### Key Observations

1. **Base Directory:** The skill content starts with a base directory path
   ```
   Base directory for this skill: {absolute-path}
   ```
   This tells the model where the skill is located on disk.

2. **Full Content:** The entire SKILL.md file is injected, including:
   - YAML frontmatter (if present)
   - Markdown content
   - All sections and tables

3. **Two Blocks:** The command metadata and skill content are in separate text blocks within the same message

4. **Context Preservation:** The base directory allows the model to understand file paths relative to the skill location

## 3. Differences: Slash Command vs. Agent Choice

### Slash Command Invocation

**Trigger:** User explicitly types `/commit`

**Characteristics:**
- Command metadata is included (`<command-name>`, `<command-args>`)
- Arguments are parsed and provided
- Clear intent from user
- Immediate injection of full skill content

**Example:**
```xml
<command-message>commit</command-message>
<command-name>/commit</command-name>
<command-args>test.txt</command-args>
```

### Agent-Initiated Invocation

**Trigger:** Model decides to use a skill based on context (not yet observed in transcript)

**Expected Characteristics:**
- Would use `Skill` tool call
- Model references skill by name from the discovery phase
- No `<command-message>` tags
- Content injected via tool result

**Tool Call Pattern (Expected):**
```json
{
  "type": "tool_use",
  "name": "Skill",
  "input": {
    "skill": "commit",
    "args": "test.txt"
  }
}
```

**Tool Result Pattern (Expected):**
```json
{
  "type": "tool_result",
  "tool_use_id": "call_xxx",
  "content": "Base directory for this skill: ...\n\n# commit\n\nGuide git commit operations..."
}
```

## 4. Exact Format and Tags

### Discovery Phase Tags

| Tag | Purpose | Example |
|-----|---------|---------|
| `<system-reminder>` | Container for all available skills | Lists all skills in conversation start |
| `-` prefix | Skill name and description separator | `- commit: Guide git commit operations...` |
| `Use when` | Trigger condition clause | `Use when committing changes, creating commits...` |

### Invocation Phase Tags

| Tag | Purpose | Required |
|-----|---------|----------|
| `<command-message>` | Skill name (no slash) | Yes (for slash commands) |
| `<command-name>` | Full slash command | Yes (for slash commands) |
| `<command-args>` | Arguments to skill | Yes (for slash commands) |
| `Base directory for this skill:` | File system location | Yes (all invocations) |

### Content Structure

1. **SKILL.md format:**
   ```markdown
   ---
   name: commit
   description: Brief description
   ---

   # commit

   [Full markdown content]
   ```

2. **Injection format:**
   ```
   Base directory for this skill: {absolute-path}

   {complete SKILL.md content}
   ```

## 5. Implementation Implications

### For Skill Discovery

```python
def build_skills_reminder(skills: List[Skill]) -> str:
    """Build the system-reminder block listing all skills."""
    skill_lines = []
    for skill in skills:
        line = f"- {skill.name}: {skill.description}."
        if skill.triggers:
            line += f" Use when {skill.triggers}."
        if skill.examples:
            line += f" Examples: {skill.examples}."
        skill_lines.append(line)

    return f"""<system-reminder>
The following skills are available for use with the Skill tool:

{chr(10).join(skill_lines)}
</system-reminder>"""
```

### For Skill Invocation (Slash Command)

```python
def invoke_skill_slash(skill: Skill, args: str) -> List[ContentBlock]:
    """Create message blocks for slash command invocation."""
    return [
        {
            "type": "text",
            "text": f"<command-message>{skill.name}</command-message>\n"
                     f"<command-name>/{skill.name}</command-name>\n"
                     f"<command-args>{args}</command-args>\n"
        },
        {
            "type": "text",
            "text": f"Base directory for this skill: {skill.base_dir}\n\n"
                    f"{skill.content}\n"
        }
    ]
```

### For Skill Invocation (Tool Call)

```python
def invoke_skill_tool(skill: Skill, args: str) -> str:
    """Create tool result for agent-initiated skill invocation."""
    return f"Base directory for this skill: {skill.base_dir}\n\n{skill.content}"
```

## 6. Key Findings Summary

### Discovery Phase

- **Location:** First user message in `<system-reminder>` block
- **Content:** Skill names and descriptions only
- **Format:** Bulleted list with `Use when` clauses
- **Persistence:** Included in every conversation turn

### Invocation Phase

- **Trigger:** Slash command or agent tool call
- **Content:** Full SKILL.md content
- **Metadata:** Command tags for slash commands
- **Base Directory:** Absolute path provided for file operations

### Tag Hierarchy

```
Discovery:
  <system-reminder>
    - skill-name: description. Use when triggers. Examples: examples.

Invocation (Slash Command):
  Message 1:
    <command-message>name</command-message>
    <command-name>/name</command-name>
    <command-args>args</command-args>

  Message 2:
    Base directory for this skill: /path
    [Full SKILL.md content]

Invocation (Tool Call):
  Tool Result:
    Base directory for this skill: /path
    [Full SKILL.md content]
```

### Implementation Requirements

1. **Skill Registry:** Maintain a list of available skills
2. **Discovery Builder:** Generate system-reminder block for each turn
3. **Slash Command Parser:** Extract skill name and arguments
4. **Content Loader:** Read SKILL.md file from disk
5. **Base Directory Resolver:** Determine absolute path to skill directory
6. **Message Constructor:** Build appropriate message structure based on invocation type

## 7. Recommendations for Yoker

### Data Structures

```python
@dataclass
class Skill:
    """Represents a skill definition."""
    name: str
    description: str
    triggers: Optional[str] = None
    examples: Optional[str] = None
    base_dir: Path
    content: str  # Full SKILL.md content

@dataclass
class SkillInvocation:
    """Represents a skill invocation."""
    skill: Skill
    args: str
    invocation_type: Literal["slash_command", "tool_call"]
```

### Key Methods

```python
class SkillRegistry:
    """Manages skill discovery and invocation."""

    def __init__(self, skill_dirs: List[Path]):
        """Load skills from directories."""
        self.skills = self._load_skills(skill_dirs)

    def get_discovery_block(self) -> str:
        """Generate system-reminder block for all skills."""
        pass

    def invoke(self, skill_name: str, args: str,
               invocation_type: Literal["slash_command", "tool_call"]) -> SkillInvocation:
        """Create skill invocation."""
        pass
```

### Integration Points

1. **Conversation Start:** Inject discovery block into first user message
2. **Slash Command Handler:** Parse command, create invocation
3. **Tool Call Handler:** Create tool result with skill content
4. **Base Directory Context:** Provide file system context for skill operations

## Conclusion

The skill infrastructure uses a two-phase approach:

1. **Discovery:** Lightweight skill listing in every conversation turn
2. **Invocation:** Full skill content injection when actually used

This pattern minimizes context bloat while ensuring the model always knows what skills are available. The distinction between slash command and tool call invocations provides flexibility for both explicit user requests and autonomous agent decisions.

The XML-style tags provide clear semantic markers for parsing, and the base directory context enables skills to perform file system operations relative to their own location.