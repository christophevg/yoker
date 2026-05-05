# Sources: Python Code Execution Safety

**Date**: 2026-05-05T00:00:00Z
**Previous Research**: none

---

## Searches

### search-1

- **Query**: python sandbox safe code execution RestrictedPython pypy-sandbox security 2026
- **Timestamp**: 2026-05-05T00:05:00Z
- **Results**:
  - [RestrictedPython v8.1](https://pypi.org/project/RestrictedPython/) - Python package for restricted code execution
  - [The idea behind RestrictedPython](https://restrictedpython.readthedocs.io/en/stable/idea.html) - Documentation explaining concept and limitations
  - [zopefoundation/RestrictedPython](https://github.com/zopefoundation/RestrictedPython) - GitHub repository
  - [PyPy's sandboxing features](https://pypy.readthedocs.io/en/latest/sandbox.html) - PyPy sandbox documentation
  - [API overview](https://restrictedpython.readthedocs.io/en/latest/usage/api.html) - RestrictedPython API documentation
- **Key Findings**:
  - RestrictedPython is NOT a sandbox, only restricts language subset
  - PyPy sandbox is unmaintained but v2 in development
  - Multiple CVEs in RestrictedPython (2023-2025)
  - PyPy uses two-process model for better isolation

### search-2

- **Query**: python subprocess isolation seccomp namespaces container sandbox security 2026
- **Timestamp**: 2026-05-05T00:15:00Z
- **Results**:
  - [ashenfad/sandtrap](https://github.com/ashenfad/sandtrap) - Python sandbox with 3 isolation levels (process, kernel)
  - [nmicic/compartment](https://github.com/nmultikernel/sandlock) - Linux process isolation toolkit
  - [multikernel/sandlock](https://github.com/multikernel/sandlock) - Lightweight process sandbox using Landlock + seccomp
  - [shcherbak-ai/tethered](https://github.com/shcherbak-ai/tethered) - Runtime network egress control for Python
  - [Tracecat nsjail hardening](https://github.com/TracecatHQ/tracecat/pull/2478) - Seccomp filtering for Python workloads
- **Key Findings**:
  - Sandtrap offers 3 isolation levels: None (in-process), Process (subprocess), Kernel (seccomp/Landlock/Seatbelt)
  - Compartment provides zero-dependency Linux sandboxing with Landlock + seccomp
  - Sandlock is Rust-based with ~5ms startup (vs 200ms for containers), no root required
  - Tethered uses Python audit hooks (PEP 578) for network egress control
  - 2026 trend: defense-in-depth combining Landlock + seccomp + namespaces without root

### search-3

- **Query**: uv python virtual environment management programmatic API 2026
- **Timestamp**: 2026-05-05T00:25:00Z
- **Results**:
  - [Commands | uv](https://docs.astral.sh/uv/reference/cli/) - Complete CLI reference
  - [Using environments | uv](https://docs.astral.sh/uv/pip/environments/) - Environment management
  - [Working on projects | uv](https://docs.astral.sh/uv/guides/projects/) - Project-based workflow
  - [Running commands | uv](https://docs.astral.sh/uv/concepts/projects/run/) - uv run command
  - [Features | uv](https://docs.astral.sh/uv/getting-started/features/) - Feature overview
- **Key Findings**:
  - uv is CLI-first, not a programmatic API
  - Use via subprocess: `uv venv`, `uv sync`, `uv run`
  - Project-based: `uv init`, `uv add`, `.venv` auto-created
  - Environment variables: `VIRTUAL_ENV`, `UV_CACHE_DIR`, `UV_PYTHON`
  - Lockfile-based: `uv.lock` for deterministic environments

### search-4

- **Query**: Python PEP 578 audit hooks security sys.addaudithook 2026
- **Timestamp**: 2026-05-05T00:30:00Z
- **Results**:
  - [PEP 578 – Python Runtime Audit Hooks](https://peps.python.org/pep-0578/) - Official PEP
  - [Audit events table](https://docs.python.org/3/library/audit_events.html) - Complete audit events list
  - [cpython issue #87604](https://github.com/python/cpython/issues/87604) - Clarification on limitations
  - [cpython audit_events.rst](https://github.com/python/cpython/blob/main/Doc/library/audit_events.rst) - Documentation
- **Key Findings**:
  - PEP 578 is for AUDITING/MONITORING, NOT SANDBOXING
  - Documentation explicitly states hooks should not be used to build sandbox
  - Hooks are per-interpreter (Python API) or global (C API)
  - Detection/auditing tool, not prevention
  - Events: compile, exec, import, os.exec, socket.*, file ops

### search-5

- **Query**: Python subprocess resource limits memory CPU timeout security best practices 2026
- **Timestamp**: 2026-05-05T00:35:00Z
- **Results**:
  - [resource module documentation](https://docs.python.org/3.15/library/resource.html) - Python 3.15 resource limits
  - [subprocess module documentation](https://docs.python.org/3/library/subprocess.html) - Subprocess management
  - [Stack Overflow: CPU time and memory to subprocess](https://stackoverflow.com/questions/68424336/) - Implementation examples
  - [Measuring CPU and Memory for subprocess](https://valarmorghulis.io/tech/202505-measuring-cpu-memory-python-subprocess/) - Measurement techniques
  - [Python subprocess guide](https://docs.kanaries.net/topics/Python/python-subprocess) - Best practices
- **Key Findings**:
  - resource module: RLIMIT_AS (memory), RLIMIT_CPU (CPU time), RLIMIT_NOFILE, RLIMIT_NPROC
  - NEVER use shell=True with untrusted input
  - Always set timeouts with subprocess.run()
  - Use check=True to catch failures
  - For Docker: use native resource limits, not resource.setrlimit
  - Python 3.12+: Windows shell search order changed for security

### search-6

- **Query**: Python AST validation security code analysis disallow dangerous operations 2026
- **Timestamp**: 2026-05-05T00:40:00Z
- **Results**:
  - [KodeAgent pattern_detector](https://kodeagent.readthedocs.io/en/latest/_modules/kodeagent/pattern_detector.html) - LLM code security patterns
  - [PyCQA/bandit](https://github.com/pycqa/bandit) - Mature security linter (7,897+ stars)
  - [SANC18/pyseccheck](https://github.com/SANC18/pyseccheck) - Focused security linter (April 2026)
  - [KodeAgent code_runner](https://kodeagent.readthedocs.io/en/latest/_modules/kodeagent/code_runner.html) - Code execution with security
  - [SecureFlow Scanner](https://github.com/BarakMozesPro/secureflow-scanner) - 31 OWASP check plugins (March 2026)
- **Key Findings**:
  - Bandit: Most mature AST-based security scanner (7,897+ stars, 150+ contributors)
  - PySecCheck: 5 rules (hardcoded secrets, dangerous calls, weak crypto, SQL injection, debug artifacts)
  - KodeAgent: Multi-layer (AST + pattern detection + LLM review)
  - Dangerous ops blocked: exec, eval, compile, os.system, subprocess(shell=True), pickle.loads
  - Introspection blocked: __class__, __bases__, __globals__, __subclasses__

## Fetches

### fetch-1

- **URL**: https://restrictedpython.readthedocs.io/en/stable/idea.html
- **Timestamp**: 2026-05-05T00:10:00Z
- **Source**: search-1
- **Title**: The Idea Behind RestrictedPython
- **Content**: [fetched/fetch-1.md](fetched/fetch-1.md)
- **Summary**: RestrictedPython defines a restricted language subset but is NOT a complete sandbox. Requires explicit configuration of globals/locals, policy for attribute access, and whitelisting of libraries. Provides compile_restricted() and limited builtins.
- **Key Excerpts**:
  - "defines a safe subset of the Python programming language"
  - "not sufficient as a sandbox environment, as all calls to libraries are still available"
  - "There should be additional preventive measures taken"

### fetch-2

- **URL**: https://github.com/ashenfad/sandtrap
- **Timestamp**: 2026-05-05T00:20:00Z
- **Source**: search-2
- **Title**: Sandtrap - Python Sandbox with Kernel-Level Isolation
- **Content**: [fetched/fetch-2.md](fetched/fetch-2.md)
- **Summary**: Sandtrap provides 3 isolation levels (none/process/kernel) using AST rewriting + whitelist policies. Kernel level uses seccomp, Landlock (Linux), Seatbelt (macOS). Designed for cooperative/agent-generated code, not adversarial inputs.
- **Key Excerpts**:
  - "designed as a walled garden for cooperative code (e.g. agent-generated scripts), not for adversarial inputs"
  - Three isolation levels: in-process, subprocess, kernel-level
  - ~5ms startup for kernel mode (Sandlock comparison)

### fetch-3

- **URL**: https://github.com/pycqa/bandit
- **Timestamp**: 2026-05-05T00:45:00Z
- **Source**: search-6
- **Title**: Bandit - Python Security Linter
- **Content**: [fetched/fetch-3.md](fetched/fetch-3.md)
- **Summary**: Bandit processes files, builds AST, and runs security plugins. Most mature tool (7,897+ stars). Can be integrated via CI/CD, pre-commit hooks, Docker containers, or programmatic API.
- **Key Excerpts**:
  - "Bandit processes each file, builds an AST from it, and runs appropriate plugins against the AST nodes"
  - "security linter" designed to find "common security issues in Python code"
  - Docker images: ghcr.io/pycqa/bandit/bandit

## Citations

<!-- Track citations used in report -->

## Excluded Findings

<!-- Record information found but excluded as incorrect/irrelevant -->