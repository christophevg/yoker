# Sandtrap GitHub Repository

**Source**: https://github.com/ashenfad/sandtrap
**Fetched**: 2026-05-05T00:20:00Z

---

## Architecture & Isolation Levels

Three isolation levels via the `sandbox()` factory:
- **"none"** (default): in-process, shares host's memory space
- **"process"**: subprocess-backed, crash protection, no kernel restrictions
- **"kernel"**: subprocess + kernel-level isolation (seccomp, Landlock, Seatbelt)

## Security Features

Uses "AST rewriting and compiled bytecode execution" with "whitelist-based policies control[ing] attribute access, imports, and resource usage." Kernel isolation includes:
- Syscall filtering
- Filesystem restriction via Landlock (Linux) or Seatbelt (macOS)
- Network blocking at kernel level

## Imports & Attribute Access

Controlled through whitelist-based policies. The Policy class configures "what sandboxed code can access."

## Performance Characteristics

- In-process mode is "lightweight"
- Process/kernel modes provide "crash protection" where a "worker crash doesn't take down the host process"

## Example Usage

```python
from sandtrap import Policy, sandbox

policy = Policy(timeout=5.0, tick_limit=100_000)
with sandbox(policy) as sb:
    result = sb.exec("total = sum(range(10))")
print(result.stdout)
print(result.namespace)  # {"total": 45}
```

## Limitations & Trade-offs

"Designed as a walled garden for cooperative code (e.g. agent-generated scripts), not for adversarial inputs."
The project explicitly states it's not intended for untrusted/malicious code.