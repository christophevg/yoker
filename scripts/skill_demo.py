#!/usr/bin/env python3
"""Skill context injection demo for Yoker.

Demonstrates how skills are introduced in system reminders (discovery phase)
and how full skill content is injected when invoked (invocation phase).

This shows the pattern from Claude Code transcript analysis:
- Skills appear in <system-reminder> block listing available skills
- When invoked via slash command, full SKILL.md content is injected
- Tags used: <command-message>, <command-name>, <command-args>
- Skill content follows "Base directory for this skill:" marker
"""

from dataclasses import dataclass

from yoker.agents.loader import parse_frontmatter


@dataclass
class SkillDefinition:
  """Skill definition with frontmatter and body.

  Attributes:
    name: Skill identifier (unique).
    description: Short description for system reminder.
    content: Full skill content (body after frontmatter).
    trigger: Optional trigger phrase.
    args_schema: Optional arguments schema description.
  """

  name: str
  description: str
  content: str
  trigger: str | None = None
  args_schema: str | None = None


def parse_skill_definition(skill_markdown: str) -> SkillDefinition:
  """Parse a skill definition from Markdown with YAML frontmatter.

  Args:
    skill_markdown: Raw Markdown content with frontmatter.

  Returns:
    SkillDefinition object.
  """
  frontmatter, body = parse_frontmatter(skill_markdown)

  name = frontmatter.get("name", "unknown")
  description = frontmatter.get("description", "No description")
  trigger = frontmatter.get("trigger")
  args_schema = frontmatter.get("args")

  return SkillDefinition(
    name=name,
    description=description,
    content=body.strip(),
    trigger=trigger,
    args_schema=args_schema,
  )


def format_discovery_block(skills: list[SkillDefinition]) -> str:
  """Format the system-reminder block showing available skills.

  This is the discovery phase - skills are listed but not loaded.

  Args:
    skills: List of skill definitions.

  Returns:
    Formatted system-reminder block.
  """
  lines = ["<system-reminder>", "The following skills are available for use:"]

  for skill in skills:
    line = f"- {skill.name}: {skill.description}"
    lines.append(line)

  lines.append("</system-reminder>")
  return "\n".join(lines)


def format_invocation_block(skill: SkillDefinition, args: str = "") -> str:
  """Format the invocation block with full skill content injection.

  This is the invocation phase - the full skill content is loaded.

  Args:
    skill: The skill being invoked.
    args: Optional arguments passed to the skill.

  Returns:
    Formatted invocation block with skill content.
  """
  # Command message shows the user's slash command
  command_part = f"/{skill.name}"
  if args:
    command_part += f" {args}"

  lines = [
    "<command-message>",
    f"<command-name>{skill.name}</command-name>",
    f"<command-args>{args}</command-args>" if args else "<command-args></command-args>",
    "</command-message>",
    "",
    "Base directory for this skill:",
    "",
  ]

  # The full skill content is injected here
  lines.append(skill.content)

  return "\n".join(lines)


# Define demo skills inline (in real usage, these would be separate files)

HELLO_SKILL = """---
name: hello
description: Greet the user with a personalized message.
trigger: when user says "hello", "greet", or "say hi"
args: Optional name to personalize greeting
---

# Hello Skill

Greets the user with a warm welcome message.

## Usage

```
/hello [name]
```

## Arguments

- `name` (optional): Name to use in greeting. If not provided, uses "friend".

## Examples

```
/hello Alice
```

Output: "Hello, Alice! Welcome to yoker."

```
/hello
```

Output: "Hello, friend! Welcome to yoker."

## Implementation Notes

This skill demonstrates the simplest form of context injection:
1. Listed in system-reminder during discovery
2. Full content injected when invoked
"""

RESEARCH_SKILL = """---
name: c3:research
description: Research topics comprehensively with full provenance tracking.
  Use for web research, literature reviews, technology investigations,
  and gathering information with source citations.
args: topic to research
---

# Research Skill

Comprehensive research with provenance tracking.

## Usage

```
/c3:research <topic>
```

## Arguments

- `topic`: The topic to research (required)

## Capabilities

- Web search and content extraction
- Academic paper lookup
- Technology investigation
- Source citation tracking
- Provenance documentation

## Examples

```
/c3:research best practices for REST API design
```

```
/c3:research investigate Y library options
```

## Output Format

Returns structured research findings with:
- Executive summary
- Detailed findings
- Source citations
- Provenance tracking
"""

ANALYZE_SKILL = """---
name: analyze
description: Analyze code for quality issues, patterns, and improvements.
args: file or directory to analyze
---

# Analyze Skill

Static code analysis with actionable recommendations.

## Usage

```
/analyze <path>
```

## Arguments

- `path`: File or directory to analyze (required)

## Analysis Types

1. **Code Quality**: Linting issues, complexity metrics
2. **Pattern Detection**: Anti-patterns, code smells
3. **Security**: Vulnerability scanning
4. **Performance**: Optimization opportunities

## Output

Returns analysis results with:
- Issue categories
- Severity levels
- Specific line references
- Recommended fixes
"""


def main():
  """Run the skill demonstration."""
  print("=" * 80)
  print("SKILL CONTEXT INJECTION DEMO")
  print("=" * 80)
  print()

  # Parse skill definitions
  skills = [
    parse_skill_definition(HELLO_SKILL),
    parse_skill_definition(RESEARCH_SKILL),
    parse_skill_definition(ANALYZE_SKILL),
  ]

  # Phase 1: Discovery
  print("PHASE 1: DISCOVERY (System Reminder)")
  print("-" * 80)
  print("Skills are listed in the system-reminder block.")
  print("The LLM sees these as available but doesn't have full content yet.")
  print()
  print(format_discovery_block(skills))
  print()
  print()

  # Phase 2: Invocation
  print("PHASE 2: INVOCATION (Full Content Injection)")
  print("-" * 80)
  print("When a skill is invoked, the full SKILL.md content is injected.")
  print("This happens via <command-message> tags and content loading.")
  print()
  print(format_invocation_block(skills[0], args="Alice"))
  print()
  print()

  # Show another invocation example
  print("SECOND INVOCATION EXAMPLE")
  print("-" * 80)
  print(format_invocation_block(skills[1], args="best practices for async Python"))
  print()
  print()

  # Summary
  print("=" * 80)
  print("KEY INSIGHTS")
  print("=" * 80)
  print()
  print("1. DISCOVERY PHASE:")
  print("   - Skills listed in <system-reminder> block")
  print("   - Shows name + brief description")
  print("   - LLM can reference these skills but doesn't load them")
  print()
  print("2. INVOCATION PHASE:")
  print("   - User types: /skill-name [args]")
  print("   - System injects: <command-message> + full SKILL.md content")
  print("   - LLM receives complete skill instructions")
  print()
  print("3. BENEFITS:")
  print("   - Context efficiency: Only load skills when needed")
  print("   - Clear structure: Discovery vs. invocation separation")
  print("   - Provenance: User can see exactly what was loaded")
  print()
  print("This pattern allows Yoker to manage many skills without")
  print("overwhelming the context window on every turn.")


if __name__ == "__main__":
  main()
