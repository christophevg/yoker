"""Single-agent backward compatibility tests (MBI-007 7.9.7, PR #43 Clarification 1).

Verifies that:
  - Single-agent ``Agent`` works without a Session (first-class path).
  - Existing examples (``library_usage.py``, ``batch_mode.py``,
    ``research_workflow.py``) import cleanly without modification.
  - Old TOML files without a ``[session]`` section still load (strict
    superset — covered in ``test_config.py``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from yoker.agent import Agent
from yoker.config import Config

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


class TestSingleAgentWithoutSession:
  """Tests for the single-agent path (no Session wrapper)."""

  def test_agent_constructs_without_session(self) -> None:
    """Agent(config=...) works as a standalone single-agent chat loop."""
    agent = Agent(config=Config())
    assert agent._session is None
    assert agent._backend is not None
    # Tool registry is populated (default tools loaded via plugins).
    assert agent.tools.get("yoker:read") is not None

  @pytest.mark.asyncio
  async def test_agent_process_does_not_require_session(self) -> None:
    """agent.process() is callable on a standalone Agent (no session needed).

    We don't actually call a model here — we just confirm ``process`` is
    a callable coroutine on a standalone Agent. The single-agent path is
    a first-class primitive, not a compatibility shim (PR #43 Clarification 1).
    """
    agent = Agent(config=Config())
    assert callable(agent.process)

  def test_agent_event_handlers_work_without_session(self) -> None:
    """add_event_handler / remove_event_handler work on a standalone Agent."""
    agent = Agent(config=Config())
    received: list = []

    def handler(event) -> None:
      received.append(event)

    agent.add_event_handler(handler)
    assert handler in agent.get_event_handlers()
    agent.remove_event_handler(handler)
    assert handler not in agent.get_event_handlers()


class TestExistingExamplesLoad:
  """Existing examples must import without modification (7.9.7)."""

  def test_library_usage_imports(self) -> None:
    """examples/library_usage.py imports cleanly."""
    spec = importlib.util.spec_from_file_location(
      "example_library_usage", EXAMPLES_DIR / "library_usage.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
    assert hasattr(module, "log_events")

  def test_batch_mode_imports(self) -> None:
    """examples/batch_mode.py imports cleanly."""
    spec = importlib.util.spec_from_file_location(
      "example_batch_mode", EXAMPLES_DIR / "batch_mode.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "run_batch")
    assert hasattr(module, "main")

  def test_research_workflow_imports(self) -> None:
    """examples/research_workflow.py imports cleanly."""
    spec = importlib.util.spec_from_file_location(
      "example_research_workflow", EXAMPLES_DIR / "research_workflow.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "run_research")
    assert hasattr(module, "main")

  def test_session_demo_imports(self) -> None:
    """examples/session_demo.py (new in MBI-007) imports cleanly."""
    spec = importlib.util.spec_from_file_location(
      "example_session_demo", EXAMPLES_DIR / "session_demo.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
