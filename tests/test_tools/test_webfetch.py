"""Tests for WebFetchTool implementation.

These tests verify the behavior of the WebFetchTool, including backend integration,
URL validation, SSRF protection, domain filtering, and error handling.
"""

from unittest.mock import MagicMock

import pytest

from yoker.config.schema import WebFetchToolConfig
from yoker.tools.base import ValidationResult
from yoker.tools.web_backend import WebFetchBackend
from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.web_types import FetchedContent, WebFetchError
from yoker.tools.webfetch import WebFetchTool


class TestWebFetchToolSchema:
  """Tests for WebFetchTool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A WebFetchTool instance
    When: Checking the tool name property
    Then: Returns 'web_fetch'
    """
    tool = WebFetchTool()
    assert tool.name == "web_fetch"

  def test_description(self) -> None:
    """
    Given: A WebFetchTool instance
    When: Checking the tool description property
    Then: Returns description mentioning web fetch
    """
    tool = WebFetchTool()
    assert "fetch" in tool.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A WebFetchTool instance
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with url, content_type, and max_size_kb parameters
    """
    tool = WebFetchTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    assert "parameters" in schema["function"]
    params = schema["function"]["parameters"]["properties"]
    assert "url" in params
    assert "content_type" in params
    assert "max_size_kb" in params

  def test_schema_url_required(self) -> None:
    """
    Given: The WebFetchTool schema
    When: Checking required parameters
    Then: 'url' is required, 'content_type' and 'max_size_kb' are optional
    """
    tool = WebFetchTool()
    schema = tool.get_schema()
    required = schema["function"]["parameters"]["required"]
    assert "url" in required

  def test_schema_content_type_enum(self) -> None:
    """
    Given: The WebFetchTool schema
    When: Checking content_type parameter
    Then: Has enum constraint with 'markdown', 'text', 'html' values
    """
    tool = WebFetchTool()
    schema = tool.get_schema()
    content_type = schema["function"]["parameters"]["properties"]["content_type"]
    assert "enum" in content_type
    assert set(content_type["enum"]) == {"markdown", "text", "html"}

  def test_schema_max_size_kb_bounds(self) -> None:
    """
    Given: The WebFetchTool schema
    When: Checking max_size_kb parameter
    Then: Has minimum=1 and maximum=10240 constraints
    """
    tool = WebFetchTool()
    schema = tool.get_schema()
    max_size = schema["function"]["parameters"]["properties"]["max_size_kb"]
    assert max_size["minimum"] == 1
    assert max_size["maximum"] == 10240


class TestWebFetchToolExecution:
  """Tests for WebFetchTool execute method."""

  def test_execute_returns_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with mocked backend
    When: Executing a valid URL fetch
    Then: Returns ToolResult with fetched content
    """
    tool = WebFetchTool(backend=mock_backend)
    result = tool.execute(url="https://example.com")
    assert result.success
    assert "content" in result.result

  def test_execute_with_default_content_type(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with mocked backend
    When: Executing fetch without content_type parameter
    Then: Uses default content_type='markdown'
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com")
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["content_type"] == "markdown"

  def test_execute_with_custom_content_type(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with mocked backend
    When: Executing fetch with content_type='text'
    Then: Passes content_type='text' to backend
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", content_type="text")
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["content_type"] == "text"

  def test_execute_with_custom_max_size(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with mocked backend
    When: Executing fetch with max_size_kb=5120
    Then: Passes max_size_kb=5120 to backend
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", max_size_kb=5120)
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["max_size_kb"] == 5120

  def test_execute_url_required(self) -> None:
    """
    Given: A WebFetchTool execute call without url
    When: Calling execute without url parameter
    Then: Returns error ToolResult
    """
    tool = WebFetchTool()
    result = tool.execute()
    assert not result.success
    assert "required" in result.error.lower()

  def test_execute_empty_url_rejected(self) -> None:
    """
    Given: A WebFetchTool execute call with empty url
    When: Calling execute with url=""
    Then: Returns error ToolResult
    """
    tool = WebFetchTool()
    result = tool.execute(url="")
    assert not result.success
    assert "required" in result.error.lower()

  def test_execute_whitespace_url_rejected(self) -> None:
    """
    Given: A WebFetchTool execute call with whitespace-only url
    When: Calling execute with url="   "
    Then: Returns error ToolResult
    """
    tool = WebFetchTool()
    result = tool.execute(url="   ")
    assert not result.success
    assert "empty" in result.error.lower() or "required" in result.error.lower()

  def test_execute_clamps_max_size(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with max_size_kb=20000 (exceeds maximum)
    When: Executing fetch
    Then: Clamps max_size_kb to 10240
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", max_size_kb=20000)
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["max_size_kb"] == 10240

  def test_execute_invalid_content_type_defaults(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with invalid content_type='pdf'
    When: Executing fetch
    Then: Defaults to content_type='markdown'
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", content_type="pdf")
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["content_type"] == "markdown"

  def test_execute_guardrail_validation_failure(self) -> None:
    """
    Given: A WebFetchTool with guardrail that rejects URL
    When: Executing fetch with blocked URL
    Then: Returns error ToolResult without calling backend
    """
    guardrail = MagicMock(spec=WebGuardrail)
    guardrail.validate_url.return_value = ValidationResult(
      valid=False, reason="Domain is blocked: internal.local"
    )
    tool = WebFetchTool(backend=None, guardrail=guardrail)
    result = tool.execute(url="https://internal.local/data")
    assert not result.success
    assert "blocked" in result.error.lower()

  def test_execute_strips_url_whitespace(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with url containing leading/trailing whitespace
    When: Executing fetch
    Then: Strips whitespace before validation
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="  https://example.com  ")
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["url"] == "https://example.com"


class TestWebFetchToolBackendIntegration:
  """Tests for WebFetchTool backend integration."""

  def test_backend_receives_valid_parameters(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchTool with mocked backend
    When: Executing fetch with valid parameters
    Then: Backend.fetch() receives validated url, content_type, and max_size_kb
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", content_type="text", max_size_kb=1024)
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["url"] == "https://example.com"
    assert call_args.kwargs["content_type"] == "text"
    assert call_args.kwargs["max_size_kb"] == 1024

  def test_backend_error_returns_error_result(self, mock_backend_error: MagicMock) -> None:
    """
    Given: A backend that raises WebFetchError
    When: Executing fetch
    Then: Returns error ToolResult with backend error message
    """
    tool = WebFetchTool(backend=mock_backend_error)
    result = tool.execute(url="https://example.com")
    assert not result.success
    assert "test" in result.error.lower()

  def test_backend_timeout_returns_error_result(self, mock_backend_timeout: MagicMock) -> None:
    """
    Given: A backend that times out
    When: Executing fetch
    Then: Returns error ToolResult with timeout message
    """
    tool = WebFetchTool(backend=mock_backend_timeout)
    result = tool.execute(url="https://example.com")
    assert not result.success
    assert "timeout" in result.error.lower()

  def test_backend_connection_error_returns_error_result(
    self, mock_backend_connection_error: MagicMock
  ) -> None:
    """
    Given: A backend that raises connection error
    When: Executing fetch
    Then: Returns error ToolResult with connection error message
    """
    tool = WebFetchTool(backend=mock_backend_connection_error)
    result = tool.execute(url="https://example.com")
    assert not result.success
    assert "connect" in result.error.lower()

  def test_backend_size_limit_error(self, mock_backend_size_error: MagicMock) -> None:
    """
    Given: A backend that raises size limit error
    When: Executing fetch
    Then: Returns error ToolResult with size limit message
    """
    tool = WebFetchTool(backend=mock_backend_size_error)
    result = tool.execute(url="https://example.com/large")
    assert not result.success
    assert "size" in result.error.lower()


class TestWebFetchToolResultFormat:
  """Tests for WebFetchTool result formatting."""

  def test_success_result_format(self, mock_backend: MagicMock) -> None:
    """
    Given: A successful web fetch
    When: Checking the ToolResult
    Then: success=True, result contains url, title, content, content_type, source, metadata
    """
    tool = WebFetchTool(backend=mock_backend)
    result = tool.execute(url="https://example.com")
    assert result.success
    assert "url" in result.result
    assert "title" in result.result
    assert "content" in result.result
    assert "content_type" in result.result
    assert "source" in result.result
    assert "metadata" in result.result

  def test_error_result_format(self) -> None:
    """
    Given: A failed web fetch
    When: Checking the ToolResult
    Then: success=False, result is empty, error contains message
    """
    tool = WebFetchTool(backend=None)
    result = tool.execute(url="https://example.com")
    assert not result.success
    assert result.result == {}
    assert result.error is not None

  def test_result_includes_metadata(self, mock_backend: MagicMock) -> None:
    """
    Given: A successful web fetch
    When: Checking the ToolResult
    Then: result contains metadata dict with size_kb
    """
    tool = WebFetchTool(backend=mock_backend)
    result = tool.execute(url="https://example.com")
    assert "metadata" in result.result
    assert "size_kb" in result.result["metadata"]

  def test_result_content_type_matches_request(self, mock_backend: MagicMock) -> None:
    """
    Given: A fetch request with content_type='text'
    When: Checking the ToolResult
    Then: result['content_type'] matches requested format
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com", content_type="text")
    # Verify the backend was called with the correct content_type
    call_args = mock_backend.fetch.call_args
    assert call_args.kwargs["content_type"] == "text"


class TestWebFetchToolConfiguration:
  """Tests for WebFetchTool configuration."""

  def test_default_backend_is_none(self) -> None:
    """
    Given: Creating WebFetchTool without explicit backend
    When: Checking backend type
    Then: Backend is None (requires explicit configuration)
    """
    tool = WebFetchTool()
    assert tool._backend is None

  def test_custom_backend_used(self, mock_backend: MagicMock) -> None:
    """
    Given: Creating WebFetchTool with custom backend
    When: Executing fetch
    Then: Uses provided backend instead of default
    """
    tool = WebFetchTool(backend=mock_backend)
    tool.execute(url="https://example.com")
    mock_backend.fetch.assert_called_once()

  def test_no_backend_returns_error(self) -> None:
    """
    Given: WebFetchTool without backend configured
    When: Executing fetch
    Then: Returns error about missing backend
    """
    tool = WebFetchTool()
    result = tool.execute(url="https://example.com")
    assert not result.success
    assert "backend" in result.error.lower()

  def test_guardrail_from_config(self) -> None:
    """
    Given: WebFetchToolConfig with domain restrictions
    When: Creating WebFetchTool with config
    Then: Guardrail is configured with domain restrictions
    """
    config = WebFetchToolConfig(
      domain_blocklist=("*.internal", "*.local"),
      require_https=True,
    )
    guardrail = WebGuardrail(
      config=WebGuardrailConfig(
        domain_blocklist=config.domain_blocklist,
        require_https=config.require_https,
      )
    )
    tool = WebFetchTool(backend=None, guardrail=guardrail)
    result = tool.execute(url="https://internal.local/data")
    assert not result.success
    assert "blocked" in result.error.lower()


class TestWebFetchToolSecurity:
  """Tests for WebFetchTool security features."""

  # SSRF Protection Tests

  def test_execute_private_ipv4_blocked(self, mock_guardrail_ssrf: MagicMock) -> None:
    """
    Given: A URL pointing to private IPv4 address (192.168.1.1)
    When: Executing fetch
    Then: Returns error about private IP blocked
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_ssrf)
    result = tool.execute(url="http://192.168.1.1/secret")
    assert not result.success
    assert "ssrf" in result.error.lower() or "private" in result.error.lower()

  def test_execute_private_ipv4_loopback_blocked(self, mock_guardrail_ssrf: MagicMock) -> None:
    """
    Given: A URL pointing to loopback address (127.0.0.1)
    When: Executing fetch
    Then: Returns error about private IP blocked
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_ssrf)
    result = tool.execute(url="http://127.0.0.1/admin")
    assert not result.success
    assert "ssrf" in result.error.lower() or "private" in result.error.lower()

  def test_execute_private_ipv6_blocked(self, mock_guardrail_ssrf: MagicMock) -> None:
    """
    Given: A URL pointing to private IPv6 address (::1)
    When: Executing fetch
    Then: Returns error about private IP blocked
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_ssrf)
    result = tool.execute(url="http://[::1]:8080/")
    assert not result.success
    assert "ssrf" in result.error.lower() or "private" in result.error.lower()

  def test_execute_metadata_endpoint_blocked(self, mock_guardrail_ssrf: MagicMock) -> None:
    """
    Given: A URL pointing to cloud metadata endpoint (169.254.169.254)
    When: Executing fetch
    Then: Returns error about metadata endpoint blocked
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_ssrf)
    result = tool.execute(url="http://169.254.169.254/latest/")
    assert not result.success
    assert "ssrf" in result.error.lower() or "metadata" in result.error.lower()

  def test_execute_localhost_blocked(self, mock_guardrail_ssrf: MagicMock) -> None:
    """
    Given: A URL pointing to localhost
    When: Executing fetch
    Then: Returns error about SSRF blocked
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_ssrf)
    result = tool.execute(url="http://localhost/admin")
    assert not result.success
    assert "ssrf" in result.error.lower() or "private" in result.error.lower()

  # Domain Filtering Tests

  def test_execute_domain_blocklist(self, mock_guardrail_blocked: MagicMock) -> None:
    """
    Given: A URL with domain in blocklist (*.internal)
    When: Executing fetch
    Then: Returns error about blocked domain
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_blocked)
    result = tool.execute(url="https://internal.local/data")
    assert not result.success
    assert "blocked" in result.error.lower()

  def test_execute_domain_allowlist_not_present(self, mock_guardrail_allowlist: MagicMock) -> None:
    """
    Given: A URL with domain not in allowlist
    When: Executing fetch
    Then: Returns error about domain not allowed
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_allowlist)
    result = tool.execute(url="https://example.com/data")
    assert not result.success
    assert "allowlist" in result.error.lower() or "not in" in result.error.lower()

  def test_execute_domain_allowlist_present(self, mock_backend: MagicMock) -> None:
    """
    Given: A URL with domain in allowlist
    When: Executing fetch
    Then: Proceeds with fetch
    """
    guardrail = MagicMock(spec=WebGuardrail)
    guardrail.validate_url.return_value = ValidationResult(valid=True)
    tool = WebFetchTool(backend=mock_backend, guardrail=guardrail)
    result = tool.execute(url="https://allowed.com/data")
    assert result.success

  # Scheme Validation Tests

  def test_execute_http_scheme_blocked_when_https_required(
    self, mock_guardrail_https: MagicMock
  ) -> None:
    """
    Given: A HTTP URL when require_https=True
    When: Executing fetch
    Then: Returns error about HTTPS required
    """
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail_https)
    result = tool.execute(url="http://example.com/")
    assert not result.success
    assert "https" in result.error.lower()

  def test_execute_https_scheme_allowed(self, mock_backend: MagicMock) -> None:
    """
    Given: A HTTPS URL
    When: Executing fetch
    Then: Proceeds with fetch
    """
    guardrail = MagicMock(spec=WebGuardrail)
    guardrail.validate_url.return_value = ValidationResult(valid=True)
    tool = WebFetchTool(backend=mock_backend, guardrail=guardrail)
    result = tool.execute(url="https://example.com/")
    assert result.success

  # URL Parsing Tests

  def test_execute_missing_scheme_rejected(self) -> None:
    """
    Given: A URL without scheme (example.com/path)
    When: Executing fetch
    Then: Returns error about missing scheme
    """
    tool = WebFetchTool(backend=None)
    result = tool.execute(url="example.com/path")
    assert not result.success
    # Should fail due to no host in urlparse

  def test_execute_missing_host_rejected(self) -> None:
    """
    Given: A URL without host (https:///path)
    When: Executing fetch
    Then: Returns error about missing host
    """
    guardrail = WebGuardrail()
    tool = WebFetchTool(backend=None, guardrail=guardrail)
    result = tool.execute(url="https:///path")
    assert not result.success
    assert "host" in result.error.lower()


class TestWebGuardrailURLValidation:
  """Tests for WebGuardrail.validate_url() method."""

  def test_validate_url_valid_https(self) -> None:
    """
    Given: A valid HTTPS URL
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=True)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate_url("https://example.com")
    assert result.valid

  def test_validate_url_invalid_url_format(self) -> None:
    """
    Given: An invalid URL format
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'Invalid URL')
    """
    guardrail = WebGuardrail()
    # URLs without host should fail
    result = guardrail.validate_url("https:///path")
    assert not result.valid
    assert "host" in result.reason.lower()

  def test_validate_url_http_blocked(self) -> None:
    """
    Given: An HTTP URL when require_https=True
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'HTTPS')
    """
    config = WebGuardrailConfig(require_https=True)
    guardrail = WebGuardrail(config=config)
    result = guardrail.validate_url("http://example.com")
    assert not result.valid
    assert "https" in result.reason.lower()

  def test_validate_url_missing_host(self) -> None:
    """
    Given: A URL without host
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'host')
    """
    guardrail = WebGuardrail()
    result = guardrail.validate_url("https:///path")
    assert not result.valid
    assert "host" in result.reason.lower()

  def test_validate_url_private_ip(self) -> None:
    """
    Given: A URL pointing to private IP
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'private IP')
    """
    guardrail = WebGuardrail()
    result = guardrail.validate_url("https://192.168.1.1/admin")
    assert not result.valid
    assert "private" in result.reason.lower()

  def test_validate_url_metadata_ip(self) -> None:
    """
    Given: A URL pointing to cloud metadata endpoint
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'private IP')
    """
    guardrail = WebGuardrail()
    result = guardrail.validate_url("https://169.254.169.254/latest")
    assert not result.valid
    # 169.254.169.254 is in link-local range 169.254.0.0/16, detected as private IP
    assert "private" in result.reason.lower() or "169.254.169.254" in result.reason

  def test_validate_url_domain_blocklist(self) -> None:
    """
    Given: A URL with domain in blocklist (*.internal)
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'blocked')
    """
    config = WebGuardrailConfig(domain_blocklist=("*.internal",))
    guardrail = WebGuardrail(config=config)
    # Use a URL that matches *.internal pattern
    result = guardrail.validate_url("https://api.internal/data")
    assert not result.valid
    assert "blocked" in result.reason.lower()

  def test_validate_url_domain_allowlist(self) -> None:
    """
    Given: A URL with domain not in allowlist
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=False, reason contains 'not in allowlist')
    """
    config = WebGuardrailConfig(domain_allowlist=("example.com",))
    guardrail = WebGuardrail(config=config)
    result = guardrail.validate_url("https://other.com/data")
    assert not result.valid
    assert "allowlist" in result.reason.lower()

  def test_validate_url_domain_allowlist_match(self) -> None:
    """
    Given: A URL with domain in allowlist
    When: Calling validate_url()
    Then: Returns ValidationResult(valid=True)
    """
    config = WebGuardrailConfig(domain_allowlist=("example.com",))
    guardrail = WebGuardrail(config=config)
    result = guardrail.validate_url("https://example.com/data")
    assert result.valid

  def test_check_ssrf_for_host_localhost(self) -> None:
    """
    Given: A hostname 'localhost'
    When: Calling _check_ssrf_for_host()
    Then: Returns error message about localhost blocked
    """
    guardrail = WebGuardrail()
    error = guardrail._check_ssrf_for_host("localhost")
    assert error is not None
    assert "localhost" in error.lower()

  def test_check_ssrf_for_host_private_ipv4(self) -> None:
    """
    Given: An IPv4 address in private range (10.0.0.1)
    When: Calling _check_ssrf_for_host()
    Then: Returns error message about private IP blocked
    """
    guardrail = WebGuardrail()
    error = guardrail._check_ssrf_for_host("10.0.0.1")
    assert error is not None
    assert "private" in error.lower()

  def test_check_ssrf_for_host_private_ipv6(self) -> None:
    """
    Given: An IPv6 address in private range (::1)
    When: Calling _check_ssrf_for_host()
    Then: Returns error message about private IP blocked
    """
    guardrail = WebGuardrail()
    error = guardrail._check_ssrf_for_host("::1")
    assert error is not None
    assert "private" in error.lower()

  def test_check_ssrf_for_host_public_ip(self) -> None:
    """
    Given: A public IP address (93.184.216.34)
    When: Calling _check_ssrf_for_host()
    Then: Returns None (no error)
    """
    guardrail = WebGuardrail()
    error = guardrail._check_ssrf_for_host("93.184.216.34")
    assert error is None


class TestWebFetchBackendProtocol:
  """Tests for WebFetchBackend protocol compliance."""

  def test_backend_protocol_fetch_method(self) -> None:
    """
    Given: A WebFetchBackend implementation
    When: Checking for fetch method
    Then: Method signature matches protocol (url, content_type, max_size_kb, timeout_seconds)
    """
    # Verify that OllamaWebFetchBackend implements the protocol
    from yoker.tools.web_backend import OllamaWebFetchBackend

    assert hasattr(OllamaWebFetchBackend, "fetch")

  def test_backend_protocol_returns_fetched_content(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebFetchBackend implementation
    When: Calling fetch()
    Then: Returns FetchedContent instance
    """
    assert isinstance(mock_backend.fetch.return_value, FetchedContent)

  def test_backend_protocol_raises_web_fetch_error(self, mock_backend_error: MagicMock) -> None:
    """
    Given: A WebFetchBackend implementation that fails
    When: Calling fetch() and it fails
    Then: Raises WebFetchError exception
    """
    assert isinstance(mock_backend_error.fetch.side_effect, WebFetchError)


class TestOllamaWebFetchBackend:
  """Tests for OllamaWebFetchBackend implementation."""

  def test_ollama_backend_init(self) -> None:
    """
    Given: An Ollama Client instance
    When: Creating OllamaWebFetchBackend
    Then: Initializes with client and default parameters
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    mock_client = MagicMock()
    backend = OllamaWebFetchBackend(client=mock_client)
    assert backend._client == mock_client
    assert backend._timeout_seconds == 30
    assert backend._max_size_kb == 2048

  def test_ollama_backend_fetch_calls_client(self, mock_ollama_client: MagicMock) -> None:
    """
    Given: An OllamaWebFetchBackend with mocked client
    When: Calling fetch(url)
    Then: Calls client.web_fetch(url)
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    backend = OllamaWebFetchBackend(client=mock_ollama_client)
    backend.fetch(url="https://example.com")
    mock_ollama_client.web_fetch.assert_called_once_with("https://example.com")

  def test_ollama_backend_fetch_returns_fetched_content(
    self, mock_ollama_client: MagicMock
  ) -> None:
    """
    Given: An OllamaWebFetchBackend with mocked client returning content
    When: Calling fetch(url)
    Then: Returns FetchedContent with extracted data
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    backend = OllamaWebFetchBackend(client=mock_ollama_client)
    result = backend.fetch(url="https://example.com")
    assert isinstance(result, FetchedContent)
    assert result.url == "https://example.com"
    assert result.source == "ollama"

  def test_ollama_backend_fetch_size_check(self, mock_ollama_client_large: MagicMock) -> None:
    """
    Given: An OllamaWebFetchBackend receiving content exceeding max_size_kb
    When: Calling fetch(url, max_size_kb=1024)
    Then: Raises WebFetchError with error_type='size_limit'
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    backend = OllamaWebFetchBackend(client=mock_ollama_client_large)
    with pytest.raises(WebFetchError) as exc_info:
      backend.fetch(url="https://example.com/large", max_size_kb=1)
    assert exc_info.value.error_type == "size_limit"

  def test_ollama_backend_fetch_connection_error(self, mock_ollama_client_error: MagicMock) -> None:
    """
    Given: An OllamaWebFetchBackend with connection error
    When: Calling fetch(url)
    Then: Raises WebFetchError with error_type='connection'
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    backend = OllamaWebFetchBackend(client=mock_ollama_client_error)
    with pytest.raises(WebFetchError) as exc_info:
      backend.fetch(url="https://example.com")
    assert exc_info.value.error_type == "connection"

  def test_ollama_backend_fetch_timeout(self, mock_ollama_client_timeout: MagicMock) -> None:
    """
    Given: An OllamaWebFetchBackend with timeout
    When: Calling fetch(url)
    Then: Raises WebFetchError with error_type='timeout'
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    backend = OllamaWebFetchBackend(client=mock_ollama_client_timeout)
    with pytest.raises(WebFetchError) as exc_info:
      backend.fetch(url="https://example.com")
    assert exc_info.value.error_type == "timeout"

  def test_ollama_backend_backend_name(self) -> None:
    """
    Given: An OllamaWebFetchBackend instance
    When: Checking backend_name
    Then: Returns 'ollama'
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    mock_client = MagicMock()
    backend = OllamaWebFetchBackend(client=mock_client)
    assert backend._backend_name == "ollama"

  def test_ollama_backend_default_timeout(self) -> None:
    """
    Given: An OllamaWebFetchBackend without explicit timeout
    When: Creating backend
    Then: Uses default timeout_seconds=30
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    mock_client = MagicMock()
    backend = OllamaWebFetchBackend(client=mock_client)
    assert backend._timeout_seconds == 30

  def test_ollama_backend_default_max_size(self) -> None:
    """
    Given: An OllamaWebFetchBackend without explicit max_size
    When: Creating backend
    Then: Uses default max_size_kb=2048
    """
    from yoker.tools.web_backend import OllamaWebFetchBackend

    mock_client = MagicMock()
    backend = OllamaWebFetchBackend(client=mock_client)
    assert backend._max_size_kb == 2048


class TestFetchedContent:
  """Tests for FetchedContent dataclass."""

  def test_fetched_content_creation(self) -> None:
    """
    Given: Valid content data
    When: Creating FetchedContent instance
    Then: All fields are set correctly
    """
    content = FetchedContent(
      url="https://example.com",
      title="Example",
      content="Test content",
      content_type="markdown",
      source="test",
      metadata={"size_kb": 1.0},
    )
    assert content.url == "https://example.com"
    assert content.title == "Example"
    assert content.content == "Test content"
    assert content.content_type == "markdown"
    assert content.source == "test"
    assert content.metadata == {"size_kb": 1.0}

  def test_fetched_content_to_dict(self) -> None:
    """
    Given: A FetchedContent instance
    When: Calling to_dict()
    Then: Returns dictionary with all fields
    """
    content = FetchedContent(
      url="https://example.com",
      title="Example",
      content="Test content",
      content_type="markdown",
      source="test",
      metadata={"size_kb": 1.0},
    )
    result = content.to_dict()
    assert result["url"] == "https://example.com"
    assert result["title"] == "Example"
    assert result["content"] == "Test content"
    assert result["content_type"] == "markdown"
    assert result["source"] == "test"
    assert result["metadata"] == {"size_kb": 1.0}

  def test_fetched_content_from_dict(self) -> None:
    """
    Given: A dictionary with content data
    When: Calling FetchedContent.from_dict()
    Then: Returns FetchedContent instance with correct fields
    """
    data = {
      "url": "https://example.com",
      "title": "Example",
      "content": "Test content",
      "content_type": "markdown",
      "source": "test",
      "metadata": {"size_kb": 1.0},
    }
    content = FetchedContent.from_dict(data)
    assert content.url == "https://example.com"
    assert content.title == "Example"
    assert content.content == "Test content"
    assert content.content_type == "markdown"
    assert content.source == "test"
    assert content.metadata == {"size_kb": 1.0}

  def test_fetched_content_frozen(self) -> None:
    """
    Given: A FetchedContent instance
    When: Attempting to modify a field
    Then: Raises error (frozen dataclass)
    """
    content = FetchedContent(
      url="https://example.com",
      title="Example",
      content="Test content",
    )
    with pytest.raises(AttributeError):
      content.url = "https://other.com"

  def test_fetched_content_default_values(self) -> None:
    """
    Given: A FetchedContent created with minimal fields
    When: Checking default values
    Then: content_type='markdown', source='unknown', metadata={}
    """
    content = FetchedContent(
      url="https://example.com",
      title="Example",
      content="Test content",
    )
    assert content.content_type == "markdown"
    assert content.source == "unknown"
    assert content.metadata == {}


class TestWebFetchError:
  """Tests for WebFetchError exception."""

  def test_web_fetch_error_creation(self) -> None:
    """
    Given: Error message and context
    When: Creating WebFetchError instance
    Then: All fields are set correctly
    """
    error = WebFetchError(
      message="Fetch failed",
      url="https://example.com",
      backend="test",
      error_type="timeout",
    )
    assert error.message == "Fetch failed"
    assert error.url == "https://example.com"
    assert error.backend == "test"
    assert error.error_type == "timeout"

  def test_web_fetch_error_str_with_backend(self) -> None:
    """
    Given: A WebFetchError with backend name
    When: Converting to string
    Then: Includes backend name in message
    """
    error = WebFetchError(
      message="Fetch failed",
      backend="ollama",
    )
    assert "[ollama]" in str(error)

  def test_web_fetch_error_str_without_backend(self) -> None:
    """
    Given: A WebFetchError without backend name
    When: Converting to string
    Then: Returns just the message
    """
    error = WebFetchError(message="Fetch failed")
    assert str(error) == "Fetch failed"

  def test_web_fetch_error_cause(self) -> None:
    """
    Given: A WebFetchError wrapping another exception
    When: Accessing cause field
    Then: Returns wrapped exception
    """
    original = ValueError("Original error")
    error = WebFetchError(
      message="Fetch failed",
      cause=original,
    )
    assert error.cause == original

  def test_web_fetch_error_types(self) -> None:
    """
    Given: Various error scenarios
    When: Creating WebFetchError with error_type
    Then: error_type field is set correctly
    """
    error_types = ["timeout", "connection", "size_limit", "ssrf", "invalid_url"]
    for error_type in error_types:
      error = WebFetchError(
        message="Error",
        error_type=error_type,
      )
      assert error.error_type == error_type


class TestWebFetchToolConfig:
  """Tests for WebFetchToolConfig dataclass."""

  def test_config_default_values(self) -> None:
    """
    Given: A WebFetchToolConfig created with defaults
    When: Checking field values
    Then: backend='ollama', timeout_seconds=30, max_size_kb=2048
    """
    config = WebFetchToolConfig()
    assert config.backend == "ollama"
    assert config.timeout_seconds == 30
    assert config.max_size_kb == 2048

  def test_config_backend_selection(self) -> None:
    """
    Given: A WebFetchToolConfig with backend='local'
    When: Checking backend field
    Then: Returns 'local'
    """
    config = WebFetchToolConfig(backend="local")
    assert config.backend == "local"

  def test_config_domain_lists(self) -> None:
    """
    Given: A WebFetchToolConfig with domain allowlist/blocklist
    When: Checking domain lists
    Then: Lists are correctly set as tuples
    """
    config = WebFetchToolConfig(
      domain_allowlist=("example.com", "*.test.com"),
      domain_blocklist=("*.internal", "*.local"),
    )
    assert config.domain_allowlist == ("example.com", "*.test.com")
    assert config.domain_blocklist == ("*.internal", "*.local")

  def test_config_ssrf_settings(self) -> None:
    """
    Given: A WebFetchToolConfig with SSRF settings
    When: Checking SSRF settings
    Then: block_private_cidrs, block_metadata_endpoints are set correctly
    """
    config = WebFetchToolConfig(
      block_private_cidrs=False,
      block_metadata_endpoints=False,
    )
    assert config.block_private_cidrs is False
    assert config.block_metadata_endpoints is False

  def test_config_https_requirement(self) -> None:
    """
    Given: A WebFetchToolConfig with require_https=False
    When: Checking require_https field
    Then: Returns False
    """
    config = WebFetchToolConfig(require_https=False)
    assert config.require_https is False

  def test_config_redirect_settings(self) -> None:
    """
    Given: A WebFetchToolConfig with redirect settings
    When: Checking redirect settings
    Then: follow_redirects, validate_redirects are set correctly
    """
    config = WebFetchToolConfig(
      follow_redirects=False,
      validate_redirects=False,
    )
    assert config.follow_redirects is False
    assert config.validate_redirects is False


# Fixtures


@pytest.fixture
def mock_backend() -> MagicMock:
  """Mock WebFetchBackend that returns sample content."""
  backend = MagicMock(spec=WebFetchBackend)
  backend.fetch.return_value = FetchedContent(
    url="https://example.com",
    title="Example Page",
    content="This is example content.",
    content_type="markdown",
    source="test",
    metadata={"size_kb": 1.5},
  )
  return backend


@pytest.fixture
def mock_backend_error() -> MagicMock:
  """Mock WebFetchBackend that raises error."""
  backend = MagicMock(spec=WebFetchBackend)
  backend.fetch.side_effect = WebFetchError(
    "Fetch failed",
    url="https://example.com",
    backend="test",
    error_type="connection",
  )
  return backend


@pytest.fixture
def mock_backend_timeout() -> MagicMock:
  """Mock WebFetchBackend that times out."""
  backend = MagicMock(spec=WebFetchBackend)
  backend.fetch.side_effect = WebFetchError(
    "Fetch timeout after 30s",
    url="https://example.com",
    backend="test",
    error_type="timeout",
  )
  return backend


@pytest.fixture
def mock_backend_connection_error() -> MagicMock:
  """Mock WebFetchBackend with connection error."""
  backend = MagicMock(spec=WebFetchBackend)
  backend.fetch.side_effect = WebFetchError(
    "Failed to connect to server",
    url="https://example.com",
    backend="test",
    error_type="connection",
  )
  return backend


@pytest.fixture
def mock_backend_size_error() -> MagicMock:
  """Mock WebFetchBackend with size limit error."""
  backend = MagicMock(spec=WebFetchBackend)
  backend.fetch.side_effect = WebFetchError(
    "Content size (5000KB) exceeds limit (2048KB)",
    url="https://example.com/large",
    backend="test",
    error_type="size_limit",
  )
  return backend


@pytest.fixture
def mock_guardrail_ssrf() -> MagicMock:
  """Mock WebGuardrail that blocks SSRF attempts."""
  guardrail = MagicMock(spec=WebGuardrail)
  guardrail.validate_url.return_value = ValidationResult(
    valid=False,
    reason="SSRF blocked: private IP address detected",
  )
  return guardrail


@pytest.fixture
def mock_guardrail_blocked() -> MagicMock:
  """Mock WebGuardrail that blocks domain."""
  guardrail = MagicMock(spec=WebGuardrail)
  guardrail.validate_url.return_value = ValidationResult(
    valid=False,
    reason="Domain is blocked: internal.local",
  )
  return guardrail


@pytest.fixture
def mock_guardrail_allowlist() -> MagicMock:
  """Mock WebGuardrail with allowlist."""
  guardrail = MagicMock(spec=WebGuardrail)
  guardrail.validate_url.return_value = ValidationResult(
    valid=False,
    reason="Domain not in allowlist: example.com",
  )
  return guardrail


@pytest.fixture
def mock_guardrail_wildcard() -> MagicMock:
  """Mock WebGuardrail with wildcard matching."""
  guardrail = MagicMock(spec=WebGuardrail)
  guardrail.validate_url.return_value = ValidationResult(valid=True)
  return guardrail


@pytest.fixture
def mock_guardrail_https() -> MagicMock:
  """Mock WebGuardrail that requires HTTPS."""
  guardrail = MagicMock(spec=WebGuardrail)
  guardrail.validate_url.return_value = ValidationResult(
    valid=False,
    reason="Only HTTPS URLs are allowed",
  )
  return guardrail


@pytest.fixture
def mock_ollama_client() -> MagicMock:
  """Mock Ollama Client for backend tests."""
  client = MagicMock()
  client.web_fetch.return_value = MagicMock(
    content="Example page content",
    title="Example Page",
  )
  return client


@pytest.fixture
def mock_ollama_client_large() -> MagicMock:
  """Mock Ollama Client returning large content."""
  client = MagicMock()
  client.web_fetch.return_value = MagicMock(
    content="x" * 3_000_000,  # 3MB content
    title="Large Page",
  )
  return client


@pytest.fixture
def mock_ollama_client_error() -> MagicMock:
  """Mock Ollama Client with connection error."""
  client = MagicMock()
  client.web_fetch.side_effect = ConnectionError("Failed to connect to Ollama")
  return client


@pytest.fixture
def mock_ollama_client_timeout() -> MagicMock:
  """Mock Ollama Client with timeout error."""
  client = MagicMock()
  client.web_fetch.side_effect = TimeoutError("Request timed out")
  return client
