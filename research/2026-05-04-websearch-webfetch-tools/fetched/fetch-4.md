# SSRF Defense Technical Details

**Source**: https://cordum.io/blog/ai-agent-policy-url-security-ssrf
**Fetched**: 2026-05-04T00:00:00Z

---

## URL Validation & Host Controls

- Host allowlist enforced before outbound policy fetch via `SAFETY_POLICY_URL_ALLOWLIST` (comma-separated hosts)
- Suffix matching: "Host checks allow exact match and subdomain suffix match (`host == entry || hasSuffix('.'+entry)`)"
- Private/loopback/link-local addresses blocked by default; override requires `SAFETY_POLICY_URL_ALLOW_PRIVATE=true`

## DNS Rebinding Protection

- "DNS resolution runs in URL validation and again in `DialContext`" to reduce time-of-check/time-of-use gaps

## Redirect Limits

- Redirect chain capped at 5 hops
- Each redirect URL revalidated against allowlist
- Production requires HTTPS for initial URL; redirects need scheme guard to prevent downgrade

## Size & Timeout Limits

- HTTP client timeout: 10 seconds
- Default max response size: 2,097,152 bytes (`SAFETY_POLICY_MAX_BYTES`)

## Scheme Enforcement

- Remote fetch path only entered for `http://` or `https://` schemes
- Production rejects `http://` policy URLs to reduce MITM/downgrade risk

## Key Code Pattern (Go)

```go
CheckRedirect: func(req *http.Request, via []*http.Request) error {
  if len(via) >= 5 {
    return errors.New("policy fetch redirect limit exceeded")
  }
  return validatePolicyURL(req.URL)
}
```

## Environment Variables

- `SAFETY_POLICY_URL` - policy source URL
- `SAFETY_POLICY_URL_ALLOWLIST` - approved hosts
- `SAFETY_POLICY_URL_ALLOW_PRIVATE` - default false
- `SAFETY_POLICY_MAX_BYTES` - response size limit
- `SAFETY_POLICY_SIGNATURE_REQUIRED` - integrity control