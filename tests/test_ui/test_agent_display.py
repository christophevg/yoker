"""Tests for AgentDisplay — the read-only projection of Agent for UI."""

from yoker.ui.agent_display import AgentDisplay


class TestAgentDisplay:
  """Tests for the AgentDisplay frozen dataclass."""

  def test_basic_construction(self) -> None:
    """AgentDisplay can be constructed with required and optional fields."""
    ad = AgentDisplay(id="researcher", name="researcher")
    assert ad.id == "researcher"
    assert ad.name == "researcher"
    assert ad.color is None
    assert ad.model is None
    assert ad.description == ""

  def test_full_construction(self) -> None:
    """AgentDisplay accepts all fields."""
    ad = AgentDisplay(
      id="researcher-2",
      name="researcher",
      color="#FF6B35",
      model="llama3.2:latest",
      description="Research specialist",
    )
    assert ad.id == "researcher-2"
    assert ad.name == "researcher"
    assert ad.color == "#FF6B35"
    assert ad.model == "llama3.2:latest"
    assert ad.description == "Research specialist"

  def test_frozen(self) -> None:
    """AgentDisplay is frozen — mutation raises FrozenInstanceError."""
    ad = AgentDisplay(id="r", name="r")
    try:
      ad.id = "other"
      raise AssertionError("Should have raised FrozenInstanceError")
    except AttributeError:
      pass

  def test_equality(self) -> None:
    """Two AgentDisplay with same fields are equal."""
    a = AgentDisplay(id="r", name="r", color="blue")
    b = AgentDisplay(id="r", name="r", color="blue")
    assert a == b

  def test_inequality(self) -> None:
    """Different fields produce non-equal AgentDisplay."""
    a = AgentDisplay(id="r", name="r")
    b = AgentDisplay(id="r2", name="r")
    assert a != b
