"""Tests for ToolContext calling-agent identity (AgentInfo).

Covers the AgentInfo dataclass shape, the executor wiring in
`_build_tool_context` (session agent id, standalone fallback to the
definition name) and backward compatibility of direct ToolContext
constructions.
"""

import dataclasses
from types import SimpleNamespace

import pytest

from yoker.core._processing import _build_tool_context
from yoker.tools import AgentInfo, ToolContext


class _StubDefinition:
  """Minimal stand-in for AgentDefinition (name attribute only)."""

  def __init__(self, name: str) -> None:
    self.name = name


class _StubSpec:
  """Attribute stand-in for ToolSpec (only name/simple_name/namespace read)."""

  name = "echo"
  simple_name = "echo"
  namespace = None


class _StubAgent:
  """Attribute stand-in for Agent (only the fields the builder reads)."""

  _tool_backends: dict = {}
  _guardrails: dict = {}

  def __init__(self) -> None:
    self.config = SimpleNamespace(
      tools=SimpleNamespace(),
      tools_shared=None,
    )


def test_agent_info_is_frozen() -> None:
  """AgentInfo is an immutable (id, definition) pair."""
  info = AgentInfo(id="c3:researcher-2", definition="c3:researcher")
  assert info.id == "c3:researcher-2"
  assert info.definition == "c3:researcher"
  with pytest.raises(dataclasses.FrozenInstanceError):
    info.id = "other"  # type: ignore[misc]


def test_tool_context_agent_defaults_to_empty_placeholder() -> None:
  """Direct ToolContext construction stays valid: empty AgentInfo default."""
  ctx = ToolContext(config=None, shared=None, backends={})
  assert ctx.agent == AgentInfo(id="", definition="")
  assert ctx.session is None


def test_build_tool_context_session_agent_uses_runtime_id() -> None:
  """Session agents report their session-assigned runtime id."""

  agent = _StubAgent()
  agent._agent_id = "c3:researcher-2"  # type: ignore[attr-defined]
  agent.definition = _StubDefinition("c3:researcher")  # type: ignore[attr-defined]

  ctx = _build_tool_context(agent, _StubSpec())  # type: ignore[arg-type]
  assert ctx.agent == AgentInfo(id="c3:researcher-2", definition="c3:researcher")


def test_build_tool_context_standalone_agent_falls_back_to_definition_name() -> None:
  """Standalone agents (no _agent_id) fall back to the definition name."""

  agent = _StubAgent()
  agent.definition = _StubDefinition("yoker:primary")  # type: ignore[attr-defined]

  ctx = _build_tool_context(agent, _StubSpec())  # type: ignore[arg-type]
  assert ctx.agent == AgentInfo(id="yoker:primary", definition="yoker:primary")


def test_build_tool_context_degenerate_agent_yields_empty() -> None:
  """An agent without id or definition still yields a usable context."""

  agent = _StubAgent()

  ctx = _build_tool_context(agent, _StubSpec())  # type: ignore[arg-type]
  assert ctx.agent == AgentInfo(id="", definition="")
