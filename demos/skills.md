---
title: Skills System Demo
description: Demonstrates skill infrastructure, slash commands, and skill invocation.
output: media/demo-skills.svg
events: media/events-skills.jsonl
---

## Setup

Create a temporary skills directory for the demo:

```bash
mkdir -p /tmp/yoker-skills
```

Create a sample skill file:

```bash
cat > /tmp/yoker-skills/demo.md << 'EOF'
---
name: demo-skill
description: A demo skill for testing skill invocation
triggers:
  - demo skill
  - test skill
---

# Demo Skill

This is a demonstration skill that shows how skills work in Yoker.

## Instructions

1. Read the user's request
2. Process the request
3. Respond with a helpful answer

Remember to be concise and helpful.
EOF
```

## Messages

- Set the YOKER_SKILLS_PATH environment variable to load skills: YOKER_SKILLS_PATH=/tmp/yoker-skills
- Run yoker with: python -m yoker
- Type /help to see available commands (including /demo-skill)
- Type /demo-skill to invoke the skill
- Ask: What does the demo skill do? Answer in 2 sentences.
- Clean up: rm -rf /tmp/yoker-skills