---
output: media/demo-skill-tool.svg
---

# Skill Tool Demo

Show how the agent can invoke skills using the skill tool.

User: what skills are available?

Assistant: Looking at the discovery block, I can see the following skills available:

- example: An example skill for testing

You can use the `skill` tool to invoke any of these skills.

User: use the example skill

Assistant: I'll invoke the example skill for you.

<skill_invocation>
skill skill_name="example"
</skill_invocation>

<skill_result>
<command-message>
<command-name>example</command-name>
<command-args></command-args>
</command-message>

Base directory for this skill:

# Example Skill

This is an example skill for testing purposes.
</skill_result>

I've loaded the example skill content. It's a simple test skill. Would you like me to help you with something specific using this skill?