# API Design: Python Tool

**Status:** Research Complete
**Date:** 2026-05-05
**Research:** [research/2026-05-05-python-execution-safety/](../research/2026-05-05-python-execution-safety/)

---

## Executive Summary

This document defines the implementation strategy for a safe Python code execution tool in yoker, based on comprehensive research into sandboxing approaches, subprocess isolation, AST validation, and kernel-level security.

**Recommendation:** Implement **subprocess isolation with AST validation and resource limits** as the default approach. This provides defense-in-depth protection suitable for cooperative agent-generated code while maintaining acceptable performance for interactive use.

---

## Research Findings

### Safe Execution Approaches

| Approach | Security | Performance | Complexity | Verdict |
|----------|----------|-------------|------------|---------|
| **RestrictedPython** | Low | High | Medium | NOT RECOMMENDED: Not a sandbox, multiple CVEs |
| **PyPy Sandbox** | Medium | Medium | High | NOT RECOMMENDED: Unmaintained, v2 in dev |
| **Subprocess + Limits** | Medium | High | Low | **RECOMMENDED: Baseline protection** |
| **Kernel-Level (Sandtrap)** | High | Medium (~5ms) | High | OPTIONAL: Linux/macOS only |
| **Containers** | Very High | Low (200-500ms) | Very High | NOT RECOMMENDED: Overkill for cooperative code |

### Key Security Insights

1. **RestrictedPython is NOT a sandbox** [1]
   - Only restricts language subset
   - Library calls still available
   - Multiple CVEs (2023-2025)

2. **PEP 578 is for auditing, NOT sandboxing** [4]
   - Documentation explicitly states: "should not be used to build a sandbox"
   - Detection/monitoring tool only

3. **Sandtrap is purpose-built for agent code** [2]
   - "Walled garden for cooperative code, not adversarial inputs"
   - 3 isolation levels: none/process/kernel
   - Uses AST rewriting + whitelist policies

4. **Defense-in-depth is required** [5]
   - No single solution provides complete isolation
   - Combine: AST validation + subprocess + resource limits + audit logging

---

## Recommended Implementation

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Python Tool                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │    Code     │─▶│ AST Validator│─▶│   Guardrail     │   │
│  │   Input     │  │  (Bandit)    │  │    Check        │   │
│  └─────────────┘  └──────────────┘  └─────────────────┘   │
│                            │                    │           │
│                            ▼                    ▼           │
│                    ┌───────────────────────────────┐       │
│                    │     Subprocess Executor       │       │
│                    │  ┌─────────────────────────┐  │       │
│                    │  │  Resource Limits        │  │       │
│                    │  │  - timeout: 30s         │  │       │
│                    │  │  - memory: 100MB       │  │       │
│                    │  │  - cpu: 10s             │  │       │
│                    │  └─────────────────────────┘  │       │
│                    └───────────────────────────────┘       │
│                            │                               │
│                            ▼                               │
│                    ┌───────────────┐                       │
│                    │    Output     │                       │
│                    │   Capture     │                       │
│                    └───────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Defense-in-Depth Layers

**Layer 1: AST Validation**
- Use Bandit or PySecCheck to scan code before execution
- Block dangerous operations: `exec`, `eval`, `compile`, `os.system`, `pickle.loads`
- Block introspection exploits: `__class__`, `__bases__`, `__globals__`
- Integration: `bandit` package (7,897+ stars, mature)

**Layer 2: Import Whitelist**
- Validate all `import` statements against allowed list
- Default: stdlib only (`os`, `sys`, `json`, `re`, `datetime`, `math`)
- Optional: third-party packages via configuration

**Layer 3: Filesystem Guardrail**
- Reuse existing `PathGuardrail` from yoker
- Restrict file operations to allowed paths
- Control read/write permissions separately

**Layer 4: Subprocess Isolation**
- Execute in separate process (can be killed without affecting host)
- Set resource limits: timeout, memory, CPU
- Capture stdout/stderr with size limits

**Layer 5: Network Guardrail**
- Block network operations by default
- Optional: allow via configuration with domain whitelist

**Layer 6: Audit Logging**
- Use PEP 578 `sys.addaudithook()` for monitoring
- Log security events: imports, exec, file ops, network ops
- Not for prevention—only for audit trail

---

## API Design

### Configuration Schema

```toml
# yoker.toml

[tools.python]
enabled = true

# Execution limits
default_timeout_seconds = 30
max_timeout_seconds = 300
default_memory_mb = 100
max_memory_mb = 500
default_cpu_seconds = 10
max_cpu_seconds = 60

# Output limits
max_output_bytes = 1024 * 1024  # 1 MB

# Import restrictions
allowed_modules = ["os", "sys", "json", "re", "datetime", "math"]
blocked_modules = ["subprocess", "socket", "requests"]

# Filesystem (integrate with PathGuardrail)
allowed_paths = ["${PROJECT_ROOT}"]
write_allowed = false

# Network
network_allowed = false
allowed_domains = []

# Isolation level: "none", "process", "kernel"
isolation_level = "process"

# Virtual environment
venv_path = ".venv"
use_uv = true

# Security
require_ast_validation = true
audit_logging = true
```

### PythonGuardrail

```python
from dataclasses import dataclass
from typing import Optional, Tuple, FrozenSet
from yoker.tools.guardrails import Guardrail

@dataclass(frozen=True)
class PythonGuardrail(Guardrail):
    """Guardrails for Python code execution."""

    # Time limits
    timeout_seconds: int = 30
    max_timeout_seconds: int = 300

    # Memory limits (bytes)
    max_memory_bytes: int = 100 * 1024 * 1024  # 100 MB

    # CPU limits
    max_cpu_seconds: int = 10

    # Output limits
    max_output_bytes: int = 1024 * 1024  # 1 MB

    # Import restrictions
    allowed_modules: FrozenSet[str] = frozenset(["os", "sys", "json", "re", "datetime", "math"])
    blocked_modules: FrozenSet[str] = frozenset(["subprocess", "socket", "requests"])

    # Filesystem (integrate with PathGuardrail)
    allowed_paths: Tuple[str, ...] = ()
    write_allowed: bool = False

    # Network
    network_allowed: bool = False
    allowed_domains: Tuple[str, ...] = ()

    # Isolation level
    isolation_level: str = "process"  # "none", "process", "kernel"

    # Virtual environment
    venv_path: Optional[str] = ".venv"
    use_uv: bool = True

    # Security options
    require_ast_validation: bool = True
    audit_logging: bool = True
```

### PythonTool API

```python
from dataclasses import dataclass
from typing import Optional
from yoker.tools.base import Tool, ToolResult
from yoker.tools.python_guardrail import PythonGuardrail

@dataclass
class PythonResult:
    """Result of Python code execution."""
    success: bool
    output: str
    error: Optional[str]
    timed_out: bool
    memory_exceeded: bool
    execution_time_seconds: float
    memory_used_bytes: int

class PythonTool(Tool):
    """Execute Python code safely with configurable guardrails."""

    name = "python"
    description = "Execute Python code with safety restrictions"

    def __init__(self, guardrail: PythonGuardrail):
        self.guardrail = guardrail
        self.validator = ASTValidator() if guardrail.require_ast_validation else None

    def execute(self, code: str, timeout: Optional[int] = None) -> ToolResult[PythonResult]:
        """
        Execute Python code.

        Args:
            code: Python code to execute
            timeout: Optional timeout override (must be <= max_timeout_seconds)

        Returns:
            ToolResult with PythonResult or error
        """
        # 1. AST validation
        if self.validator:
            validation_error = self.validator.validate(code)
            if validation_error:
                return ToolResult(error=validation_error)

        # 2. Guardrail check
        guardrail_error = self._check_guardrails(code)
        if guardrail_error:
            return ToolResult(error=guardrail_error)

        # 3. Execute in subprocess with limits
        result = self._execute_in_subprocess(code, timeout)

        return ToolResult(result=result)

    def _check_guardrails(self, code: str) -> Optional[str]:
        """Check all guardrails before execution."""
        # Import whitelist check
        # Filesystem path check (reuse PathGuardrail)
        # Network check
        # Return error message or None
        pass

    def _execute_in_subprocess(self, code: str, timeout: Optional[int]) -> PythonResult:
        """Execute code in subprocess with resource limits."""
        pass
```

### AST Validator

```python
import ast
from typing import Optional, List
import bandit
from bandit.core import manager

class ASTValidator:
    """Validate Python code for safety before execution."""

    # Dangerous operations to block
    BLOCKED_CALLS = {
        # Code execution
        "exec", "eval", "compile",
        # Shell commands
        "os.system", "os.popen", "subprocess.run",
        # Unsafe deserialization
        "pickle.loads", "yaml.load",
    }

    # Dangerous attribute access
    BLOCKED_ATTRS = {
        "__class__", "__bases__", "__subclasses__",
        "__globals__", "__code__", "__builtins__",
    }

    def validate(self, code: str) -> Optional[str]:
        """
        Validate code for safety.

        Returns:
            Error message if validation fails, None if safe
        """
        # Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error: {e}"

        # Check for blocked operations
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name in self.BLOCKED_CALLS:
                    return f"Blocked operation: {call_name}"

            if isinstance(node, ast.Attribute):
                if node.attr in self.BLOCKED_ATTRS:
                    return f"Blocked attribute access: {node.attr}"

        # Run Bandit security scan
        issues = self._run_bandit(code)
        if issues:
            return f"Security issues found: {', '.join(issues)}"

        return None

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract call name from AST node."""
        # Handle both simple and qualified names
        pass

    def _run_bandit(self, code: str) -> List[str]:
        """Run Bandit security scan on code."""
        # Use bandit manager to scan code string
        pass
```

---

## Subprocess Executor Implementation

### Resource Limits (Unix)

```python
import subprocess
import resource
import os
from typing import Optional

def set_resource_limits(guardrail: PythonGuardrail):
    """Set resource limits for subprocess (Unix only)."""
    # Memory limit
    soft, hard = guardrail.max_memory_bytes, resource.RLIM_INFINITY
    resource.setrlimit(resource.RLIMIT_AS, (soft, hard))

    # CPU time limit
    soft, hard = guardrail.max_cpu_seconds, guardrail.max_cpu_seconds + 1
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))

    # File descriptor limit
    soft, hard = 64, 64  # Limit open files
    resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))

def execute_with_limits(
    code: str,
    guardrail: PythonGuardrail,
    timeout: Optional[int] = None
) -> PythonResult:
    """Execute code in subprocess with resource limits."""

    timeout = timeout or guardrail.timeout_seconds

    # Build execution command
    if guardrail.use_uv and guardrail.venv_path:
        cmd = ["uv", "run", "--directory", guardrail.venv_path, "python", "-c", code]
    else:
        cmd = ["python", "-c", code]

    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=True,
            preexec_fn=lambda: set_resource_limits(guardrail) if os.name != 'nt' else None
        )

        return PythonResult(
            success=True,
            output=result.stdout[:guardrail.max_output_bytes],
            error=None,
            timed_out=False,
            memory_exceeded=False,
            execution_time_seconds=0.0,  # Track separately
            memory_used_bytes=0
        )

    except subprocess.TimeoutExpired:
        return PythonResult(
            success=False,
            output="",
            error=f"Execution timed out after {timeout} seconds",
            timed_out=True,
            memory_exceeded=False,
            execution_time_seconds=timeout,
            memory_used_bytes=0
        )

    except subprocess.CalledProcessError as e:
        return PythonResult(
            success=False,
            output="",
            error=e.stderr or f"Process exited with code {e.returncode}",
            timed_out=False,
            memory_exceeded=False,
            execution_time_seconds=0.0,
            memory_used_bytes=0
        )
```

### Audit Hook (PEP 578)

```python
import sys
import logging

logger = logging.getLogger(__name__)

def setup_audit_hook():
    """Set up PEP 578 audit hook for security logging."""
    def audit_hook(event: str, args):
        # Log security-relevant events
        security_events = {
            "exec", "compile", "import",
            "os.exec", "os.system", "os.spawn",
            "subprocess.Popen",
            "socket.connect", "socket.bind",
            "open", "os.open",
        }

        if event in security_events:
            logger.info(f"Security event: {event} args={args}")

    sys.addaudithook(audit_hook)
```

---

## Integration with yoker Architecture

### File Structure

```
src/yoker/tools/
    __init__.py
    base.py                  # Tool ABC and ToolResult
    guardrails.py            # Guardrail protocol
    path_guardrail.py        # PathGuardrail implementation
    python.py                # PythonTool implementation
    python_guardrail.py       # PythonGuardrail dataclass
    python_validator.py       # AST validation
    python_executor.py        # Subprocess execution
```

### Tool Registry Integration

```python
# src/yoker/tools/__init__.py

from yoker.tools.python import PythonTool
from yoker.tools.python_guardrail import PythonGuardrail

def create_default_registry(config: Config) -> ToolRegistry:
    """Create default tool registry with configured guardrails."""
    registry = ToolRegistry()

    # Read Python tool configuration
    python_config = config.tools.get("python", {})
    if python_config.get("enabled", False):
        guardrail = PythonGuardrail(
            timeout_seconds=python_config.get("default_timeout_seconds", 30),
            max_memory_bytes=python_config.get("default_memory_mb", 100) * 1024 * 1024,
            allowed_modules=frozenset(python_config.get("allowed_modules", [])),
            # ... other config
        )
        registry.register(PythonTool(guardrail=guardrail))

    return registry
```

### Event Emission

```python
# Emit events for agent feedback
from yoker.events import ToolEvent, ContentEvent

class PythonTool(Tool):
    def execute(self, code: str, timeout: Optional[int] = None) -> ToolResult[PythonResult]:
        # Emit tool start event
        yield ToolEvent(name="python", action="start", code=code[:100])

        # Execute with limits
        result = self._execute_in_subprocess(code, timeout)

        # Emit result
        yield ContentEvent(content=result.output)
        yield ToolEvent(name="python", action="end", success=result.success)

        return ToolResult(result=result)
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_tools/test_python.py

def test_ast_validator_blocks_exec():
    """AST validator should block exec() calls."""
    validator = ASTValidator()
    error = validator.validate("exec('print(1)')")
    assert error is not None
    assert "exec" in error

def test_ast_validator_blocks_dunder_attrs():
    """AST validator should block __class__ etc."""
    validator = ASTValidator()
    error = validator.validate("x.__class__.__bases__")
    assert error is not None
    assert "__class__" in error or "__bases__" in error

def test_subprocess_timeout():
    """Subprocess should enforce timeout."""
    guardrail = PythonGuardrail(timeout_seconds=1)
    tool = PythonTool(guardrail=guardrail)
    result = tool.execute("while True: pass", timeout=1)
    assert result.result.timed_out

def test_memory_limit():
    """Subprocess should enforce memory limit."""
    guardrail = PythonGuardrail(max_memory_bytes=10 * 1024 * 1024)  # 10 MB
    tool = PythonTool(guardrail=guardrail)
    result = tool.execute("x = ' ' * 100 * 1024 * 1024")  # 100 MB string
    assert result.result.memory_exceeded

def test_import_whitelist():
    """Should block imports not in whitelist."""
    guardrail = PythonGuardrail(allowed_modules=frozenset(["os", "sys"]))
    tool = PythonTool(guardrail=guardrail)
    result = tool.execute("import requests")
    assert not result.result.success
    assert "import" in result.result.error.lower()
```

### Integration Tests

```python
def test_uv_venv_execution():
    """Should execute in virtual environment with uv."""
    # Create temp venv
    # Execute code requiring installed package
    # Verify package available
    pass

def test_kernel_isolation_level():
    """Should use kernel-level isolation when configured."""
    # Configure guardrail with isolation_level="kernel"
    # Verify seccomp/Landlock restrictions applied
    pass
```

---

## Security Checklist

Before deploying Python Tool, verify:

- [ ] AST validation blocks all dangerous operations
- [ ] Import whitelist is properly enforced
- [ ] Timeout enforcement works (test with infinite loop)
- [ ] Memory limits work (test with large allocation)
- [ ] CPU limits work (test with CPU-bound computation)
- [ ] Filesystem guardrails integrate with PathGuardrail
- [ ] Network operations are blocked by default
- [ ] Output size is limited to prevent memory exhaustion
- [ ] Audit logging captures all security events
- [ ] Subprocess cleanup happens on timeout/kill
- [ ] Error messages don't leak sensitive information
- [ ] All tests pass (unit + integration)

---

## Performance Characteristics

| Isolation Level | Startup Time | Memory Overhead | Security Level |
|-----------------|--------------|-----------------|----------------|
| `none` (in-process) | ~0ms | 0 MB | Low |
| `process` (subprocess) | ~50-100ms | 10-20 MB | Medium |
| `kernel` (seccomp/Landlock) | ~5ms | 10-20 MB | High |

**Recommendation:** Use `process` isolation as default. It provides good security with acceptable overhead for interactive use.

---

## Future Enhancements

### Phase 1 (MVP)
- Subprocess isolation with resource limits
- AST validation (Bandit)
- Import whitelist
- Timeout enforcement
- Output capture

### Phase 2
- Kernel-level isolation (Linux only, optional)
- Virtual environment support via uv
- Filesystem guardrail integration
- Network guardrail

### Phase 3
- Audit hook integration (PEP 578)
- Metrics collection (execution time, memory usage)
- Hot-reload of configuration
- Multiple isolation level profiles

---

## References

1. [RestrictedPython Documentation](https://restrictedpython.readthedocs.io/en/stable/idea.html) - Language subset restrictions
2. [Sandtrap GitHub](https://github.com/ashenfad/sandtrap) - Agent-focused sandbox
3. [uv Documentation](https://docs.astral.sh/uv/reference/cli/) - Virtual environment management
4. [PEP 578](https://peps.python.org/pep-0578/) - Python Runtime Audit Hooks
5. [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html) - Subprocess management
6. [Bandit GitHub](https://github.com/pycqa/bandit) - AST security scanner

---

## Changelog

- **2026-05-05:** Initial API design based on research findings