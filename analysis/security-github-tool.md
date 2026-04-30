# Security Analysis: GitHub Tool

**Document Version**: 1.0
**Date**: 2026-04-30
**Status**: Draft

## 1. Threat Model

### 1.1 Asset Identification

| Asset | Sensitivity | Exposure via GitHub Tool |
|-------|-------------|--------------------------|
| Repository metadata | Low | Public by default, accessible via tool |
| Issue/PR content | Low-Medium | May contain sensitive discussion |
| Workflow logs | Medium | May reveal secrets if misconfigured |
| Release assets | Low | Public downloads |
| Authentication token | Critical | Never exposed by tool, managed by `gh` |

### 1.2 Threat Actors

| Actor | Capability | Risk Level |
|-------|------------|------------|
| Compromised agent | Read access to allowed repos | Medium |
| Malicious LLM prompt | Manipulate tool parameters | Medium |
| External attacker | Intercept `gh` commands | Low (localhost) |

### 1.3 Attack Vectors

#### Vector 1: Information Disclosure

**Scenario**: Agent views workflow logs that accidentally contain secrets.

**Mitigation**:
- Workflow view does not include full logs by default
- Configuration can disable workflow operations entirely

#### Vector 2: Rate Limit Exhaustion

**Scenario**: Agent loops on GitHub operations, exhausting API rate limits.

**Mitigation**:
- Per-operation timeout (30 seconds default)
- Result count limits (max 100 for lists)
- Rate limit error handling returns error to agent

#### Vector 3: Command Injection

**Scenario**: Malicious input in parameters attempts to inject shell commands.

**Mitigation**:
- Operation is enum-restricted (whitelist)
- All parameters passed as proper arguments (not shell interpolation)
- Subprocess uses `subprocess.run()` with list args, not shell=True

#### Vector 4: Unauthorized Operations

**Scenario**: Agent attempts destructive operation (merge PR, delete branch).

**Mitigation**:
- MVP only includes read-only operations
- Operation allowlist in configuration
- Destructive operations require explicit Phase 2 enablement

## 2. Guardrails

### 2.1 Operation Allowlist

Only operations explicitly enabled in configuration are permitted:

```toml
[tools.github]
allowed_operations = ["repo_view", "issue_list", "issue_view"]
```

Default: All MVP operations enabled.

### 2.2 Repository Access Control

**MVP**: No repository restriction - any repo accessible to authenticated user.

**Phase 2**: Add repository allowlist:

```toml
[tools.github]
allowed_repos = ["owner/repo1", "owner/repo2"]
```

### 2.3 Rate Limiting

| Guardrail | Default | Description |
|-----------|---------|-------------|
| `timeout_seconds` | 30 | Maximum command execution time |
| `max_results` | 100 | Maximum items returned per list operation |
| `require_explicit_repo` | false | Require repo parameter (prevent auto-detection) |

### 2.4 Destructive Operation Protection

**MVP**: No destructive operations implemented.

**Phase 2 Design**:
```toml
[tools.github]
allow_destructive = false  # Master switch
destructive_operations = ["pr_merge", "branch_delete"]  # Explicit list
destructive_require_confirmation = true  # Ask user before executing
```

## 3. Security Checklist

### 3.1 Implementation Requirements

- [ ] Operation enum validation (no arbitrary strings)
- [ ] Subprocess execution with list args (not shell=True)
- [ ] Timeout enforcement on all `gh` commands
- [ ] Rate limit error detection and handling
- [ ] Authentication state verification before operations
- [ ] Error messages sanitized (no internal paths/tokens leaked)
- [ ] Structured logging for all GitHub operations

### 3.2 Configuration Validation

- [ ] `allowed_operations` contains only known operations
- [ ] `timeout_seconds` is positive integer
- [ ] `max_results` within reasonable bounds (1-1000)

### 3.3 Testing Requirements

- [ ] Test command injection attempts are blocked
- [ ] Test timeout enforcement
- [ ] Test operation allowlist enforcement
- [ ] Test error handling for unauthenticated state
- [ ] Test rate limit error handling

## 4. Security Considerations by Operation

### 4.1 repo_view

**Risk**: Low
- Only reads public metadata
- No sensitive information exposure

**Guardrails**: None beyond authentication check

### 4.2 issue_list / issue_view

**Risk**: Low-Medium
- Issues may contain sensitive discussion
- Private repo issues are sensitive

**Guardrails**:
- Authentication required
- Respects repo visibility (private repos require auth)

### 4.3 pr_list / pr_view

**Risk**: Low-Medium
- PRs may contain code reviews with sensitive information
- Draft PRs may expose incomplete security fixes

**Guardrails**:
- Authentication required
- Private repos require explicit access

### 4.4 workflow_list / workflow_view

**Risk**: Medium
- Workflow names may reveal CI/CD architecture
- Workflow logs could contain secrets if misconfigured

**Guardrails**:
- Workflow view shows summary, not full logs by default
- Can be disabled entirely in configuration
- Full log view requires Phase 2 explicit enablement

### 4.5 release_list / release_view

**Risk**: Low
- Releases are public by nature
- No secrets expected in release descriptions

**Guardrails**: None beyond authentication

## 5. Authentication Model

### 5.1 GitHub CLI Authentication

The tool relies on `gh` CLI's authentication:
- User authenticates with `gh auth login`
- Token stored in `~/.config/gh/hosts.yml` or keyring
- Token never exposed to the tool or agent

### 5.2 Token Permissions

**Recommended**: Use a token with minimal permissions:
- `repo` scope for private repo access
- `public_repo` scope for public repos only
- `read:org` for organization repos

### 5.3 Security Benefits

- Token management delegated to `gh` (secure storage)
- Agent never sees token
- Token can be revoked independently
- Supports SSO, 2FA via `gh`

## 6. Audit Trail

All GitHub operations are logged with:
- Timestamp
- Operation type
- Repository (if specified)
- Success/failure status
- Error type (if failed)

**Log Entry Example**:
```json
{
  "event": "github_tool_execute",
  "timestamp": "2026-04-30T10:30:00Z",
  "operation": "issue_view",
  "repo": "owner/repo",
  "number": 123,
  "success": true,
  "duration_ms": 342
}
```

## 7. Comparison with Direct API Access

| Aspect | gh CLI Wrapper | Direct HTTP API |
|--------|---------------|-----------------|
| Authentication | Managed by `gh` | Token in tool config |
| Secret Storage | Keyring/encrypted | Config file (risk) |
| Rate Limiting | Built-in | Manual implementation |
| Error Handling | Mature | Must reimplement |
| Security Updates | `gh` updates | Manual maintenance |
| Dependencies | `gh` binary | httpx (already used) |

**Recommendation**: Use `gh` CLI wrapper for MVP. Consider direct API for Phase 2 if fine-grained control needed.

## 8. Phase 2 Security Enhancements

1. **Repository Allowlist**: Restrict to specific repositories
2. **Destructive Operations**: Add with confirmation prompts
3. **Audit Export**: Structured audit log export
4. **Token Scope Validation**: Verify token has minimal required scopes
5. **Webhook Support**: React to GitHub events