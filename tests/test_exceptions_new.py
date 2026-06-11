"""Tests for exception classes."""

from yoker.exceptions import (
  AgentError,
  ConfigurationError,
  NetworkError,
  PluginError,
  SkillError,
  ToolError,
  YokerError,
)


class TestYokerError:
  """Tests for base YokerError exception."""

  def test_base_exception(self):
    """YokerError should be initialized with message."""
    error = YokerError("Test error")
    assert error.message == "Test error"
    assert str(error) == "Test error"
    assert isinstance(error, Exception)


class TestNetworkError:
  """Tests for NetworkError exception."""

  def test_network_error_basic(self):
    """NetworkError should have recoverable attribute."""
    error = NetworkError("Connection failed")
    assert error.message == "Connection failed"
    assert error.recoverable is True
    assert error.original_error is None

  def test_network_error_with_cause(self):
    """NetworkError should store original error."""
    original = ValueError("Original error")
    error = NetworkError("Connection failed", original_error=original)
    assert error.original_error is original
    assert "caused by: Original error" in str(error)

  def test_network_error_non_recoverable(self):
    """NetworkError can be marked as non-recoverable."""
    error = NetworkError("Fatal error", recoverable=False)
    assert error.recoverable is False


class TestToolError:
  """Tests for ToolError exception."""

  def test_tool_error(self):
    """ToolError should store tool name."""
    error = ToolError("read", "File not found")
    assert error.tool_name == "read"
    assert "read: File not found" in str(error)


class TestAgentError:
  """Tests for AgentError exception."""

  def test_agent_error(self):
    """AgentError should be initialized with message."""
    error = AgentError("Agent initialization failed")
    assert str(error) == "Agent initialization failed"
    assert isinstance(error, YokerError)


class TestSkillError:
  """Tests for SkillError exception."""

  def test_skill_error(self):
    """SkillError should store skill name."""
    error = SkillError("my-skill", "Skill execution failed")
    assert error.skill_name == "my-skill"
    assert "Skill 'my-skill': Skill execution failed" in str(error)


class TestExceptionHierarchy:
  """Tests for exception hierarchy."""

  def test_all_exceptions_inherit_from_yoker_error(self):
    """All custom exceptions should inherit from YokerError."""
    exceptions = [
      ConfigurationError("test", "value"),
      NetworkError("test"),
      PluginError("test-package", "test message"),
      ToolError("test", "test message"),
      AgentError("test message"),
      SkillError("test", "test message"),
    ]

    for exc in exceptions:
      assert isinstance(exc, YokerError)
      assert isinstance(exc, Exception)
