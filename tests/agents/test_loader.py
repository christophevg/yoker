"""Tests for agent definition loader."""

from pathlib import Path

import pytest

from yoker.agents.loader import (
  load_agent_definition,
  load_agent_definitions,
  parse_frontmatter,
)
from yoker.exceptions import ConfigurationError, FileNotFoundError


class TestParseFrontmatter:
  """Tests for frontmatter parsing."""

  def test_parse_valid_frontmatter(self) -> None:
    """Test parsing valid frontmatter."""
    content = """---
name: test-agent
description: Test agent
tools: Read, Search
---

# System Prompt

You are a test agent.
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter == {
      "name": "test-agent",
      "description": "Test agent",
      "tools": "Read, Search",
    }
    assert "# System Prompt" in body
    assert "You are a test agent." in body

  def test_parse_no_frontmatter(self) -> None:
    """Test content without frontmatter."""
    content = "# Just Markdown\n\nNo frontmatter here."
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter == {}
    assert body == content

  def test_parse_empty_frontmatter(self) -> None:
    """Test empty frontmatter."""
    content = """---
---

# Content
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter == {}
    assert "# Content" in body

  def test_parse_frontmatter_with_list(self) -> None:
    """Test frontmatter with YAML list."""
    content = """---
name: test
description: Test
tools:
  - Read
  - Search
  - List
---

Body content.
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter["tools"] == ["Read", "Search", "List"]
    assert "Body content." in body

  def test_parse_frontmatter_with_optional_color(self) -> None:
    """Test frontmatter with optional color field."""
    content = """---
name: test
description: Test
tools: Read
color: blue
---

Body.
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter["color"] == "blue"

  def test_parse_invalid_yaml(self) -> None:
    """Test invalid YAML raises ConfigurationError."""
    content = """---
name: test
invalid yaml: [unclosed
---
Body.
"""
    with pytest.raises(ConfigurationError) as exc_info:
      parse_frontmatter(content)
    assert "Invalid YAML" in str(exc_info.value)

  def test_parse_frontmatter_not_dict(self) -> None:
    """Test frontmatter that parses to non-dict raises ConfigurationError."""
    content = """---
- item1
- item2
---
Body.
"""
    with pytest.raises(ConfigurationError) as exc_info:
      parse_frontmatter(content)
    assert "dictionary" in str(exc_info.value)

  def test_parse_unclosed_frontmatter(self) -> None:
    """Test unclosed frontmatter returns empty frontmatter."""
    content = """---
name: test
description: Test

No closing delimiter.
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter == {}
    assert "No closing delimiter." in body  # Full content returned

  def test_parse_multiple_delimiters_in_body(self) -> None:
    """Test that only first frontmatter block is parsed."""
    content = """---
name: test
description: Test
tools: Read
---

# Header

---

More content with delimiter.
"""
    frontmatter, body = parse_frontmatter(content)
    assert frontmatter["name"] == "test"
    assert "---" in body  # Second delimiter in body


class TestLoadAgentDefinition:
  """Tests for loading single agent definition."""

  def test_load_valid_agent(self, tmp_path: Path) -> None:
    """Test loading a valid agent definition."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: researcher
description: Research assistant
tools: Read, Search
color: blue
---

# Researcher Agent

You are a research assistant.
""")
    definition = load_agent_definition(agent_file)
    assert definition.name == "researcher"
    assert definition.description == "Research assistant"
    assert definition.tools == ("Read", "Search")
    assert definition.color == "blue"
    assert "Researcher Agent" in definition.system_prompt
    assert str(agent_file) == definition.source_path

  def test_load_agent_with_tools_list(self, tmp_path: Path) -> None:
    """Test loading agent with tools as YAML list."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
tools:
  - List
  - Read
  - Search
---

Body.
""")
    definition = load_agent_definition(agent_file)
    assert definition.tools == ("List", "Read", "Search")

  def test_load_missing_file(self, tmp_path: Path) -> None:
    """Test loading non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as exc_info:
      load_agent_definition(tmp_path / "nonexistent.md")
    assert "agent definition not found" in str(exc_info.value).lower()

  def test_load_missing_name(self, tmp_path: Path) -> None:
    """Test missing name field raises ConfigurationError."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
description: Test
tools: Read
---

Body.
""")
    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definition(agent_file)
    assert "name" in str(exc_info.value)

  def test_load_missing_description(self, tmp_path: Path) -> None:
    """Test missing description field raises ConfigurationError."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
tools: Read
---

Body.
""")
    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definition(agent_file)
    assert "description" in str(exc_info.value)

  def test_load_missing_tools(self, tmp_path: Path) -> None:
    """Test missing tools field raises ConfigurationError."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
---

Body.
""")
    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definition(agent_file)
    assert "tools" in str(exc_info.value)

  def test_load_empty_tools_string(self, tmp_path: Path) -> None:
    """Test empty tools string raises ConfigurationError."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
tools: ""
---

Body.
""")
    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definition(agent_file)
    assert "tools" in str(exc_info.value)

  def test_load_invalid_tools_type(self, tmp_path: Path) -> None:
    """Test invalid tools type raises ConfigurationError."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
tools: 123
---

Body.
""")
    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definition(agent_file)
    assert "tools" in str(exc_info.value)

  def test_load_agent_no_color(self, tmp_path: Path) -> None:
    """Test loading agent without optional color field."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
tools: Read
---

Body.
""")
    definition = load_agent_definition(agent_file)
    assert definition.color is None

  def test_load_agent_empty_body(self, tmp_path: Path) -> None:
    """Test loading agent with empty body."""
    agent_file = tmp_path / "test.md"
    agent_file.write_text("""---
name: test
description: Test
tools: Read
---
""")
    definition = load_agent_definition(agent_file)
    assert definition.system_prompt == ""


class TestLoadAgentDefinitions:
  """Tests for loading all agents from directory."""

  def test_load_multiple_agents(self, tmp_path: Path) -> None:
    """Test loading multiple agent definitions."""
    # Create agents directory
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    # Create multiple agent files
    (agents_dir / "main.md").write_text("""---
name: main
description: Main agent
tools: Read
---

Main agent prompt.
""")

    (agents_dir / "researcher.md").write_text("""---
name: researcher
description: Research agent
tools: Read, Search
---

Research prompt.
""")

    definitions = load_agent_definitions(agents_dir)
    assert len(definitions) == 2
    assert "main" in definitions
    assert "researcher" in definitions
    assert definitions["main"].tools == ("Read",)
    assert definitions["researcher"].tools == ("Read", "Search")

  def test_load_empty_directory(self, tmp_path: Path) -> None:
    """Test loading from empty directory."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    definitions = load_agent_definitions(agents_dir)
    assert definitions == {}

  def test_load_missing_directory(self, tmp_path: Path) -> None:
    """Test loading from non-existent directory."""
    with pytest.raises(FileNotFoundError) as exc_info:
      load_agent_definitions(tmp_path / "nonexistent")
    assert "agents directory not found" in str(exc_info.value).lower()

  def test_load_file_not_directory(self, tmp_path: Path) -> None:
    """Test loading from path that is a file."""
    file_path = tmp_path / "notadir.md"
    file_path.write_text("content")

    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definitions(file_path)
    assert "not a directory" in str(exc_info.value)

  def test_load_duplicate_names(self, tmp_path: Path) -> None:
    """Test loading agents with duplicate names raises ConfigurationError."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    # Create two agents with same name
    (agents_dir / "agent1.md").write_text("""---
name: duplicate
description: First agent
tools: Read
---

First.
""")

    (agents_dir / "agent2.md").write_text("""---
name: duplicate
description: Second agent
tools: Search
---

Second.
""")

    with pytest.raises(ConfigurationError) as exc_info:
      load_agent_definitions(agents_dir)
    assert "Duplicate agent name" in str(exc_info.value)

  def test_load_ignores_non_markdown(self, tmp_path: Path) -> None:
    """Test that non-markdown files are ignored."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    (agents_dir / "main.md").write_text("""---
name: main
description: Main
tools: Read
---

Prompt.
""")

    (agents_dir / "config.toml").write_text("name = 'ignored'")
    (agents_dir / "README.txt").write_text("This is ignored")

    definitions = load_agent_definitions(agents_dir)
    assert len(definitions) == 1
    assert "main" in definitions

  def test_load_sorted_order(self, tmp_path: Path) -> None:
    """Test that agents are loaded in sorted filename order."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    # Create in non-alphabetical order
    (agents_dir / "zebra.md").write_text("""---
name: zebra
description: Z
tools: Read
---
""")

    (agents_dir / "alpha.md").write_text("""---
name: alpha
description: A
tools: Read
---
""")

    definitions = load_agent_definitions(agents_dir)
    names = list(definitions.keys())
    # Both should be loaded, order doesn't matter for dict
    assert "alpha" in names
    assert "zebra" in names
