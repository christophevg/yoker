# Demo Scripts

This directory contains demo scripts for demonstrating Yoker features.

## Script Types

### Markdown Demos (`.md` files)

Simple demos that can be run with `demo_session.py`:

```bash
# Run a specific demo
uv run python scripts/demo_session.py --script demos/session.md

# Run all demos
uv run python scripts/demo_session.py --scripts-dir demos/

# Generate screenshot with logging
uv run python scripts/demo_session.py --script demos/list-tool.md --log
```

Each demo script is a Markdown file with YAML frontmatter:

```yaml
---
title: Feature Name
description: What this demo illustrates
output: media/demo-feature.svg
events: media/events-feature.jsonl
---

## Messages

- /command
- User message 1
- User message 2
```

### Python Demos (in `scripts/` directory)

Complex demos that require programmatic setup:

```bash
# Skill context injection demo
uv run python scripts/skill_demo.py
```

## Available Demos

### Core Features

- **session.md** - Full session showing commands, tool calls, and thinking mode
- **commands.md** - Built-in slash commands (`/help`, `/think`)
- **thinking.md** - LLM thinking mode with visible reasoning

### Tools

- **list-tool.md** - Directory listing with pattern matching
- **read-tool.md** - Reading files
- **write-tool.md** - Writing files
- **update-tool.md** - Editing existing files
- **search-tool.md** - Searching files and content
- **existence-tool.md** - Checking file/folder existence
- **mkdir-tool.md** - Creating directories
- **git-tool.md** - Git operations (status, log, diff, branch, show)
- **webfetch.md** - Fetching web content
- **websearch.md** - Web search capability
- **agent-tool.md** - Spawning sub-agents

### Advanced Features

- **skills.md** - Skills infrastructure demonstration

## Skills Infrastructure Demo

The skills infrastructure is demonstrated via a dedicated Python script:

```bash
uv run python scripts/skill_demo.py
```

This demo shows:

1. **Discovery Phase**: Skills listed in system reminder
2. **Invocation Phase**: Full skill content injected via slash command
3. **Natural Language Invocation**: Agent recognizes skill from context

**Note**: Skills are not yet integrated into the command system. The demo shows
the infrastructure pattern and how skill context injection would work.

For details, see:
- `scripts/skill_demo.py` - Working demonstration
- `analysis/api-skill-infrastructure.md` - API design
- `src/yoker/skills/` - Implementation

## Writing Demos

### Best Practices

1. **Keep it focused**: One feature per demo
2. **Add brevity constraints**: Add "Answer in X lines" to keep output concise
3. **Use specific patterns**: Instead of "list all files", use "list files matching CLAUDE*"
4. **Avoid open-ended questions**: They trigger long LLM responses
5. **Single message preferred**: Keep demos short for readable screenshots

### Example

```markdown
---
title: List Tool
description: Demonstrates the list tool for directory listings.
output: media/demo-list-tool.svg
events: media/events-list-tool.jsonl
---

## Messages

- List files matching "CLAUDE*" in the current directory. Reply in 2 lines or less.
```

### Generating Screenshots

After creating or modifying demos:

```bash
# Generate specific demo screenshot
uv run python scripts/demo_session.py --script demos/new-feature.md

# Regenerate all screenshots
make demos

# Or individually
uv run python scripts/demo_session.py --script demos/list-tool.md
```

Output files:
- `media/demo-{feature}.svg` - SVG screenshot
- `media/events-{feature}.jsonl` - Conversation log (with `--log` flag)

## Related Files

- `scripts/demo_session.py` - Demo runner
- `src/yoker/demo/` - Demo script loader
- `media/` - Generated screenshots