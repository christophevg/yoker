#!/usr/bin/env python3
"""Skill context injection demo for Yoker.

Demonstrates how skills are introduced in system reminders (discovery phase)
and how full skill content is injected when invoked (invocation phase).

Uses the actual Yoker Agent to show:
1. Discovery phase: Skills listed in system reminder
2. Slash command invocation: Full skill content injected
3. Natural language invocation: Agent recognizes skill from context
4. Agent attempts to execute skill actions (git commands in this case)

This is a demonstration of the skill infrastructure pattern, not a full implementation.
"""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yoker.agent import Agent
from yoker.agents.loader import parse_frontmatter
from yoker.config import Config, discover_config
from yoker.events import ContentChunkEvent, Event, EventType, ToolCallEvent, ToolResultEvent
from yoker.thinking import ThinkingMode


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


class DemoEventHandler:
  """Event handler to capture agent responses for demonstration."""

  def __init__(self):
    self.content_chunks: list[str] = []
    self.tool_calls: list[dict] = []
    self.tool_results: list[dict] = []

  def __call__(self, event: Event) -> None:
    """Handle an event from the agent."""
    if isinstance(event, ContentChunkEvent):
      self.content_chunks.append(event.text)
    elif isinstance(event, ToolCallEvent):
      self.tool_calls.append(
        {"tool": event.tool_name, "args": event.arguments}
      )
    elif isinstance(event, ToolResultEvent):
      self.tool_results.append(
        {"tool": event.tool_name, "result": event.result, "success": event.success}
      )


async def demonstrate_skill_injection():
  """Demonstrate skill context injection with the actual Yoker Agent."""
  print("=" * 80)
  print("SKILL CONTEXT INJECTION DEMO - Using Real Yoker Agent")
  print("=" * 80)
  print()

  # Load actual configuration like the CLI does
  config, config_path = discover_config()
  if config_path:
    print(f"Loaded configuration from: {config_path}")
  else:
    print("Using default configuration")
    config = Config()

  # Parse the commit skill from the actual file
  skill_path = Path("inbox/commit/SKILL.md")
  if skill_path.exists():
    skill_markdown = skill_path.read_text()
    print(f"Loaded skill from: {skill_path}")
  else:
    # Use inline skill definition for demo purposes
    skill_markdown = """---
name: commit
description: Guide git commit operations with atomic commits and conventional format.
---
# commit

Guide git commit operations.

## Usage

```
/commit [message]
```

Commit changes with atomic commits and conventional format.
"""
    print("Using inline skill definition (file not found)")

  commit_skill = parse_skill_definition(skill_markdown)
  print(f"Skill: {commit_skill.name}")
  print(f"Description: {commit_skill.description[:80]}...")
  print()

  # Create agent with config
  print("Creating agent...")
  agent = Agent(config=config, thinking_mode=ThinkingMode.SILENT)

  # Create event handler to capture output
  handler = DemoEventHandler()
  agent.add_event_handler(handler)

  # Begin session
  print("Starting agent session...\n")
  await agent.begin_session()

  # ============================================================
  # PHASE 1: DISCOVERY - Skills listed in system reminder
  # ============================================================
  print("=" * 80)
  print("PHASE 1: DISCOVERY (System Reminder)")
  print("=" * 80)
  print()
  print("Skills are listed in the <system-reminder> block.")
  print("The LLM sees these as available but doesn't have full content yet.")
  print()

  discovery_block = format_discovery_block([commit_skill])
  print(discovery_block)
  print()

  # Inject discovery block as system message
  agent.context.add_message("system", discovery_block)

  # ============================================================
  # PHASE 2: INVOCATION - Full content injection via slash command
  # ============================================================
  print("=" * 80)
  print("PHASE 2: INVOCATION (Slash Command)")
  print("=" * 80)
  print()
  print("User types: /commit")
  print()

  # Format invocation block
  invocation_block = format_invocation_block(commit_skill)

  print("System injects:")
  print(invocation_block[:500] + "...")
  print()

  # Clear previous chunks
  handler.content_chunks.clear()
  handler.tool_calls.clear()
  handler.tool_results.clear()

  # Add skill content as a user message (simulating the command)
  # In a real implementation, the system would inject this, not the user
  await agent.process(f"I want to commit my changes. Here is the skill content:\n\n{invocation_block}")

  # Show what happened
  print()
  print("-" * 80)
  print("Agent Response:")
  print("-" * 80)
  full_response = "".join(handler.content_chunks)
  print(full_response[:1000] if full_response else "(no text response)")

  if handler.tool_calls:
    print()
    print("Tool Calls:")
    for tc in handler.tool_calls:
      print(f"  - {tc['tool']}: {tc['args']}")

  if handler.tool_results:
    print()
    print("Tool Results:")
    for tr in handler.tool_results:
      print(f"  - {tr['tool']}: {tr['result'][:100]}...")

  # ============================================================
  # PHASE 3: NATURAL LANGUAGE INVOCATION
  # ============================================================
  print()
  print("=" * 80)
  print("PHASE 3: NATURAL LANGUAGE INVOCATION")
  print("=" * 80)
  print()
  print("User says: 'commit these changes'")
  print()

  # Clear previous chunks
  handler.content_chunks.clear()
  handler.tool_calls.clear()
  handler.tool_results.clear()

  # Add skill to system context (discovery phase)
  agent.context.add_message("system", discovery_block)

  # Send natural language message
  await agent.process("commit these changes")

  print()
  print("-" * 80)
  print("Agent Response:")
  print("-" * 80)
  full_response = "".join(handler.content_chunks)
  print(full_response[:1000] if full_response else "(no text response)")

  if handler.tool_calls:
    print()
    print("Tool Calls:")
    for tc in handler.tool_calls:
      print(f"  - {tc['tool']}: {tc['args']}")

  if handler.tool_results:
    print()
    print("Tool Results:")
    for tr in handler.tool_results:
      print(f"  - {tr['tool']}: {tr['result'][:100]}...")

  # End session
  await agent.end_session(reason="demo_complete")

  # ============================================================
  # SUMMARY
  # ============================================================
  print()
  print("=" * 80)
  print("KEY INSIGHTS")
  print("=" * 80)
  print()
  print("1. DISCOVERY PHASE:")
  print("   - Skills listed in <system-reminder> block")
  print("   - Shows name + brief description")
  print("   - LLM can reference these skills but doesn't load them")
  print()
  print("2. INVOCATION PHASE (Slash Command):")
  print("   - User types: /commit [args]")
  print("   - System injects: <command-message> + full SKILL.md content")
  print("   - LLM receives complete skill instructions")
  print("   - Agent attempts to execute skill actions (e.g., git commands)")
  print()
  print("3. NATURAL LANGUAGE INVOCATION:")
  print("   - User mentions skill trigger: 'commit these changes'")
  print("   - System has skill in context from discovery phase")
  print("   - LLM recognizes intent and references skill knowledge")
  print("   - Agent responds based on skill context")
  print()
  print("4. BENEFITS:")
  print("   - Context efficiency: Only load skills when needed")
  print("   - Clear structure: Discovery vs. invocation separation")
  print("   - Provenance: User can see exactly what was loaded")
  print()
  print("This pattern allows Yoker to manage many skills without")
  print("overwhelming the context window on every turn.")


def main():
  """Run the demonstration."""
  try:
    asyncio.run(demonstrate_skill_injection())
  except KeyboardInterrupt:
    print("\n\nDemo interrupted by user.")
  except Exception as e:
    print(f"\n\nError during demo: {e}")
    import traceback
    traceback.print_exc()


if __name__ == "__main__":
  main()