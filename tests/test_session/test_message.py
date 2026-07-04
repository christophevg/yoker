"""Tests for the Message dataclass (MBI-007 7.1.1 / 7.4.1)."""

from dataclasses import FrozenInstanceError

import pytest

from yoker.session import Message


class TestMessage:
  """Tests for the Message frozen dataclass."""

  def test_import_from_session(self) -> None:
    """from yoker.session import Message works."""
    from yoker.session import Message as ImportedMessage

    assert ImportedMessage is Message

  def test_basic_construction(self) -> None:
    """Message carries from_id, to_id, content."""
    msg = Message(from_id="a", to_id="b", content="hello")
    assert msg.from_id == "a"
    assert msg.to_id == "b"
    assert msg.content == "hello"

  def test_metadata_defaults_to_empty_dict(self) -> None:
    """metadata defaults to a fresh empty dict per instance."""
    msg = Message(from_id="a", to_id="b", content="hello")
    assert msg.metadata == {}

  def test_metadata_can_be_provided(self) -> None:
    """metadata can carry arbitrary key/value pairs."""
    msg = Message(from_id="a", to_id="b", content="hello", metadata={"priority": 1})
    assert msg.metadata == {"priority": 1}

  def test_metadata_default_is_per_instance(self) -> None:
    """Each instance gets its own metadata dict (no shared mutable default)."""
    a = Message(from_id="a", to_id="b", content="x")
    b = Message(from_id="a", to_id="b", content="y")
    a.metadata["k"] = "v"
    assert "k" not in b.metadata

  def test_message_is_frozen(self) -> None:
    """Message is a frozen dataclass — mutation raises FrozenInstanceError."""
    msg = Message(from_id="a", to_id="b", content="hello")
    with pytest.raises(FrozenInstanceError):
      msg.content = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
      msg.from_id = "c"  # type: ignore[misc]

  def test_message_has_four_fields(self) -> None:
    """Message has exactly from_id, to_id, content, metadata (D3)."""
    from dataclasses import fields

    names = {f.name for f in fields(Message)}
    assert names == {"from_id", "to_id", "content", "metadata"}
