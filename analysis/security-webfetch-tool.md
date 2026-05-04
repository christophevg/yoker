# Security Analysis: WebFetchTool

**Task:** 2.12 WebFetch Tool
**Date:** 2026-05-04
**Status:** Complete

---

## Executive Summary

WebFetchTool presents higher security risk than WebSearchTool due to direct URL handling and HTTP connection management. The existing `WebGuardrail` provides a strong foundation but requires URL-specific extensions for SSRF protection through redirect chains, DNS rebinding defense, and content size limits. The analysis identifies **1 Critical** and **3 High** severity findings requiring implementation guardrails before the tool can be safely deployed.

---

## Threat Model: STRIDE Analysis

| Category | Threat | Mitigation |
|----------|--------|------------|
| **Spoofing** | Attacker provides URL that resolves to internal service | IP validation, allowlists, DNS rebinding protection |
| **Tampering** | Malicious redirect chain to private IP | Redirect validation with re-check at each hop |
| **Information Disclosure** | Fetching sensitive internal endpoints (metadata, admin panels) | SSRF protection, private IP blocking |
| **Denial of Service** | Large file download, slow connections | Size limits, timeouts, rate limiting |
| **Elevation of Privilege** | Cloud metadata access (AWS IMDS, GCP metadata) | Block 169.254.169.254 and equivalent IPs |

---

## Attack Vectors Specific to WebFetch

### 1. SSRF via Direct URL Input (Critical)

Unlike WebSearchTool where the query is processed by Ollama's backend, WebFetchTool accepts URLs directly, enabling precise SSRF attacks:

```
Attack Examples:
- http://169.254.169.254/latest/meta-data/iam/security-credentials/
- http://127.0.0.1:8080/admin
- http://10.0.0.1/internal-api
- http://[::1]:8080/ (IPv6 loopback)
- http://2130706433/ (decimal-encoded 127.0.0.1)
- http://0x7f000001/ (hex-encoded 127.0.0.1)
```

**Mitigation**: Reuse `WebGuardrail._check_ssrf()` with URL-specific extraction.

### 2. DNS Rebinding (Critical)

DNS rebinding exploits the time-of-check to time-of-use (TOCTOU) gap:

```
Timeline:
1. Validation: attacker-controlled.com → 93.184.216.34 (public IP, passes check)
2. Connection: DNS re-resolves → 169.254.169.254 (private IP, bypasses check)
```

**Mitigation**: IP pinning - resolve once, connect to the IP directly, set Host header.

```python
# Secure pattern
resolved_ip = socket.getaddrinfo(hostname, None)[0][4][0]
validate_ip(resolved_ip)  # Block private ranges
fetch_url = f"https://{resolved_ip}/path"
headers = {"Host": hostname}
```

### 3. Redirect Bypass (High)

HTTP redirects can traverse from public to private IPs:

```
Attack Chain:
1. http://attacker.com/redirect → 302 Found
2. Location: http://169.254.169.254/latest/meta-data/
3. Redirect target bypasses initial validation
```

**Mitigation**: Disable automatic redirects or validate each redirect target.

```python
# Secure pattern - manual redirect handling
async with httpx.AsyncClient(follow_redirects=False) as client:
    response = await client.get(url, timeout=30.0)
    if 300 <= response.status_code < 400:
        redirect_url = response.headers["Location"]
        if not is_safe_url(redirect_url):
            raise SecurityError("Unsafe redirect")
```

### 4. Content Size Attack (Medium)

Resource exhaustion via large files:

```
Attack Examples:
- http://attacker.com/10gb.file
- Infinite stream endpoints
- Compressed bomb (zip of death)
```

**Mitigation**: Stream with size tracking, reject at limit.

```python
# Secure pattern - track response size
MAX_CONTENT_SIZE = 2 * 1024 * 1024  # 2MB
total_size = 0
async for chunk in response.aiter_bytes():
    total_size += len(chunk)
    if total_size > MAX_CONTENT_SIZE:
        raise ContentTooLargeError(f"Response exceeds {MAX_CONTENT_SIZE} bytes")
```

### 5. Scheme Confusion (Low)

HTTP scheme downgrade attacks:

```
Attack:
- https://example.com/ redirects to http://internal.local/
- User credentials sent over cleartext HTTP
```

**Mitigation**: Enforce HTTPS in production, reject HTTP URLs.

---

## Guardrail Requirements

### What WebGuardrail Already Covers

| Protection | Status | Implementation |
|------------|--------|----------------|
| Private IP blocking | Done | `PRIVATE_CIDRS` list |
| Cloud metadata blocking | Done | `METADATA_IPS` list |
| Domain allowlist | Done | `_check_domain_allowlist()` |
| Domain blocklist | Done | `_check_domain_blocklist()` |
| Rate limiting | Done | `_check_rate_limit()` |
| Query length limits | Done | `max_query_length` |
| Unicode stripping | Done | `_strip_invisible_unicode()` |
| Sensitive patterns | Done | `SENSITIVE_PATTERNS` |

### What WebGuardrail Needs for WebFetch

| Protection | Priority | Implementation |
|------------|----------|----------------|
| URL parsing (extract host) | Critical | Add `_extract_url_host()` method |
| DNS rebinding defense | Critical | Add IP pinning to `WebFetchBackend` |
| Redirect validation | High | Add `_check_redirect_target()` method |
| Content size tracking | High | Add to `WebFetchBackend` (streaming) |
| Scheme validation | Medium | Add `_validate_url_scheme()` method |
| Timeout enforcement | Medium | Add to configuration |

---

## Implementation Recommendations

### 1. WebFetchGuardrail Class (Extends WebGuardrail)

```python
@dataclass
class WebFetchGuardrailConfig(WebGuardrailConfig):
    """Extended configuration for WebFetch guardrail."""
    max_content_size_kb: int = 2048  # 2MB default
    max_redirects: int = 5
    allowed_schemes: tuple[str, ...] = ("https",)
    block_private_cidrs: bool = True
    dns_resolution_cache_ttl: int = 60  # seconds
    
class WebFetchGuardrail(WebGuardrail):
    """Guardrail for WebFetchTool with URL-specific validation."""
    
    def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
        """Validate WebFetch parameters.
        
        Steps:
            1. Extract and validate URL parameter
            2. Parse URL and validate scheme
            3. Validate domain against allowlist/blocklist
            4. Resolve hostname and validate IP (DNS rebinding protection)
            5. Check rate limits
        """
        url = params.get("url", "")
        if not url:
            return ValidationResult(valid=False, reason="URL is required")
        
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            return ValidationResult(valid=False, reason=f"Invalid URL: {e}")
        
        # Validate scheme
        scheme_error = self._validate_scheme(parsed.scheme)
        if scheme_error:
            return ValidationResult(valid=False, reason=scheme_error)
        
        # Validate domain (reuse parent method)
        if parsed.hostname:
            domain_error = self._check_domain(parsed.hostname)
            if domain_error:
                return ValidationResult(valid=False, reason=domain_error)
        
        # DNS rebinding protection - resolve and validate IP
        if self._config.block_private_cidrs:
            ip_error = self._validate_resolved_ip(parsed.hostname)
            if ip_error:
                return ValidationResult(valid=False, reason=ip_error)
        
        return ValidationResult(valid=True)
```

### 2. WebFetchBackend with IP Pinning

For local backend implementation (Phase 2), IP pinning prevents DNS rebinding:

```python
class LocalWebFetchBackend:
    """Local fetch backend with SSRF protection."""
    
    async def fetch(
        self, 
        url: str, 
        timeout: int = 30,
        max_size: int = 2_000_000,
        max_redirects: int = 5,
    ) -> FetchedContent:
        """Fetch content with SSRF protection.
        
        Security steps:
            1. Validate URL scheme
            2. Extract hostname and validate domain
            3. Resolve hostname ONCE
            4. Validate resolved IP (block private ranges)
            5. Connect to IP directly with Host header
            6. Handle redirects with revalidation
            7. Track content size during streaming
        """
        parsed = urlparse(url)
        
        # DNS rebinding protection: resolve once
        hostname = parsed.hostname
        resolved_ip = socket.getaddrinfo(hostname, parsed.port or 443)[0][4][0]
        
        # Validate resolved IP
        self._validate_ip(resolved_ip)
        
        # Build pinned URL
        pinned_url = url.replace(hostname, resolved_ip, 1)
        
        async with httpx.AsyncClient(follow_redirects=False) as client:
            current_url = pinned_url
            current_host = hostname
            redirects_followed = 0
            total_size = 0
            
            while True:
                response = await client.get(
                    current_url,
                    headers={"Host": current_host},
                    timeout=timeout,
                )
                
                # Handle redirects
                if 300 <= response.status_code < 400:
                    redirects_followed += 1
                    if redirects_followed > max_redirects:
                        raise WebFetchError("Too many redirects")
                    
                    redirect_url = response.headers["Location"]
                    # Revalidate redirect target
                    redirect_error = self._validate_redirect(redirect_url)
                    if redirect_error:
                        raise WebFetchError(redirect_error)
                    
                    current_url = redirect_url
                    current_host = urlparse(redirect_url).hostname
                    continue
                
                # Track content size
                total_size = 0
                content_chunks = []
                async for chunk in response.aiter_bytes():
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise WebFetchError(f"Content exceeds {max_size} bytes")
                    content_chunks.append(chunk)
                
                content = b"".join(content_chunks)
                break
            
            # Extract content with Trafilatura
            text = extract(content, output_format="markdown")
            return FetchedContent(
                url=url,
                content=text,
                content_type=response.headers.get("content-type", ""),
                size_bytes=total_size,
            )
```

### 3. Configuration Schema

```toml
[tools.webfetch]
enabled = true
backend = "ollama"  # or "local" when implemented
timeout_seconds = 30
max_content_size_kb = 2048
max_redirects = 5
allowed_schemes = ["https"]

[permissions.web_domains]
# Inherit from WebSearchTool configuration
allow = ["*.github.com", "docs.python.org", "pypi.org", "*.wikipedia.org"]
block = ["*.internal", "*.local", "*.localhost"]
```

---

## Test Cases for Security Validation

### SSRF Protection Tests

```python
class TestWebFetchSSRFProtection:
    """Test cases for SSRF attack prevention."""
    
    @pytest.mark.parametrize("url,expected_error", [
        # IPv4 private ranges
        ("http://127.0.0.1/admin", "private IP"),
        ("http://10.0.0.1/api", "private IP"),
        ("http://192.168.1.1/", "private IP"),
        ("http://172.16.0.1/", "private IP"),
        
        # Cloud metadata
        ("http://169.254.169.254/latest/", "metadata"),
        ("http://100.100.100.200/", "metadata"),  # Alibaba
        
        # IPv6 private
        ("http://[::1]:8080/", "private IP"),
        ("http://[fe80::1]/", "private IP"),
        
        # Encoded IPs
        ("http://2130706433/admin", "private IP"),  # Decimal 127.0.0.1
        ("http://0x7f000001/admin", "private IP"),   # Hex 127.0.0.1
        ("http://0177.0.0.1/admin", "private IP"),   # Octal 127.0.0.1
        
        # DNS rebinding domains (mocked DNS)
        ("http://attacker-controlled.local/", "private IP"),
    ])
    def test_private_ip_blocked(self, url: str, expected_error: str) -> None:
        """Private IP addresses should be blocked."""
        guardrail = WebFetchGuardrail()
        result = guardrail.validate("web_fetch", {"url": url})
        
        assert not result.valid
        assert expected_error in result.reason.lower()
```

### Redirect Validation Tests

```python
class TestWebFetchRedirectValidation:
    """Test cases for redirect attack prevention."""
    
    def test_redirect_to_private_ip_blocked(self) -> None:
        """Redirects to private IPs should be blocked."""
        backend = LocalWebFetchBackend()
        
        with pytest.raises(WebFetchError) as exc_info:
            backend.fetch("http://attacker.com/redirect-to-internal")
        
        assert "redirect" in str(exc_info.value).lower()
    
    def test_redirect_chain_limit_enforced(self) -> None:
        """Redirect chains should be limited to prevent infinite loops."""
        backend = LocalWebFetchBackend(max_redirects=5)
        
        with pytest.raises(WebFetchError) as exc_info:
            backend.fetch("http://attacker.com/infinite-redirect")
        
        assert "too many redirects" in str(exc_info.value).lower()
    
    def test_redirect_preserves_scheme_https(self) -> None:
        """HTTPS URLs should not redirect to HTTP."""
        guardrail = WebFetchGuardrail(WebFetchGuardrailConfig(allowed_schemes=("https",)))
        
        result = guardrail.validate("web_fetch", {"url": "http://example.com/"})
        assert not result.valid
        assert "scheme" in result.reason.lower()
```

### DNS Rebinding Tests

```python
class TestWebFetchDNSRebinding:
    """Test cases for DNS rebinding attack prevention."""
    
    def test_ip_pinning_prevents_rebind(self, mock_dns) -> None:
        """IP pinning should prevent DNS rebinding attacks."""
        mock_dns.add_record("attacker.com", ["93.184.216.34", "169.254.169.254"])
        
        backend = LocalWebFetchBackend()
        content = backend.fetch("https://attacker.com/path")
        
        # Verify connection was to public IP
        assert backend.last_connected_ip == "93.184.216.34"
    
    def test_post_connection_ip_validation(self) -> None:
        """Validate connected IP even if DNS changes mid-flight."""
        backend = LocalWebFetchBackend()
        
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.side_effect = [
                [("AF_INET", 0, 0, "attacker.com", ("93.184.216.34", 443))],
                [("AF_INET", 0, 0, "attacker.com", ("169.254.169.254", 443))],
            ]
            
            with pytest.raises(WebFetchError):
                backend.fetch("https://attacker.com/path")
```

### Content Size Tests

```python
class TestWebFetchContentSize:
    """Test cases for content size limits."""
    
    def test_content_size_limit_enforced(self, mock_http) -> None:
        """Content exceeding limit should be rejected."""
        backend = LocalWebFetchBackend(max_size=1_000_000)  # 1MB
        
        mock_http.add_response("https://example.com/large", 
            content=b"x" * 2_000_000,  # 2MB
        )
        
        with pytest.raises(WebFetchError) as exc_info:
            backend.fetch("https://example.com/large")
        
        assert "exceeds" in str(exc_info.value).lower()
    
    def test_streaming_stops_at_limit(self, mock_http) -> None:
        """Streaming should stop at size limit, not download entire file."""
        backend = LocalWebFetchBackend(max_size=100)  # 100 bytes
        
        with pytest.raises(WebFetchError):
            backend.fetch("https://example.com/streaming")
        
        # Verify backend didn't read more than needed
        assert mock_http.bytes_read <= 150  # Some overhead allowed
```

---

## Vulnerability Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| SSRF via direct URL input | Blocking | Implement URL-specific validation in WebFetchGuardrail |
| DNS rebinding bypass | Blocking | Implement IP pinning in LocalWebFetchBackend |
| Redirect chain bypass | Blocking | Implement redirect validation in WebFetchGuardrail |
| Content size DoS | Blocking | Implement size tracking in WebFetchBackend |
| HTTP scheme downgrade | Related | Add scheme validation to config |
| Timeout exhaustion | Related | Add timeout to configuration |

---

## Security Checklist for WebFetchTool Implementation

- [ ] **WebFetchGuardrail class** extends WebGuardrail with URL-specific validation
- [ ] **URL parsing** extracts hostname, validates scheme
- [ ] **DNS rebinding protection** resolves hostname once, connects to IP directly
- [ ] **Redirect validation** checks each redirect target against allowlist
- [ ] **Content size tracking** streams with size limits (2MB default)
- [ ] **Timeout enforcement** aborts after configurable timeout
- [ ] **Scheme enforcement** HTTPS only in production (configurable for development)
- [ ] **IP validation** blocks all private CIDRs including IPv6
- [ ] **Rate limiting** reuses WebGuardrail's rate limiting
- [ ] **Test coverage** all attack vectors have security tests

---

## Sources

- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and Forwards_Cheat_Sheet.html)
- [DNS Rebinding Attacks Against SSRF Protections](https://behradtaher.dev/DNS-Rebinding-Attacks-Against-SSRF-Protections/)
- [Python SSRF Prevention Guide 2026](https://chs.us/2026/05/python-ssrf-prevention-guide/)
- [OWASP Open Redirect Documentation](https://owasp.org/www-community/attacks/open_redirect)