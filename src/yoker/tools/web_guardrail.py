"""Web guardrail for security enforcement.

Provides comprehensive security validation for web tools including:
- SSRF (Server-Side Request Forgery) protection
- Domain whitelist/blacklist
- Query sanitization
- Rate limiting
"""

import ipaddress
import logging
import re
import socket
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from .base import ValidationResult
from .guardrails import Guardrail

if TYPE_CHECKING:
  pass

logger = logging.getLogger(__name__)

# IP ranges for SSRF protection
PRIVATE_CIDRS = [
  ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918
  ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918
  ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
  ipaddress.ip_network("127.0.0.0/8"),  # Loopback
  ipaddress.ip_network("169.254.0.0/16"),  # Link-local (cloud metadata)
  ipaddress.ip_network("::1/128"),  # IPv6 loopback
  ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
  ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
]

# Cloud metadata endpoints
METADATA_IPS = [
  "169.254.169.254",  # AWS/GCP/Azure metadata
]

# Sensitive patterns to block in queries
# Note: These block patterns that indicate actual secret exposure attempts,
# not documentation/tutorial searches. A web search for ".env tutorial" is fine.
SENSITIVE_PATTERNS = [
  r"password\s*=\s*['\"]?\S+",  # password='actual_password'
  r"api[_-]?key\s*=\s*['\"]?\S+",  # api_key='actual_key'
  r"apikey\s*=\s*['\"]?\S+",  # apikey='actual_key'
  r"secret\s*=\s*['\"]?\S+",  # secret='actual_secret'
  r"token\s*=\s*['\"]?\S+",  # token='actual_token'
  r"credentials\s*=\s*['\"]?\S+",  # credentials='actual_creds'
  r"private[_-]?key\s*=\s*['\"]?\S+",  # private_key='actual_key'
  r"bearer\s+['\"]?[a-zA-Z0-9_-]+",  # bearer actual_token
]

# Unicode characters to strip
INVISIBLE_UNICODE = [
  "​",  # Zero-width space
  "‌",  # Zero-width non-joiner
  "‍",  # Zero-width joiner
  "﻿",  # BOM
]


@dataclass
class RateLimitState:
  """Rate limiting state for a user/session.

  Attributes:
    requests_per_minute: Request timestamps for minute window.
    requests_per_hour: Request timestamps for hour window.
    concurrent_requests: Current concurrent request count.
    last_reset: Timestamp of last rate limit reset.
  """

  requests_per_minute: list[float] = field(default_factory=list)
  requests_per_hour: list[float] = field(default_factory=list)
  concurrent_requests: int = 0
  last_reset: float = field(default_factory=time.time)


@dataclass
class WebGuardrailConfig:
  """Configuration for WebGuardrail.

  Attributes:
    max_query_length: Maximum query string length (default 500).
    domain_allowlist: Domains to allow (empty = all allowed).
    domain_blocklist: Domains to block (empty = none blocked).
    requests_per_minute: Maximum requests per minute (0 = unlimited).
    requests_per_hour: Maximum requests per hour (0 = unlimited).
    max_concurrent_requests: Maximum concurrent requests (0 = unlimited).
    block_private_cidrs: Whether to block private IP ranges.
    timeout_seconds: Search timeout in seconds.
  """

  max_query_length: int = 500
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  requests_per_minute: int = 60
  requests_per_hour: int = 1000
  max_concurrent_requests: int = 0
  block_private_cidrs: bool = True
  timeout_seconds: int = 30


class WebGuardrail(Guardrail):
  """Guardrail for web tool validation.

  Validates:
    - Query length (prevents excessive queries)
    - Domain allowlist (optional, for restricted searches)
    - Domain blocklist (optional, for blocked domains)
    - SSRF protection (blocks private IPs, cloud metadata)
    - Query sanitization (blocks sensitive patterns)
    - Rate limiting (requests per minute, per hour, concurrent)

  Note:
    Domain filtering is client-side validation only.
    Ollama backend may still access blocked domains.
    For full control, use LocalWebSearchBackend.
  """

  def __init__(self, config: "WebGuardrailConfig | None" = None) -> None:
    """Initialize guardrail with configuration.

    Args:
      config: WebGuardrailConfig with validation settings.
    """
    self._config = config or WebGuardrailConfig()
    self._rate_limit_lock = Lock()
    self._rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)

  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    """Validate web search parameters.

    Steps:
      1. Validate query is present and non-empty.
      2. Validate query length <= max_query_length.
      3. Check for SSRF attempts (private IPs, cloud metadata).
      4. Check domain allowlist if configured.
      5. Check domain blocklist if configured.
      6. Check for sensitive patterns in query.
      7. Check rate limits.

    Args:
      tool_name: Name of tool being validated.
      params: Tool parameters from LLM.

    Returns:
      ValidationResult with success/failure and reason.
    """
    # Step 1: Validate query parameter
    query = params.get("query", "")
    if not query:
      return ValidationResult(valid=False, reason="Query is required")

    # Strip whitespace and check
    stripped_query = query.strip()
    if not stripped_query:
      return ValidationResult(valid=False, reason="Query cannot be empty or whitespace")

    # Step 2: Validate query length
    if len(stripped_query) > self._config.max_query_length:
      return ValidationResult(
        valid=False,
        reason=f"Query exceeds maximum length: {len(stripped_query)} > {self._config.max_query_length}",
      )

    # Step 3: Strip invisible Unicode and validate
    cleaned_query = self._strip_invisible_unicode(stripped_query)

    # Step 4: Check for SSRF attempts
    ssrf_error = self._check_ssrf(cleaned_query)
    if ssrf_error:
      return ValidationResult(valid=False, reason=ssrf_error)

    # Step 5: Check domain allowlist/blocklist
    if self._config.domain_allowlist:
      allow_error = self._check_domain_allowlist(cleaned_query)
      if allow_error:
        return ValidationResult(valid=False, reason=allow_error)

    if self._config.domain_blocklist:
      block_error = self._check_domain_blocklist(cleaned_query)
      if block_error:
        return ValidationResult(valid=False, reason=block_error)

    # Step 6: Check for sensitive patterns
    sensitive_error = self._check_sensitive_patterns(cleaned_query)
    if sensitive_error:
      return ValidationResult(valid=False, reason=sensitive_error)

    # Step 7: Check rate limits
    user_id = params.get("_user_id", "default")
    rate_error = self._check_rate_limit(user_id)
    if rate_error:
      return ValidationResult(valid=False, reason=rate_error)

    return ValidationResult(valid=True)

  def _strip_invisible_unicode(self, text: str) -> str:
    """Strip invisible Unicode characters from text.

    Args:
      text: Input text.

    Returns:
      Text with invisible characters removed.
    """
    result = text
    for char in INVISIBLE_UNICODE:
      result = result.replace(char, "")
    # Strip Unicode Tag characters (U+E0000-U+E007F)
    # These are invisible characters that can be used for prompt injection
    result = re.sub(r"[\U000e0000-\U000e007f]", "", result)
    return result

  def _check_ssrf(self, query: str) -> str | None:
    """Check for SSRF attempts in query.

    Checks for:
      - Private IP addresses (10.x, 172.16-31.x, 192.168.x)
      - Cloud metadata IPs (169.254.169.254)
      - Localhost (127.0.0.1, localhost)
      - URL-encoded IPs
      - Hex-encoded IPs
      - Decimal-encoded IPs
      - IPv6 private ranges

    Args:
      query: Search query string.

    Returns:
      Error message if SSRF detected, None if safe.
    """
    if not self._config.block_private_cidrs:
      return None

    # Extract potential IPs/URLs from query
    # Check for IP patterns
    ip_pattern = r"\b(?:(?:\d{1,3}\.){3}\d{1,3})\b"
    # IPv6 pattern (supports compressed notation like fe80::1, ::1, etc.)
    ipv6_pattern = r"\b(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*|::(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*)?)\b"

    # Find all potential IPs
    potential_ips = re.findall(ip_pattern, query)
    potential_ips.extend(re.findall(ipv6_pattern, query))

    # Also check for URL-encoded IPs
    try:
      decoded_query = unquote(query)
      potential_ips.extend(re.findall(ip_pattern, decoded_query))
    except Exception:
      pass

    # Check hex-encoded IPs (0xa9fea9fe = 169.254.169.254)
    hex_pattern = r"0x([0-9a-fA-F]+)"
    hex_matches = re.findall(hex_pattern, query)
    for hex_val in hex_matches:
      try:
        decimal_val = int(hex_val, 16)
        if decimal_val < 2**32:
          # Convert to IP (big-endian: most significant byte first)
          ip_str = ".".join(str((decimal_val >> (8 * (3 - i))) & 0xFF) for i in range(4))
          potential_ips.append(ip_str)
      except ValueError:
        pass

    # Check decimal-encoded IPs
    decimal_pattern = r"\b(\d{8,12})\b"
    decimal_matches = re.findall(decimal_pattern, query)
    for dec_val in decimal_matches:
      try:
        decimal_val = int(dec_val)
        if decimal_val < 2**32:
          # Convert to IP (big-endian: most significant byte first)
          ip_str = ".".join(str((decimal_val >> (8 * (3 - i))) & 0xFF) for i in range(4))
          potential_ips.append(ip_str)
      except ValueError:
        pass

    # Validate each potential IP
    for ip_str in potential_ips:
      try:
        # Check for IPv4-mapped IPv6
        if ip_str.lower().startswith("::ffff:"):
          ip_str = ip_str[7:]  # Remove ::ffff: prefix

        ip = ipaddress.ip_address(ip_str)

        # Check against private CIDRs
        for cidr in PRIVATE_CIDRS:
          if ip in cidr:
            return f"SSRF blocked: private IP address detected ({ip_str})"

        # Check for cloud metadata IP
        if str(ip) in METADATA_IPS:
          return "SSRF blocked: cloud metadata endpoint detected"
      except ValueError:
        # Not a valid IP, might be a domain
        pass

    # Check for localhost
    if re.search(r"\blocalhost\b", query, re.IGNORECASE):
      return "SSRF blocked: localhost detected"

    # Check for domains that might resolve to private IPs
    # Extract domains from query (must contain at least one dot)
    url_with_scheme_pattern = r"https?://([a-zA-Z0-9.-]+)"
    bare_domain_pattern = r"(?:^|\s)([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)(?:/|\s|$)"
    site_pattern = r"\bsite:\s*([a-zA-Z0-9.-]+)"

    domains = re.findall(url_with_scheme_pattern, query)
    domains.extend(re.findall(bare_domain_pattern, query))
    domains.extend(re.findall(site_pattern, query))

    for domain in domains:
      if not self._is_safe_domain(domain):
        return f"SSRF blocked: domain may resolve to private IP ({domain})"

    return None

  def _is_safe_domain(self, domain: str) -> bool:
    """Check if a domain is safe (doesn't resolve to private IP).

    Note: This performs DNS resolution which can be slow.
    We cache results in production implementations.

    Args:
      domain: Domain name to check.

    Returns:
      True if domain is safe, False if it resolves to private IP.
    """
    try:
      # Resolve domain to IPs
      infos = socket.getaddrinfo(domain, None)
      for info in infos:
        ip_str = info[4][0]
        try:
          ip = ipaddress.ip_address(ip_str)
          # Check against private CIDRs
          for cidr in PRIVATE_CIDRS:
            if ip in cidr:
              return False
          # Check metadata IP
          if str(ip) in METADATA_IPS:
            return False
        except ValueError:
          continue
      return True
    except socket.gaierror:
      # Cannot resolve - allow but log
      logger.debug(f"Could not resolve domain: {domain}")
      return True

  def _check_domain_allowlist(self, query: str) -> str | None:
    """Check if query violates domain allowlist.

    Note:
      This is a heuristic check. It looks for domain patterns
      in the query string. For full control, use LocalWebSearchBackend
      which can filter results by domain.

    Args:
      query: Search query string.

    Returns:
      Error message if blocked, None if allowed.
    """
    if not self._config.domain_allowlist:
      return None

    # Extract domains from query
    # Pattern 1: URL pattern with scheme (http://, https://)
    url_with_scheme_pattern = r"https?://([a-zA-Z0-9.-]+)"
    # Pattern 2: Bare domain (must contain at least one dot to be a domain)
    bare_domain_pattern = r"(?:^|\s)([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)(?:/|\s|$)"
    # Pattern 3: site: directive
    site_pattern = r"\bsite:\s*([a-zA-Z0-9.-]+)"

    domains = re.findall(url_with_scheme_pattern, query.lower())
    domains.extend(re.findall(bare_domain_pattern, query.lower()))
    domains.extend(re.findall(site_pattern, query.lower()))

    # If no domains found, allow (no domain restriction in query)
    if not domains:
      return None

    # Check each domain against allowlist
    for domain in domains:
      if not self._domain_matches_list(domain, self._config.domain_allowlist):
        return f"Query contains non-whitelisted domain: {domain}"

    return None

  def _check_domain_blocklist(self, query: str) -> str | None:
    """Check if query matches blocked domains.

    Args:
      query: Search query string.

    Returns:
      Error message if blocked, None if allowed.
    """
    if not self._config.domain_blocklist:
      return None

    # Extract domains from query
    # Pattern 1: URL pattern with scheme (http://, https://)
    url_with_scheme_pattern = r"https?://([a-zA-Z0-9.-]+)"
    # Pattern 2: Bare domain (must contain at least one dot to be a domain)
    bare_domain_pattern = r"(?:^|\s)([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)(?:/|\s|$)"
    # Pattern 3: site: directive
    site_pattern = r"\bsite:\s*([a-zA-Z0-9.-]+)"

    domains = re.findall(url_with_scheme_pattern, query.lower())
    domains.extend(re.findall(bare_domain_pattern, query.lower()))
    domains.extend(re.findall(site_pattern, query.lower()))

    # Check each domain against blocklist
    for domain in domains:
      if self._domain_matches_list(domain, self._config.domain_blocklist):
        return f"Query contains blocked domain: {domain}"

    return None

  def _domain_matches_list(self, domain: str, patterns: tuple[str, ...]) -> bool:
    """Check if domain matches any pattern in list.

    Supports wildcard matching:
      - "*.example.com" matches "api.example.com", "v1.api.example.com"
      - "example.com" matches only "example.com"

    Args:
      domain: Domain to check (lowercase).
      patterns: List of patterns (may include wildcards).

    Returns:
      True if domain matches any pattern.
    """
    domain_lower = domain.lower()

    for pattern in patterns:
      pattern_lower = pattern.lower()

      if pattern_lower.startswith("*."):
        # Wildcard pattern - match any subdomain
        suffix = pattern_lower[1:]  # Remove "*"
        if domain_lower.endswith(suffix) or domain_lower == pattern_lower[2:]:
          return True
      else:
        # Exact match
        if domain_lower == pattern_lower:
          return True

    return False

  def _check_sensitive_patterns(self, query: str) -> str | None:
    """Check for sensitive patterns in query.

    Args:
      query: Search query string.

    Returns:
      Error message if sensitive pattern found, None if safe.
    """
    for pattern in SENSITIVE_PATTERNS:
      if re.search(pattern, query, re.IGNORECASE):
        return "Query contains sensitive pattern"

    return None

  def _check_rate_limit(self, user_id: str) -> str | None:
    """Check rate limits for user.

    Args:
      user_id: User/session identifier.

    Returns:
      Error message if rate limited, None if allowed.
    """
    if (
      self._config.requests_per_minute == 0
      and self._config.requests_per_hour == 0
      and self._config.max_concurrent_requests == 0
    ):
      return None

    with self._rate_limit_lock:
      state = self._rate_limits[user_id]
      current_time = time.time()

      # Clean old timestamps
      minute_ago = current_time - 60
      hour_ago = current_time - 3600
      state.requests_per_minute = [t for t in state.requests_per_minute if t > minute_ago]
      state.requests_per_hour = [t for t in state.requests_per_hour if t > hour_ago]

      # Check per-minute limit
      if (
        self._config.requests_per_minute > 0
        and len(state.requests_per_minute) >= self._config.requests_per_minute
      ):
        return f"Rate limit exceeded: {self._config.requests_per_minute} requests per minute"

      # Check per-hour limit
      if (
        self._config.requests_per_hour > 0
        and len(state.requests_per_hour) >= self._config.requests_per_hour
      ):
        return f"Rate limit exceeded: {self._config.requests_per_hour} requests per hour"

      # Check concurrent limit
      if (
        self._config.max_concurrent_requests > 0
        and state.concurrent_requests >= self._config.max_concurrent_requests
      ):
        return f"Rate limit exceeded: {self._config.max_concurrent_requests} concurrent requests"

      # Record this request
      state.requests_per_minute.append(current_time)
      state.requests_per_hour.append(current_time)
      state.concurrent_requests += 1

      return None

  def release_concurrent(self, user_id: str = "default") -> None:
    """Release a concurrent request slot.

    Call this after search completes to decrement concurrent count.

    Args:
      user_id: User/session identifier.
    """
    with self._rate_limit_lock:
      if user_id in self._rate_limits:
        state = self._rate_limits[user_id]
        if state.concurrent_requests > 0:
          state.concurrent_requests -= 1


__all__ = [
  "WebGuardrail",
  "WebGuardrailConfig",
  "RateLimitState",
]
