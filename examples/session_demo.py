"""Session demo example for Yoker (MBI-007).

This example demonstrates the :class:`yoker.session.Session` construct —
the team-of-agents coordinator that owns agent lifecycle, registry,
recursion depth tracking, event aggregation, and inter-agent messaging.

It shows:

  - Constructing a :class:`Session` from a :class:`Config`.
  - Creating a primary :class:`Agent` via ``session.create_primary_agent``
    so it gets a runtime id and the Session-injected tools (``agent`` and
    ``send_message``).
  - Registering session-scoped event handlers that observe both
    session-level events (``SESSION_START``/``SESSION_END``,
    ``AGENT_SPAWNED``/``AGENT_FINISHED``) and aggregated sub-agent events
    (wrapped in :class:`yoker.events.SessionEvent` envelopes).
  - Programmatic ``session.spawn(...)`` — the canonical sub-agent API
    (Decision 8). The ``agent`` tool is a thin wrapper around this.
  - Programmatic ``session.send(...)`` — inter-agent messaging (D3).

The example requires a running backend (default: Ollama on
``http://localhost:11434``). When the backend is unreachable, a
``NetworkError`` is reported without crashing, mirroring the other
examples.

Run with:

    python examples/session_demo.py

"""

import asyncio
from dataclasses import replace
from pathlib import Path

from yoker import __version__
from yoker.config import AgentsConfig, Config, get_yoker_config
from yoker.events import (
  Event,
  SessionEvent,
)
from yoker.exceptions import NetworkError
from yoker.session import Session


def log_event(event: Event | SessionEvent) -> None:
  """Print every session event with its origin.

  Args:
    event: A bare session-level event (``SessionStartEvent``,
      ``AgentSpawnedEvent``, ...) or a :class:`SessionEvent` envelope
      wrapping an agent-emitted event tagged with ``agent_id``
      (PR #43 Clarification 9).
  """
  if isinstance(event, SessionEvent):
    print(f"[event] {event.event.type.name} (from {event.agent_id})")
  else:
    print(f"[event] {event.type.name}")


def _config_with_example_agents(config: Config) -> Config:
  """Ensure the session loads agent definitions from examples/agents.

  Args:
    config: The loaded Yoker config.

  Returns:
    A config whose ``agents.directories`` includes ``examples/agents``
    so the ``researcher`` agent definition is available to the session
    registry.
  """
  examples_agents = str(Path(__file__).parent / "agents")
  return replace(config, agents=AgentsConfig(directories=(examples_agents,)))


async def run_session_demo() -> None:
  """Construct a Session, register a primary agent, and exercise spawn/send."""
  config = _config_with_example_agents(get_yoker_config(cli=False))

  print(f"Yoker v{__version__}")
  print(f"Backend: {config.backend.provider} / {config.backend.config.model}")
  print(f"Session max_agents: {config.session.max_agents}")
  print(f"Event aggregation: {config.session.event_aggregation}")
  print()

  # Construct the Session (async context manager; D1/D4). The Session owns
  # the AgentRegistry, recursion depth tracking, and event aggregation.
  async with Session(config=config) as session:
    print(f"Session id: {session.id}")
    print(f"Available agent definitions: {', '.join(sorted(session.agents.names))}")
    print()

    # Register a session-scoped event handler. Session-level events
    # (SESSION_START, AGENT_SPAWNED, ...) reach this handler directly;
    # sub-agent events reach it wrapped in a SessionEvent envelope (D5,
    # PR #43 Clarification 9).
    session.on_event(log_event)

    # Construct the primary Agent via the Session. create_primary_agent
    # resolves the config-based agent definition (if any), shares the
    # session's backend, and registers the agent. The primary agent is
    # available via session.agent.
    agent = await session.create_primary_agent(
      config=config,
      console_logging=False,
    )
    print(f"Primary agent tools: {', '.join(sorted(agent.tools.names))}")
    print()

    # Programmatic sub-agent spawn (Decision 8): session.spawn returns a
    # reusable Agent (no prompt, no response). The caller drives the agent
    # via agent.process(...). The agent stays in the active map until
    # session.release(agent) is called (or the session exits).
    if "agents:researcher" in session.agents.names:
      print("Spawning 'researcher' sub-agent via session.spawn(...) ...")
      try:
        researcher = await session.spawn("researcher")
        response = await researcher.process("Summarize the README.md file in two sentences.")
        print(f"Response: {response}")
        print()

        # Inter-agent messaging (D3): send a follow-up message to the
        # spawned agent while it is still active. The Python API takes
        # Agent instances directly (the session resolves the ids for the
        # event payload internally).
        print("Sending follow-up message to researcher ...")
        try:
          reply = await session.send(
            to=researcher, from_=agent, content="What was the most surprising finding?"
          )
          print(f"Reply: {reply}")
        except ValueError as e:
          print(f"Expected (agent finished): {e}")
        finally:
          session.release(researcher)
      except NetworkError as e:
        print(f"Network error: {e}")
      except TimeoutError as e:
        print(f"Timeout: {e}")
    else:
      print(
        "Agent 'researcher' not in the registry; skipping spawn demo. "
        "Check that examples/agents/researcher.md is readable."
      )

  # SESSION_END is emitted on __aexit__ even if the body raised.
  print()
  print("Session closed.")


def main() -> None:
  """Entry point for the session demo example."""
  try:
    asyncio.run(run_session_demo())
  except KeyboardInterrupt:
    pass


if __name__ == "__main__":
  main()
