"""Acceptance tests for M.2 Default Tools Behavior (Option C).

Covers all 12 acceptance criteria from the approved plan:

1. Missing `tools` in YAML → tools=() + tools_unspecified=True → ALL config tools.
2. tools: (null/null/~/""/[]) → tools=() + tools_unspecified=False → NO tools.
3. tools: [read, list] → exactly those tools (no regression).
4. In-memory AgentDefinition() → ALL tools (no regression).
5. In-memory AgentDefinition(tools=None) and AgentDefinition(tools=[]) → NO tools.
6. In-memory AgentDefinition(tools=("yoker:read",)) → filter (no regression).
7. config.tools.<name>.enabled=False drops a tool even when all-tools is granted.
8. WARN event `agent_tools_default_granted` emitted when all-tools is granted by omission.
9. validate_agent_definition on runtime path; empty/missing tools accepted.
10. backwards.md continues to load as a no-tools agent (regression guard).
11. Docstring/code agreement in core/__init__.py, agents/schema.py, agents/loader.py.
12. No regression for explicit-tool filtering and namespace handling.
"""

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from yoker.agents import AgentDefinition, load_agent_definition
from yoker.agents.validator import validate_agent_definition
from yoker.config import Config
from yoker.core import Agent


class TestLoaderMatrix:
  """Criteria 1-3: loader handles all YAML `tools:` forms correctly."""

  def _write(self, tmp_path: Path, frontmatter: str) -> Path:
    f = tmp_path / "agent.md"
    f.write_text(f"---\n{frontmatter}\n---\n\nBody.\n")
    return f

  def test_missing_tools_loads_all_tools_flag(self, tmp_path: Path) -> None:
    """Criterion 1: missing `tools:` → tools=() + tools_unspecified=True."""
    f = self._write(tmp_path, "name: test\ndescription: Test\n")
    d = load_agent_definition(f)
    assert d.tools == ()
    assert d.tools_unspecified is True

  @pytest.mark.parametrize("value", ["", "null", "~", "[]"])
  def test_present_null_tools_loads_no_tools_flag(self, tmp_path: Path, value: str) -> None:
    """Criterion 2: present-but-empty → tools=() + tools_unspecified=False."""
    f = self._write(tmp_path, f"name: test\ndescription: Test\ntools: {value}\n")
    d = load_agent_definition(f)
    assert d.tools == ()
    assert d.tools_unspecified is False

  def test_explicit_list_filters(self, tmp_path: Path) -> None:
    """Criterion 3: tools: [read, list] → exactly those (namespaced)."""
    f = self._write(tmp_path, "name: test\ndescription: Test\ntools:\n  - read\n  - list\n")
    d = load_agent_definition(f)
    assert d.tools == ("file:read", "file:list")
    assert d.tools_unspecified is False


class TestInMemoryAgentDefinition:
  """Criteria 4-6: in-memory AgentDefinition constructors."""

  def test_default_constructor_grants_all_tools(self) -> None:
    """Criterion 4: AgentDefinition() → all tools (no regression)."""
    d = AgentDefinition()
    assert d.tools == ()
    assert d.tools_unspecified is True

  @pytest.mark.parametrize("empty", [None, []])
  def test_explicit_empty_disables_tools(self, empty) -> None:
    """Criterion 5: AgentDefinition(tools=None) and AgentDefinition(tools=[]) → no tools."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=empty)
    assert d.tools == ()
    assert d.tools_unspecified is False

  def test_explicit_filter(self) -> None:
    """Criterion 6: AgentDefinition(tools=("yoker:read",)) → filter (no regression)."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=("yoker:read",))
    assert d.tools == ("yoker:read",)
    assert d.tools_unspecified is False


class TestRuntimeFiltering:
  """Criteria 1, 4, 7, 8: Agent runtime behavior for each branch."""

  def test_default_definition_grants_all_tools(self) -> None:
    """Criterion 4: AgentDefinition() at runtime → all config-enabled tools."""
    agent = Agent(config=Config(), agent_definition=AgentDefinition())
    # All built-in tools are present.
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is not None
    assert agent.tools.get("yoker:write") is not None

  def test_missing_tools_yaml_grants_all_tools(self, tmp_path: Path) -> None:
    """Criterion 1: agent loaded from YAML with no `tools:` → all tools."""
    f = tmp_path / "agent.md"
    f.write_text("---\nname: test\ndescription: Test\n---\n\nBody.\n")
    d = load_agent_definition(f)
    agent = Agent(config=Config(), agent_definition=d)
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is not None

  @pytest.mark.parametrize("value", ["", "null", "~", "[]"])
  def test_present_null_yaml_disables_tools(self, tmp_path: Path, value: str) -> None:
    """Criterion 2: agent loaded with present-but-empty tools → no tools."""
    f = tmp_path / "agent.md"
    f.write_text(f"---\nname: test\ndescription: Test\ntools: {value}\n---\n\nBody.\n")
    d = load_agent_definition(f)
    agent = Agent(config=Config(), agent_definition=d)
    assert list(agent.tools.names) == []

  def test_explicit_list_filters_at_runtime(self) -> None:
    """Criterion 3: explicit list at runtime → only those tools.

    Uses bare names against an in-memory definition so the runtime's
    built-in `yoker:` prefix handling kicks in (file-loaded agents get a
    `file:` namespace on tool names, which is exercised separately by the
    loader tests).
    """
    d = AgentDefinition(simple_name="test-agent", description="d", tools=("read", "list"))
    agent = Agent(config=Config(), agent_definition=d)
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is not None
    assert agent.tools.get("yoker:write") is None
    assert agent.tools.get("yoker:search") is None

  def test_in_memory_explicit_empty_disables_tools(self) -> None:
    """Criterion 5: AgentDefinition(tools=None) at runtime → no tools."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=None)
    agent = Agent(config=Config(), agent_definition=d)
    assert list(agent.tools.names) == []

  def test_in_memory_explicit_list_disables_tools(self) -> None:
    """Criterion 5 (list form): AgentDefinition(tools=[]) at runtime → no tools."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=[])
    agent = Agent(config=Config(), agent_definition=d)
    assert list(agent.tools.names) == []

  def test_in_memory_explicit_filter(self) -> None:
    """Criterion 6: AgentDefinition(tools=("yoker:read",)) → only read."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=("yoker:read",))
    agent = Agent(config=Config(), agent_definition=d)
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is None

  def test_config_disabled_drops_tool_even_when_all_granted(self) -> None:
    """Criterion 7: config.tools.<name>.enabled=False drops the tool even on all-tools grant."""
    config = Config()
    # Sanity: read is enabled by default; disable it.
    config.tools.read.enabled = False
    agent = Agent(config=config, agent_definition=AgentDefinition())
    assert agent.tools.get("yoker:read") is None
    # Other tools still present.
    assert agent.tools.get("yoker:list") is not None

  def test_warn_emitted_on_all_tools_granted_by_omission(self) -> None:
    """Criterion 8: WARN `agent_tools_default_granted` emitted when all-tools granted by omission."""
    with patch("yoker.core.logger.warning") as mock_warning:
      Agent(config=Config(), agent_definition=AgentDefinition())
    matching = [
      c
      for c in mock_warning.call_args_list
      if c.args and c.args[0] == "agent_tools_default_granted"
    ]
    assert len(matching) == 1
    # Logged at WARN level (using logger.warning, which is WARN).

  def test_warn_not_emitted_when_tools_explicitly_empty(self) -> None:
    """No all-tools-granted warning when tools are explicitly empty (None/[])."""
    with patch("yoker.core.logger.warning") as mock_warning:
      Agent(
        config=Config(),
        agent_definition=AgentDefinition(simple_name="test-agent", description="d", tools=None),
      )
    matching = [
      c
      for c in mock_warning.call_args_list
      if c.args and c.args[0] == "agent_tools_default_granted"
    ]
    assert matching == []


class TestValidatorOnRuntimePath:
  """Criterion 9: validate_agent_definition is wired into the runtime path."""

  def test_validator_called_on_agent_construction(self) -> None:
    """The validator runs during Agent construction (warnings logged, not raised)."""
    with patch("yoker.core.validate_agent_definition") as mock_validate:
      mock_validate.return_value = ["test warning"]
      with patch("yoker.core.logger.warning") as mock_warning:
        Agent(config=Config(), agent_definition=AgentDefinition())
      mock_validate.assert_called_once()
      # The warning is logged at WARN level.
      validation_calls = [
        c for c in mock_warning.call_args_list if c.args and c.args[0] == "agent_validation_warning"
      ]
      assert len(validation_calls) == 1

  def test_validator_accepts_empty_tools(self) -> None:
    """Empty/missing tools no longer raise (Option C)."""
    config = Config()
    # tools=() with tools_unspecified=True (default).
    d_all = AgentDefinition(simple_name="test-agent", description="d")
    assert validate_agent_definition(d_all, config.tools) == []
    # tools=None → tools_unspecified=False (no tools).
    d_none = AgentDefinition(simple_name="test-agent", description="d", tools=None)
    assert validate_agent_definition(d_none, config.tools) == []
    # tools=() + tools_unspecified=False (no tools).
    d_explicit = AgentDefinition(
      simple_name="test-agent", description="d", tools=(), tools_unspecified=False
    )
    assert validate_agent_definition(d_explicit, config.tools) == []


class TestBackwardsRegression:
  """Criterion 10: backwards.md (tools: []) stays a no-tools agent."""

  def test_backwards_md_loads_no_tools(self) -> None:
    """backwards.md continues to load as a no-tools agent (regression guard)."""
    backwards_path = (
      Path(__file__).parent.parent.parent
      / "examples"
      / "plugins"
      / "demo"
      / "yoker_plugin_demo"
      / "agents"
      / "backwards.md"
    )
    assert backwards_path.exists(), f"backwards.md not found at {backwards_path}"
    d = load_agent_definition(backwards_path)
    assert d.tools == ()
    assert d.tools_unspecified is False
    # At runtime: no tools.
    agent = Agent(config=Config(), agent_definition=d)
    assert list(agent.tools.names) == []


class TestDocstringAgreement:
  """Criterion 11: docstrings agree with code in core/__init__.py, schema.py, loader.py."""

  def test_filter_tools_docstring_describes_three_branches(self) -> None:
    """_filter_tools_by_definition docstring documents the three Option C branches."""
    doc = Agent._filter_tools_by_definition.__doc__ or ""
    assert "tools_unspecified=True" in doc
    assert "tools_unspecified=False" in doc
    assert "agent_tools_default_granted" in doc
    assert "no tools" in doc.lower() or "clear the registry" in doc.lower()

  def test_schema_tools_field_documents_unspecified(self) -> None:
    """AgentDefinition.tools field docstring mentions tools_unspecified semantics."""
    from yoker.agents.schema import AgentDefinition as AD

    doc = AD.__doc__ or ""
    assert "tools_unspecified" in doc
    assert "all config-enabled tools" in doc or "all tools" in doc.lower()

  def test_loader_handles_present_vs_missing_keys(self) -> None:
    """Loader docstring/comments distinguish missing key from present-null."""
    from yoker.agents import loader

    src = inspect.getsource(loader.parse_agent_definition)
    assert '"tools" not in frontmatter' in src
    assert "agent_tools_explicit_null_treated_as_empty" in src


class TestNoRegression:
  """Criterion 12: no regression for explicit-tool filtering and namespace handling."""

  def test_explicit_filter_still_filters(self) -> None:
    """tools=("read",) keeps only read-related tools (existing behavior)."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=("read",))
    agent = Agent(config=Config(), agent_definition=d)
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is None
    assert agent.tools.get("yoker:write") is None

  def test_case_insensitive_filter_still_works(self) -> None:
    """Built-in tools are matched case-insensitively from agent definitions."""
    d = AgentDefinition(
      simple_name="test-agent", description="d", tools=("Read", "LIST", "Yoker:write")
    )
    agent = Agent(config=Config(), agent_definition=d)
    assert agent.tools.get("yoker:read") is not None
    assert agent.tools.get("yoker:list") is not None
    assert agent.tools.get("yoker:write") is not None
    assert agent.tools.get("yoker:update") is None

  def test_namespaced_tools_preserved(self) -> None:
    """Namespaced tool references are preserved verbatim (no re-namespacing)."""
    d = AgentDefinition(simple_name="test-agent", description="d", tools=("yoker:read",))
    assert d.tools == ("yoker:read",)
