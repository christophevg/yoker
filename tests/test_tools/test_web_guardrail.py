"""Tests for WebGuardrail security enforcement.

These tests verify the security guardrails for web tools, including SSRF protection,
domain allowlist/blocklist, query sanitization, and rate limiting.

SECURITY CRITICAL: These tests ensure the guardrails prevent security vulnerabilities.
"""

from unittest.mock import MagicMock

import pytest

from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig


class TestWebGuardrailSSRFProtection:
  """Tests for Server-Side Request Forgery (SSRF) protection.

  SECURITY CRITICAL: These tests ensure attackers cannot access internal network
  resources or cloud metadata endpoints through web search queries.
  """

  def test_blocks_cloud_metadata_ip(self) -> None:
    """
    Given: A query containing cloud metadata IP (169.254.169.254)
    When: Validating the query
    Then: Returns ValidationResult(valid=False) with SSRF block reason
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "site:169.254.169.254 data"})

    assert not result.valid
    assert "SSRF" in result.reason or "private" in result.reason.lower()

  def test_blocks_aws_metadata_ip_with_path(self) -> None:
    """
    Given: A query containing "169.254.169.254/latest/meta-data/"
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "169.254.169.254/latest/meta-data/"})

    assert not result.valid

  def test_blocks_private_ip_range_10(self) -> None:
    """
    Given: A query containing private IP (10.x.x.x)
    When: Validating the query
    Then: Returns validation failure with private IP block reason
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "10.0.0.1 admin panel"})

    assert not result.valid
    assert "SSRF" in result.reason or "private" in result.reason.lower()

  def test_blocks_private_ip_range_172_16(self) -> None:
    """
    Given: A query containing private IP (172.16.x.x - 172.31.x.x)
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "172.16.0.1 internal"})

    assert not result.valid

  def test_blocks_private_ip_range_192_168(self) -> None:
    """
    Given: A query containing private IP (192.168.x.x)
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "192.168.1.1 router"})

    assert not result.valid

  def test_blocks_localhost_ip(self) -> None:
    """
    Given: A query containing 127.0.0.1 or localhost
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "localhost:8080 api"})

    assert not result.valid

  def test_blocks_ipv4_mapped_ipv6_addresses(self) -> None:
    """
    Given: A query containing IPv4-mapped IPv6 addresses (::ffff:169.254.169.254)
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "::ffff:169.254.169.254"})

    assert not result.valid

  def test_blocks_ipv6_link_local(self) -> None:
    """
    Given: A query containing IPv6 link-local addresses (fe80::)
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "fe80::1 service"})

    assert not result.valid

  def test_blocks_url_encoded_ip_addresses(self) -> None:
    """
    Given: A query with URL-encoded IPs (%316%2e%3254%2e%3169%2e%3254)
    When: Validating the query
    Then: Decodes and blocks the IP address
    """
    guardrail = WebGuardrail()
    # URL-encoded "192.168.1.1"
    result = guardrail.validate("web_search", {"query": "%3192%2e168%2e1%2e1"})

    # Should detect and block (URL encoded form)
    # The guardrail should decode and check
    assert not result.valid

  def test_blocks_hex_encoded_ip_addresses(self) -> None:
    """
    Given: A query with hex-encoded IP (0xa9fea9fe)
    When: Validating the query
    Then: Decodes and blocks the IP address
    """
    guardrail = WebGuardrail()
    # 0xa9fea9fe = 169.254.169.254
    result = guardrail.validate("web_search", {"query": "0xa9fea9fe metadata"})

    assert not result.valid

  def test_blocks_decimal_ip_addresses(self) -> None:
    """
    Given: A query with decimal IP (2852039166)
    When: Validating the query
    Then: Converts and blocks the IP address
    """
    guardrail = WebGuardrail()
    # 2852039166 = 169.254.169.254
    result = guardrail.validate("web_search", {"query": "2852039166"})

    assert not result.valid


class TestWebGuardrailDomainWhitelist:
  """Tests for domain allowlist (whitelist) validation."""

  def test_allows_whitelisted_domain_exact(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["docs.python.org"]
    When: Validating query containing docs.python.org
    Then: Returns ValidationResult(valid=True)
    """
    config = WebGuardrailConfig(domain_allowlist=("docs.python.org",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:docs.python.org asyncio"})

    # Note: The guardrail checks domains extracted from query
    # If no domains extracted, it passes (allowlist only blocks non-matching domains)
    # This is a heuristic check
    assert result.valid

  def test_allows_whitelisted_domain_wildcard(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["*.github.com"]
    When: Validating query containing api.github.com
    Then: Returns validation success
    """
    config = WebGuardrailConfig(domain_allowlist=("*.github.com",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:api.github.com repos"})

    assert result.valid

  def test_allows_whitelisted_domain_nested_subdomain(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["*.github.com"]
    When: Validating query containing v1.api.github.com (nested subdomain)
    Then: Returns validation success
    """
    config = WebGuardrailConfig(domain_allowlist=("*.github.com",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:v1.api.github.com files"})

    # The nested subdomain (v1.api.github.com) should match the wildcard (*.github.com)
    assert result.valid

  def test_blocks_non_whitelisted_domain(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["docs.python.org"]
    When: Validating query containing example.com
    Then: Returns validation failure with domain not whitelisted reason
    """
    config = WebGuardrailConfig(domain_allowlist=("docs.python.org",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:example.com secrets"})

    assert not result.valid
    assert "whitelist" in result.reason.lower() or "domain" in result.reason.lower()

  def test_empty_allowlist_allows_all(self) -> None:
    """
    Given: A WebGuardrail with empty domain_allowlist
    When: Validating query containing any domain
    Then: Returns validation success (allows all domains)
    """
    config = WebGuardrailConfig(domain_allowlist=())
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:example.com content"})

    assert result.valid

  def test_whitelist_case_insensitive(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["Docs.Python.Org"]
    When: Validating query containing docs.python.org
    Then: Returns validation success (case-insensitive matching)
    """
    config = WebGuardrailConfig(domain_allowlist=("Docs.Python.Org",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:docs.python.org asyncio"})

    assert result.valid


class TestWebGuardrailDomainBlacklist:
  """Tests for domain blocklist (blacklist) validation."""

  def test_blocks_blacklisted_domain_exact(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["internal.company.com"]
    When: Validating query containing internal.company.com
    Then: Returns validation failure with domain blocked reason
    """
    config = WebGuardrailConfig(domain_blocklist=("internal.company.com",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:internal.company.com secrets"})

    assert not result.valid
    assert "blocked" in result.reason.lower()

  def test_blocks_blacklisted_domain_wildcard(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["*.internal"]
    When: Validating query containing secret.internal
    Then: Returns validation failure
    """
    config = WebGuardrailConfig(domain_blocklist=("*.internal",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:secret.internal data"})

    assert not result.valid

  def test_blocks_blacklisted_domain_nested_subdomain(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["*.local"]
    When: Validating query containing api.service.local
    Then: Returns validation failure
    """
    config = WebGuardrailConfig(domain_blocklist=("*.local",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:api.service.local api"})

    assert not result.valid

  def test_allows_non_blacklisted_domain(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["*.internal"]
    When: Validating query containing example.com
    Then: Returns validation success
    """
    config = WebGuardrailConfig(domain_blocklist=("*.internal",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:example.com public"})

    assert result.valid

  def test_blacklist_takes_precedence_over_whitelist(self) -> None:
    """
    Given: A WebGuardrail with domain_allowlist=["*.github.com"] and
           domain_blocklist=["api.github.com"]
    When: Validating query containing api.github.com
    Then: Returns validation failure (blocklist wins)
    """
    config = WebGuardrailConfig(
      domain_allowlist=("*.github.com",),
      domain_blocklist=("api.github.com",),
    )
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:api.github.com data"})

    assert not result.valid

  def test_blacklist_case_insensitive(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["*.INTERNAL"]
    When: Validating query containing secret.internal
    Then: Returns validation failure (case-insensitive matching)
    """
    config = WebGuardrailConfig(domain_blocklist=("*.INTERNAL",))
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "site:secret.internal data"})

    assert not result.valid

  def test_blocks_common_internal_domains(self) -> None:
    """
    Given: A WebGuardrail with domain_blocklist=["*.internal", "*.local", "*.localhost"]
    When: Validating query containing any internal domain
    Then: Returns validation failure
    """
    config = WebGuardrailConfig(domain_blocklist=("*.internal", "*.local", "*.localhost"))
    guardrail = WebGuardrail(config)

    for domain in ["secret.internal", "service.local", "test.localhost"]:
      result = guardrail.validate("web_search", {"query": f"site:{domain} data"})
      assert not result.valid


class TestWebGuardrailQuerySanitization:
  """Tests for query sanitization and content filtering."""

  def test_allows_env_file_queries(self) -> None:
    """
    Given: A query about .env files (documentation/tutorial search)
    When: Validating the query
    Then: Returns validation success (web search for .env tutorials is legitimate)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "how to read .env file in Python"})

    # Web search for .env tutorials is legitimate - not exposing actual secrets
    assert result.valid

  def test_blocks_password_with_value_queries(self) -> None:
    """
    Given: A query containing "password='actual_password'"
    When: Validating the query
    Then: Returns validation failure (attempting to search for actual secrets)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "password='secret123'"})

    assert not result.valid
    assert "sensitive" in result.reason.lower()

  def test_allows_password_tutorial_queries(self) -> None:
    """
    Given: A query about password handling (documentation/tutorial search)
    When: Validating the query
    Then: Returns validation success (web search for password tutorials is legitimate)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "how to hash passwords in Python"})

    # Web search for password tutorials is legitimate
    assert result.valid

  def test_blocks_api_key_queries(self) -> None:
    """
    Given: A query containing "api_key='actual_key'"
    When: Validating the query
    Then: Returns validation failure (attempting to search for actual secrets)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "api_key='abcd1234'"})

    assert not result.valid
    assert "sensitive" in result.reason.lower()

  def test_blocks_secret_queries(self) -> None:
    """
    Given: A query containing "secret='actual_secret'"
    When: Validating the query
    Then: Returns validation failure (attempting to search for actual secrets)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "secret='mysecret'"})

    assert not result.valid
    assert "sensitive" in result.reason.lower()

  def test_allows_credentials_tutorial_queries(self) -> None:
    """
    Given: A query about credentials (documentation/tutorial search)
    When: Validating the query
    Then: Returns validation success (web search for credential tutorials is legitimate)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "how to manage credentials in Python"})

    # Web search for credential tutorials is legitimate
    assert result.valid

  def test_enforces_query_length_limit(self) -> None:
    """
    Given: A query longer than max_query_length (default 500)
    When: Validating the query
    Then: Returns validation failure with length limit reason
    """
    config = WebGuardrailConfig(max_query_length=100)
    guardrail = WebGuardrail(config)
    long_query = "a" * 150
    result = guardrail.validate("web_search", {"query": long_query})

    assert not result.valid
    assert "length" in result.reason.lower()

  def test_allows_normal_length_query(self) -> None:
    """
    Given: A query shorter than max_query_length
    When: Validating the query
    Then: Returns validation success
    """
    config = WebGuardrailConfig(max_query_length=500)
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "python async best practices"})

    assert result.valid

  def test_strips_invisible_unicode_characters(self) -> None:
    """
    Given: A query containing zero-width characters (U+200B, U+200C, U+200D, U+FEFF)
    When: Validating the query
    Then: Strips invisible characters before validation
    """
    guardrail = WebGuardrail()
    # Query with zero-width space
    query_with_zwsp = "python​async"  # zero-width space between words
    result = guardrail.validate("web_search", {"query": query_with_zwsp})

    # Should still be valid after stripping
    assert result.valid

  def test_allows_normal_query(self) -> None:
    """
    Given: A normal search query
    When: Validating the query
    Then: Returns validation success
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "python async best practices"})

    assert result.valid


class TestWebGuardrailRateLimiting:
  """Tests for rate limiting enforcement."""

  def test_allows_first_request(self) -> None:
    """
    Given: A WebGuardrail with rate limiting configured
    When: Making the first request
    Then: Returns validation success
    """
    config = WebGuardrailConfig(requests_per_minute=10)
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "test"})

    assert result.valid

  def test_enforces_requests_per_minute_limit(self) -> None:
    """
    Given: A WebGuardrail with requests_per_minute=10
    When: Making the 11th request within a minute
    Then: Returns validation failure with rate limit reason
    """
    config = WebGuardrailConfig(requests_per_minute=5)
    guardrail = WebGuardrail(config)

    # Make 5 requests (should all succeed)
    for i in range(5):
      result = guardrail.validate("web_search", {"query": f"test {i}"})
      assert result.valid

    # 6th request should fail
    result = guardrail.validate("web_search", {"query": "test 6"})
    assert not result.valid
    assert "rate" in result.reason.lower()

  def test_enforces_requests_per_hour_limit(self) -> None:
    """
    Given: A WebGuardrail with requests_per_hour=100
    When: Making the 101st request within an hour
    Then: Returns validation failure
    """
    config = WebGuardrailConfig(requests_per_hour=5)
    guardrail = WebGuardrail(config)

    # Make 5 requests (should all succeed)
    for i in range(5):
      result = guardrail.validate("web_search", {"query": f"test {i}"})
      assert result.valid

    # 6th request should fail
    result = guardrail.validate("web_search", {"query": "test 6"})
    assert not result.valid

  def test_rate_limit_resets_after_minute(self) -> None:
    """
    Given: A WebGuardrail that has reached per-minute limit
    When: Waiting for the minute to pass
    Then: Allows requests again
    """
    config = WebGuardrailConfig(requests_per_minute=2)
    guardrail = WebGuardrail(config)

    # Make 2 requests
    guardrail.validate("web_search", {"query": "test 1"})
    guardrail.validate("web_search", {"query": "test 2"})

    # 3rd should fail
    result = guardrail.validate("web_search", {"query": "test 3"})
    assert not result.valid

    # Manually expire the rate limit by manipulating timestamps
    # This simulates time passing
    state = guardrail._rate_limits["default"]
    state.requests_per_minute = []  # Clear old timestamps

    # Should work again
    result = guardrail.validate("web_search", {"query": "test 4"})
    assert result.valid

  def test_rate_limit_tracks_per_user(self) -> None:
    """
    Given: A WebGuardrail with rate limiting
    When: Multiple users make requests
    Then: Rate limits are tracked separately per user
    """
    config = WebGuardrailConfig(requests_per_minute=2)
    guardrail = WebGuardrail(config)

    # User 1 makes 2 requests
    guardrail.validate("web_search", {"query": "test", "_user_id": "user1"})
    guardrail.validate("web_search", {"query": "test", "_user_id": "user1"})

    # User 1's 3rd request should fail
    result = guardrail.validate("web_search", {"query": "test", "_user_id": "user1"})
    assert not result.valid

    # User 2 should still be able to make requests
    result = guardrail.validate("web_search", {"query": "test", "_user_id": "user2"})
    assert result.valid

  def test_concurrent_request_limit(self) -> None:
    """
    Given: A WebGuardrail with max_concurrent_requests=5
    When: Making 6 concurrent requests
    Then: Returns validation failure for the 6th request
    """
    config = WebGuardrailConfig(max_concurrent_requests=2)
    guardrail = WebGuardrail(config)

    # Make 2 requests without releasing
    guardrail.validate("web_search", {"query": "test 1"})
    guardrail.validate("web_search", {"query": "test 2"})

    # 3rd should fail due to concurrent limit
    result = guardrail.validate("web_search", {"query": "test 3"})
    assert not result.valid

    # Release one
    guardrail.release_concurrent()

    # Should work again
    result = guardrail.validate("web_search", {"query": "test 4"})
    assert result.valid


class TestWebGuardrailConfiguration:
  """Tests for guardrail configuration."""

  def test_default_config_allows_all_domains(self) -> None:
    """
    Given: A WebGuardrail with default configuration
    When: Validating query containing any domain
    Then: Returns validation success (no domain restrictions)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "site:example.com test"})

    assert result.valid

  def test_default_config_has_sensible_limits(self) -> None:
    """
    Given: A WebGuardrail with default configuration
    When: Checking max_query_length, rate limits
    Then: Uses sensible defaults (500 char limit, 60/min, 1000/hour)
    """
    config = WebGuardrailConfig()
    guardrail = WebGuardrail(config)

    assert guardrail._config.max_query_length == 500
    assert guardrail._config.requests_per_minute == 60
    assert guardrail._config.requests_per_hour == 1000

  def test_custom_max_query_length(self) -> None:
    """
    Given: A WebGuardrailConfig with max_query_length=100
    When: Validating a 150 character query
    Then: Returns validation failure
    """
    config = WebGuardrailConfig(max_query_length=100)
    guardrail = WebGuardrail(config)
    result = guardrail.validate("web_search", {"query": "a" * 150})

    assert not result.valid

  def test_disabled_rate_limiting(self) -> None:
    """
    Given: A WebGuardrailConfig with rate limiting disabled
    When: Making many requests rapidly
    Then: Allows all requests (no rate limit enforced)
    """
    config = WebGuardrailConfig(
      requests_per_minute=0,
      requests_per_hour=0,
      max_concurrent_requests=0,
    )
    guardrail = WebGuardrail(config)

    # Make many requests - all should succeed
    for i in range(100):
      result = guardrail.validate("web_search", {"query": f"test {i}"})
      assert result.valid


class TestWebGuardrailEdgeCases:
  """Tests for edge cases and bypass attempts."""

  def test_empty_query_rejected(self) -> None:
    """
    Given: A WebGuardrail validating empty query ""
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": ""})

    assert not result.valid

  def test_whitespace_only_query_rejected(self) -> None:
    """
    Given: A WebGuardrail validating whitespace-only query "   "
    When: Validating the query
    Then: Returns validation failure
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "   "})

    assert not result.valid

  def test_allows_query_with_public_domain(self) -> None:
    """
    Given: A WebGuardrail validating query "python documentation"
    When: Validating the query
    Then: Returns validation success
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "python documentation"})

    assert result.valid

  def test_query_case_preserved(self) -> None:
    """
    Given: A WebGuardrail validating query "Python Documentation"
    When: Validating and passing to backend
    Then: Query case is preserved (not lowercased)
    """
    guardrail = WebGuardrail()
    query = "Python Documentation"
    result = guardrail.validate("web_search", {"query": query})

    assert result.valid
    # The query itself is not modified by the guardrail

  def test_unicode_allowed_in_query(self) -> None:
    """
    Given: A WebGuardrail validating query with Unicode characters
    When: Validating the query
    Then: Returns validation success (Unicode is allowed)
    """
    guardrail = WebGuardrail()
    result = guardrail.validate("web_search", {"query": "Python 中文 文档"})

    assert result.valid


# Fixtures


@pytest.fixture
def mock_config() -> MagicMock:
  """Mock WebSearchToolConfig with default settings."""
  config = MagicMock()
  config.max_query_length = 500
  config.requests_per_minute = 60
  config.requests_per_hour = 1000
  config.domain_allowlist = ()
  config.domain_blocklist = ("*.internal", "*.local")
  config.enabled = True
  return config


@pytest.fixture
def strict_config() -> MagicMock:
  """Mock WebSearchToolConfig with strict settings."""
  config = MagicMock()
  config.max_query_length = 100
  config.requests_per_minute = 10
  config.requests_per_hour = 100
  config.domain_allowlist = ("*.github.com", "docs.python.org")
  config.domain_blocklist = ("*.internal", "*.local", "*.localhost")
  config.enabled = True
  return config
