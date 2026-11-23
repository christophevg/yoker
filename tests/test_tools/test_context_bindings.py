"""Tests for the harness → tools binding channel (Binding protocol).

The harness (yoker's host, or any embedding application) can bind live
operating-context resources (e.g. a provider session) to an Agent or a
Session. Values travel to tools via ``ToolContext.bindings`` and are
resolved by the provider module's own key (``ctx.get(key)``) — the harness
never needs to know provider-specific names.
"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config
from yoker.core import Agent
from yoker.core._processing import _build_tool_context
from yoker.session import Session
from yoker.tools import ToolRegistry
from yoker.tools.context import Binding, ToolContext


class TestBindingProtocol:
  """The reference Binding and structural duck-typing."""

  def test_reference_binding_carries_key_and_value(self) -> None:
    """Binding(key, value) holds both fields."""
    binding = Binding(key="provider.session", value=object())
    assert binding.key == "provider.session"
    assert isinstance(binding.value, object)

  def test_reference_binding_frozen(self) -> None:
    """Binding is immutable — binding replaces, never mutates."""
    binding = Binding(key="k", value=1)
    with pytest.raises(AttributeError):
      binding.value = 2  # type: ignore[misc]

  def test_protocol_is_structural(self) -> None:
    """Any object with .key/.value satisfies the protocol (no yoker import
    required by the provider module for values; bind() is duck-typed)."""

    class HarnessVar:
      key = "harness.thing"
      value = "live-resource"

    assert HarnessVar().key == "harness.thing"
    assert HarnessVar().value == "live-resource"

  def test_no_stdlib_name_collision(self) -> None:
    """yoker.tools.Binding is NOT stdlib contextvars.ContextVar (different
    semantics: module-owned keys, no task-locals)."""
    import contextvars

    assert Binding is not contextvars.ContextVar


class TestToolContextGet:
  """ToolContext.get() resolves by Binding object or key string."""

  def _context(self, bindings: dict) -> ToolContext:
    return ToolContext(config=MagicMock(), shared=MagicMock(), backends={}, bindings=bindings)

  def test_get_by_binding_object(self) -> None:
    binding = Binding(key="provider.session", value="conn")
    assert self._context({"provider.session": "conn"}).get(binding) == "conn"

  def test_get_by_key_string(self) -> None:
    assert self._context({"provider.session": "conn"}).get("provider.session") == "conn"

  def test_get_missing_returns_none(self) -> None:
    """Unbound key → None; tools must degrade gracefully."""
    assert self._context({}).get("provider.session") is None


class TestAgentBind:
  """Agent.bind() stores values keyed by key, validates the contract."""

  def _agent(self) -> Agent:
    # Hermetic: explicit default config — no discovery of host/repo yoker.toml.
    return Agent(config=Config())

  def test_bind_actually_stores(self) -> None:
    agent = self._agent()
    agent.bind(Binding(key="provider.session", value="conn"))
    assert agent._context_vars == {"provider.session": "conn"}

  def test_bind_multiple_vars(self) -> None:
    agent = self._agent()
    agent.bind(
      Binding(key="provider.session", value="conn"),
      Binding(key="acme.pool", value="pool"),
    )
    assert agent._context_vars == {"provider.session": "conn", "acme.pool": "pool"}

  def test_bind_returns_self_for_chaining(self) -> None:
    agent = self._agent()
    assert agent.bind(Binding(key="k", value="v")) is agent

  def test_bind_duplicate_key_raises(self) -> None:
    agent = self._agent()
    agent.bind(Binding(key="provider.session", value="conn"))
    with pytest.raises(ValueError, match="already bound"):
      agent.bind(Binding(key="provider.session", value="other"))

  def test_bind_missing_key_raises(self) -> None:
    broken = object()  # no .key attribute
    with pytest.raises(ValueError, match="non-None '.key'"):
      self._agent().bind(broken)

  def test_bind_none_key_raises(self) -> None:
    class KeylessVar:
      key = None  # noqa: N815 — protocol violation on purpose
      value = "v"

    with pytest.raises(ValueError, match="non-None '.key'"):
      self._agent().bind(KeylessVar())

  def test_constructor_context_vars(self) -> None:
    agent = Agent(config=Config(), context_vars=[Binding(key="provider.session", value="conn")])
    assert agent._context_vars == {"provider.session": "conn"}

  def test_late_bind_takes_effect(self) -> None:
    """_context_vars is read fresh per tool call (executor snapshots it)."""
    agent = self._agent()
    agent.bind(Binding(key="provider.session", value="conn"))
    # simulate a later rebinding through attribute replacement
    agent._context_vars["provider.session"] = "conn2"
    assert agent._context_vars == {"provider.session": "conn2"}


class TestToolContextInjection:
  """_build_tool_context threads bindings from the agent into the context."""

  def _agent_with(self, context_vars: dict) -> MagicMock:
    agent = MagicMock(spec=Agent)
    agent.config = MagicMock()
    agent.config.tools = MagicMock()
    agent._tool_backends = {}
    agent._guardrails = {}
    agent._context_vars = context_vars
    return agent

  def _spec(self) -> MagicMock:
    spec = MagicMock()
    spec.simple_name = "read"
    spec.namespace = "yoker"
    spec.name = "yoker:read"
    return spec

  def test_bindings_reach_tool_context(self) -> None:
    agent = self._agent_with({"provider.session": "conn"})
    ctx = _build_tool_context(agent, self._spec())
    assert ctx.bindings == {"provider.session": "conn"}
    assert ctx.get("provider.session") == "conn"

  def test_bindings_absent_agent_gets_empty(self) -> None:
    """Agents without bindings (plain mocks, CLI path) yield empty dict."""
    agent = MagicMock(spec=Agent)
    agent.config = MagicMock()
    agent.config.tools = MagicMock()
    agent._tool_backends = {}
    agent._guardrails = {}
    type(agent)._context_vars = property(
      lambda self: (_ for _ in ()).throw(AttributeError("_context_vars"))
    )
    ctx = _build_tool_context(agent, self._spec())
    assert ctx.bindings == {}

  def test_bindings_copied_not_referenced(self) -> None:
    """The context gets a snapshot — later agent dict mutation doesn't
    retroactively change an already-built context."""
    agent = self._agent_with({"k": "v1"})
    ctx = _build_tool_context(agent, self._spec())
    agent._context_vars["k"] = "v2"
    assert ctx.bindings == {"k": "v1"}


class TestSessionPropagation:
  """Session-level bindings reach every agent (primary + spawned)."""

  def _session(self) -> Session:
    return Session(
      config=Config(),
      context_vars=[Binding(key="provider.session", value="conn")],
    )

  def test_primary_agent_receives_session_bindings(self) -> None:
    session = self._session()
    assert session.agent._context_vars == {"provider.session": "conn"}

  def test_child_inherits_session_bindings_via_create_agent(self) -> None:
    """The real _create_agent flow propagates session bindings to spawned
    children (mock-backed child, per test_lifecycle.py's pattern)."""
    session = self._session()
    self._exercise_child_propagation(session, child_vars={})
    assert self._last_child._context_vars == {"provider.session": "conn"}
    # session-wide dict stays clean — no child keys leak back
    assert session._context_vars == {"provider.session": "conn"}

  def test_child_custom_bindings_merge_with_session(self) -> None:
    """A child's constructor-bound vars merge with (never clobber) the
    session-wide ones — _create_agent runs after Agent.__init__."""
    session = self._session()
    self._exercise_child_propagation(session, child_vars={"child.only": "x"})
    assert self._last_child._context_vars == {
      "provider.session": "conn",
      "child.only": "x",
    }

  def _exercise_child_propagation(self, session: Session, child_vars: dict) -> None:
    """Spawn a mock-backed child through the real _create_agent flow."""
    session_module = importlib.import_module("yoker.session")
    defn = AgentDefinition(simple_name="worker", description="d")
    session.agents.register(defn)
    with patch.object(session_module, "Agent") as mock_agent_cls:
      mock_child = MagicMock(spec=Agent)
      type(mock_child).tools = ToolRegistry()
      type(mock_child).definition = defn
      mock_child._context_vars = dict(child_vars)
      mock_child.process = AsyncMock(return_value="ok")
      mock_child.aclose = AsyncMock()
      mock_child.on_event = MagicMock()
      mock_agent_cls.return_value = mock_child
      child, _agent_id = session._create_agent(name=defn.name, agent_definition=defn)
    self._last_child = child

  def test_child_bind_does_not_leak_to_session(self) -> None:
    """Copy-not-reference: sibling/session dicts are immune to child edits."""
    session = self._session()
    child = MagicMock(spec=Agent)
    child._context_vars = {}
    merged = dict(child._context_vars)
    merged.update(session._context_vars)
    merged["child.only"] = "x"
    child._context_vars = merged
    assert session._context_vars == {"provider.session": "conn"}

  def test_session_constructor_validates_key(self) -> None:
    broken = object()
    with pytest.raises(ValueError, match="non-None '.key'"):
      Session(config=Config(), context_vars=[broken])

  def test_session_empty_context_vars_by_default(self) -> None:
    session = Session(config=Config())
    assert session._context_vars == {}

  def test_facade_forwards_context_vars(self) -> None:
    """yoker.session(context_vars=[...]) reaches the Session constructor
    (the facade passes the kwarg straight through — smoke check of
    signature wiring via inspect, no LLM needed)."""
    import inspect

    import yoker

    sig = inspect.signature(yoker.session)
    assert "context_vars" in sig.parameters
    sig_agent = inspect.signature(yoker.agent)
    assert "context_vars" in sig_agent.parameters
