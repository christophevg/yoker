# Python Code Execution Safety for yoker

**Research Date:** 2026-05-05
**Purpose:** Investigate safe Python code execution approaches for implementing a Python Tool in yoker agent harness
**Previous Research:** None

---

## Executive Summary

Safe Python code execution requires a **defense-in-depth approach** combining multiple security layers. No single solution provides complete isolation. The recommended approach for yoker is **subprocess isolation with AST validation and resource limits**, avoiding kernel-level sandboxing complexity while providing adequate protection for cooperative agent-generated code.

Key findings:
- **RestrictedPython** is NOT a sandbox—it only restricts language subset, not library access
- **PyPy sandbox** is unmaintained but v2 in development; not production-ready
- **Subprocess isolation** is the baseline protection layer
- **Sandtrap** provides a practical 3-level approach (none/process/kernel) specifically designed for agent-generated code
- **Defense-in-depth** (AST validation + subprocess + resource limits) is the 2026 standard pattern

---

## 1. Safe Execution Approaches

### 1.1 Language-Based Restrictions

#### RestrictedPython

**What it is:** A tool that defines a restricted subset of Python via AST transformation [1].

**Security Reality:**
- Explicitly states it is **NOT a sandbox** [1]
- Restricts EBNF grammar elements but library calls remain available
- Requires manual configuration of `safe_globals`, `safe_builtins`, and custom policies
- Multiple CVEs (2023-2025): CVE-2025-22153, CVE-2024-47532, CVE-2023-37271, CVE-2023-41039

**Verdict:** Insufficient alone. Only useful as part of multi-layer defense.

#### PyPy Sandbox

**Status:** Unmaintained, but v2 in development [2].

**Architecture:**
- Two-process model: outer controller + sandboxed subprocess
- All I/O serialized through stdin/stdout pipes
- More secure than CPython (harder to segfault)

**Verdict:** Not production-ready. Wait for sandbox-2 branch to mature.

---

### 1.2 Subprocess Isolation

The baseline protection layer. Execute code in a separate process that can be killed without affecting the host.

**Key Techniques:**
- Use `subprocess.run()` with `timeout` parameter
- NEVER use `shell=True` with untrusted input [5]
- Always use `check=True` to catch failures [5]
- Set resource limits via `resource` module

**Resource Limits (Python `resource` module) [5]:**
- `RLIMIT_AS` — Maximum address space (memory)
- `RLIMIT_CPU` — Maximum CPU time in seconds
- `RLIMIT_NOFILE` — Maximum open file descriptors
- `RLIMIT_NPROC` — Maximum number of processes

**Best Practice:**
```python
import subprocess
import resource

def run_with_limits(code: str, timeout: int = 30, max_memory: int = 100 * 1024 * 1024):
    # Run in subprocess with timeout and memory limit
    result = subprocess.run(
        ["python", "-c", code],
        timeout=timeout,
        capture_output=True,
        text=True,
        check=True,
        # Resource limits set via preexec_fn on Unix
        preexec_fn=lambda: resource.setrlimit(
            resource.RLIMIT_AS,
            (max_memory, max_memory)
        )
    )
    return result.stdout
```

---

### 1.3 Kernel-Level Isolation

Advanced isolation using Linux kernel security features. Requires Linux-specific implementation.

#### Sandtrap (Recommended for Agent Code) [2]

A Python sandbox designed specifically for **cooperative/agent-generated code** with three isolation levels:

| Level | Isolation | Performance | Security | Use Case |
|-------|-----------|-------------|----------|----------|
| `none` | In-process | Fastest | Lowest | Trusted code |
| `process` | Subprocess | Medium | Medium | Crash protection |
| `kernel` | seccomp + Landlock/Seatbelt | ~5ms startup | Highest | Untrusted code |

**Key Features:**
- AST rewriting with whitelist policies
- Attribute access control
- Import restrictions
- Resource usage limits (timeout, tick_limit)
- Cross-platform: Landlock (Linux), Seatbelt (macOS)

**Important Note:** Sandtrap explicitly states it's "designed as a walled garden for cooperative code (e.g. agent-generated scripts), not for adversarial inputs" [2].

#### Sandlock [2]

Rust-based process sandbox with ~5ms startup (vs 200ms for containers):
- No root, cgroups, or containers required
- Landlock (filesystem/network/IPC) + seccomp-bpf (syscall filtering)
- Python SDK via ctypes FFI
- HTTP-level ACL, port virtualization, COW filesystem

#### Compartment [2]

Zero-dependency Linux process isolation toolkit:
- **compartment-user:** rootless sandboxing (Landlock + seccomp + environment sanitization)
- **compartment-root:** full namespace container (pivot_root, capability dropping, seccomp)

---

### 1.4 Container-Based Isolation

**Docker/Firecracker/gVisor:**
- Highest isolation level
- Highest overhead (200-500ms startup)
- Best for multi-tenant environments
- Requires infrastructure dependency

**Not recommended for yoker:**
- Adds complexity and external dependencies
- Slow startup unsuitable for interactive agent tasks
- Overkill for single-user, cooperative code

---

## 2. Virtual Environment Management

### uv Integration

**Current State:** uv is CLI-first, not a programmatic API [3].

**Programmatic Usage:**
```python
import subprocess
import os

def setup_venv(project_path: str):
    """Create and sync virtual environment using uv."""
    env = os.environ.copy()

    # Create virtual environment
    subprocess.run(
        ["uv", "venv", ".venv"],
        cwd=project_path,
        env=env,
        check=True
    )

    # Sync dependencies from pyproject.toml
    subprocess.run(
        ["uv", "sync"],
        cwd=project_path,
        env=env,
        check=True
    )

def run_in_venv(project_path: str, code: str):
    """Execute code in project's virtual environment."""
    subprocess.run(
        ["uv", "run", "python", "-c", code],
        cwd=project_path,
        check=True,
        timeout=30
    )
```

**Key Environment Variables [3]:**
- `VIRTUAL_ENV` — Target virtual environment path
- `UV_CACHE_DIR` — Cache location
- `UV_PYTHON` — Python interpreter specification
- `UV_SYSTEM_PYTHON` — Use system Python

**yoker Integration:**
- Use `uv run python -c <code>` for execution
- Leverage existing `PathGuardrail` for filesystem access
- Configuration: `python.venv` path in yoker.toml

---

## 3. Security Model

### 3.1 Audit Hooks (PEP 578) [4]

**Purpose:** Monitoring/auditing, NOT sandboxing.

**Key Points:**
- Documentation explicitly states: "should not be used to build a sandbox" [4]
- Hooks are per-interpreter (Python API) or global (C API)
- Detection/auditing tool, not prevention

**Use Case:** Log security-relevant events for audit trail:
- `compile`, `exec`, `import` events
- `os.exec`, `os.system`, `subprocess.Popen`
- `socket.*`, `urllib.Request`
- Filesystem operations

**Implementation:**
```python
import sys

def audit_hook(event, args):
    if event in ("exec", "compile", "import"):
        logger.warning(f"Security event: {event} with args {args}")
    if event.startswith("os."):
        logger.warning(f"OS operation: {event}")

sys.addaudithook(audit_hook)
```

---

### 3.2 AST Validation

Pre-execution validation to block dangerous operations.

**Tools:**

| Tool | Focus | Maturity | Use Case |
|------|-------|----------|----------|
| **Bandit** [6] | Common security issues | High (7,897+ stars) | CI/CD, pre-execution scan |
| **PySecCheck** [6] | 5 critical rules | New (April 2026) | Lightweight validation |
| **KodeAgent** [6] | LLM code patterns | Medium | Agent-generated code |

**Dangerous Operations to Block:**
```python
# Code execution
exec(code_string)           # BLOCKED
eval(expression)            # BLOCKED
compile(source, ...)        # BLOCKED

# Shell commands
os.system(cmd)              # BLOCKED
subprocess.run(cmd, shell=True)  # BLOCKED

# Unsafe deserialization
pickle.loads(untrusted)     # BLOCKED
yaml.load(stream)           # BLOCKED (use safe_load)

# Introspection exploits
obj.__class__.__bases__     # BLOCKED
obj.__globals__             # BLOCKED
obj.__subclasses__()        # BLOCKED
```

**PySecCheck Rules [6]:**
- S001: Hardcoded passwords, API keys, tokens
- S002: Dangerous calls (exec, eval, os.system, pickle.loads)
- S003: Weak crypto (hashlib.md5, hashlib.sha1, random for security)
- S004: SQL injection (string concat, f-strings, .format())
- S005: Debug artifacts (debug=True, hardcoded IPs)

**Bandit Integration:**
```python
import bandit
from bandit.core import manager

def validate_code_safety(code: str) -> bool:
    """Run Bandit AST scan on code before execution."""
    mgr = manager.BanditManager(bandit.config.BanditConfig(), "file")
    # Scan code string and check results
    results = mgr.run_code(code)
    return len(results.get("results", [])) == 0
```

---

### 3.3 Resource Limits

**Memory Limits:**
```python
import resource

def set_memory_limit(max_bytes: int):
    """Limit process address space."""
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
```

**CPU Time Limits:**
```python
def set_cpu_limit(seconds: int):
    """Limit CPU time before SIGXCPU."""
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
```

**File Descriptor Limits:**
```python
def set_file_limit(max_files: int):
    """Limit open file descriptors."""
    resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, max_files))
```

**Important Notes:**
- `resource.setrlimit` limits only apply to the calling process
- For Docker: use native resource constraints (`mem_limit`, etc.)
- For subprocesses: set limits in `preexec_fn` on Unix

---

## 4. Guardrails and Permissions

### Integration with yoker's PathGuardrail

**Existing Architecture:** yoker already has `PathGuardrail` for filesystem access control.

**Python Tool Guardrails:**

```python
from dataclasses import dataclass
from typing import Optional
from yoker.tools.guardrails import Guardrail

@dataclass(frozen=True)
class PythonGuardrail(Guardrail):
    """Guardrail for Python code execution."""

    # Time limits
    timeout_seconds: int = 30

    # Memory limits (bytes)
    max_memory_bytes: int = 100 * 1024 * 1024  # 100 MB

    # CPU limits
    max_cpu_seconds: int = 10

    # File system access (leverage existing PathGuardrail)
    allowed_paths: tuple[str, ...] = ()
    write_allowed: bool = False

    # Import restrictions
    allowed_modules: tuple[str, ...] = ("os", "sys", "json", "re")

    # Network access
    network_allowed: bool = False

    # Isolation level
    isolation_level: str = "process"  # "none", "process", "kernel"
```

---

### Configuration Requirements

```toml
# yoker.toml

[tools.python]
enabled = true
default_timeout = 30
max_timeout = 300
default_memory_mb = 100
max_memory_mb = 500

[tools.python.guardrails]
# Import allowlist (stdlib only by default)
allowed_modules = ["os", "sys", "json", "re", "datetime", "math"]

# Filesystem access (integrate with PathGuardrail)
allowed_paths = ["${PROJECT_ROOT}"]
write_allowed = false

# Network access
network_allowed = false

# Isolation level: "none", "process", "kernel"
isolation_level = "process"

# Optional: venv configuration
venv_path = ".venv"
use_uv = true
```

---

## 5. Implementation Recommendation

### Recommended Approach: Defense-in-Depth

```
User Code
    |
    v
[1] AST Validation (Bandit/PySecCheck)
    |  - Block dangerous operations
    |  - Check for code execution patterns
    v
[2] Import Whitelist Check
    |  - Only allow specified modules
    |  - Validate imports against allowed_modules
    v
[3] Subprocess Execution
    |  - Isolated process
    |  - Timeout enforcement
    |  - Resource limits (memory, CPU)
    v
[4] Output Capture & Limits
    |  - Capture stdout/stderr
    |  - Limit output size
    v
[5] Audit Logging (PEP 578)
    |  - Log security events
    |  - Track executed code
    v
Result
```

### Isolation Level Choice

| Level | Security | Performance | Complexity | Recommendation |
|-------|----------|-------------|------------|----------------|
| **None (in-process)** | Low | High | Low | Only for completely trusted code |
| **Process (subprocess)** | Medium | Medium | Medium | **Default for yoker** |
| **Kernel (seccomp/Landlock)** | High | Low overhead | High | Optional, Linux-only |

**Recommendation:** Start with **subprocess isolation** as default. Add kernel-level isolation as optional Linux-only enhancement.

### Implementation Structure

```
src/yoker/tools/
    python.py              # PythonTool implementation
    python_guardrail.py    # Python-specific guardrails
    python_validator.py     # AST validation
    python_executor.py      # Subprocess execution
```

---

## 6. Trade-off Analysis

### Why Not RestrictedPython?

- Not a sandbox—only restricts language subset
- Multiple CVEs (security track record is poor)
- Requires manual configuration of globals/locals
- Library access still available after configuration

### Why Not PyPy Sandbox?

- Unmaintained (v2 in development)
- Not production-ready
- Adds interpreter dependency

### Why Not Container-Based Isolation?

- 200-500ms startup overhead
- Infrastructure dependency (Docker)
- Overkill for single-user cooperative code
- Slow for interactive agent tasks

### Why Subprocess + AST + Resource Limits?

- Defense-in-depth: multiple independent layers
- Each layer catches different classes of issues
- Moderate complexity, good security
- Fast enough for interactive use
- Works on all platforms (with kernel-level as Linux-only enhancement)

---

## 7. Near-Miss Tier

The following approaches ranked just below the recommended approach:

### Sandtrap (Kernel-Level Isolation)

- **Why it nearly made the cut:** Purpose-built for agent-generated code with 3-level isolation
- **Why it ranked below:** Adds external dependency, kernel-level requires Linux/macOS, may be overkill for cooperative code
- **Best for:** High-security environments running untrusted agent code on Linux

### Docker/Firecracker Containers

- **Why it nearly made the cut:** Highest isolation level, multi-tenant safe
- **Why it ranked below:** Slow startup (200-500ms), infrastructure dependency, complexity
- **Best for:** Multi-tenant platforms running untrusted user code

### RestrictedPython + Subprocess

- **Why it nearly made the cut:** Additional language-level restrictions before execution
- **Why it ranked below:** CVE history, incomplete security, adds complexity without full protection
- **Best for:** Environments where you want to restrict Python syntax/features, not just operations

---

## 8. Security Considerations

### Threat Model

**Assumed:** Agent-generated code is cooperative (not actively malicious), but may contain:
- Infinite loops
- Memory exhaustion
- Dangerous library calls
- Unintended filesystem access

**NOT Assumed:** Actively malicious code trying to escape sandbox. For that, use containers or hardware isolation.

### What to Block

**Always:**
- `exec()`, `eval()`, `compile()` with user input
- `os.system()`, `subprocess.run(..., shell=True)`
- `pickle.loads()` on untrusted data
- Introspection exploits (`__class__`, `__bases__`, `__globals__`)

**Conditionally (via guardrails):**
- Import statements (whitelist approach)
- Filesystem operations (via PathGuardrail)
- Network operations (block by default)
- Process creation (block by default)

### Error Handling

```python
from dataclasses import dataclass

@dataclass
class PythonResult:
    success: bool
    output: str
    error: Optional[str]
    timed_out: bool
    memory_exceeded: bool
```

---

## 9. Example Usage Patterns

### Basic Execution

```python
from yoker.tools import PythonTool
from yoker.tools.python_guardrail import PythonGuardrail

guardrail = PythonGuardrail(
    timeout_seconds=30,
    max_memory_bytes=100 * 1024 * 1024,
    allowed_modules=["os", "sys", "json"],
)

tool = PythonTool(guardrail=guardrail)
result = tool.execute("import json; print(json.dumps({'status': 'ok'}))")
```

### With Virtual Environment

```python
guardrail = PythonGuardrail(
    venv_path=".venv",
    use_uv=True,
    timeout_seconds=60,
)

# Code will run in .venv context
result = tool.execute("import requests; print(requests.__version__)")
```

### Kernel-Level Isolation (Linux-only)

```python
guardrail = PythonGuardrail(
    isolation_level="kernel",  # Uses seccomp + Landlock
    timeout_seconds=30,
)
```

---

## 10. Key Takeaways

1. **No single solution is sufficient**—use defense-in-depth
2. **RestrictedPython is NOT a sandbox**—only restricts language subset
3. **Subprocess isolation is the baseline**—always use it
4. **AST validation catches dangerous patterns**—use Bandit or PySecCheck
5. **Resource limits prevent runaway code**—set timeout, memory, CPU limits
6. **Sandtrap is purpose-built for agent code**—consider for kernel-level isolation
7. **Containers are overkill**—too slow for interactive use
8. **PEP 578 is for auditing**—not for sandboxing
9. **uv is CLI-first**—use subprocess to invoke
10. **Cooperative code assumption**—not designed for adversarial inputs

---

## Sources

[1] RestrictedPython Documentation - https://restrictedpython.readthedocs.io/en/stable/idea.html - Accessed 2026-05-05

[2] Sandtrap GitHub Repository - https://github.com/ashenfad/sandtrap - Accessed 2026-05-05

[3] uv Documentation - https://docs.astral.sh/uv/reference/cli/ - Accessed 2026-05-05

[4] PEP 578 – Python Runtime Audit Hooks - https://peps.python.org/pep-0578/ - Accessed 2026-05-05

[5] Python subprocess documentation - https://docs.python.org/3/library/subprocess.html - Accessed 2026-05-05

[6] Bandit GitHub Repository - https://github.com/pycqa/bandit - Accessed 2026-05-05