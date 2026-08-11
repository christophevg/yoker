# Contributing to Yoker

Thank you for your interest in contributing to Yoker! This guide covers the
practical steps for setting up a development environment, making changes, and
submitting pull requests.

## Project Overview

Yoker is a Python agent harness with configurable tools, guardrails, and
multi-provider LLM backend integration. It lets developers enhance existing
Python code with LLM-powered features without needing to build the underlying
agent infrastructure.

For a detailed map of the codebase, module structure, and architectural
conventions, read [AGENTS.md](AGENTS.md) — it is the primary reference for
anyone working on the codebase.

## Development Setup

### Prerequisites

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/) for dependency management
- Git

### Getting Started

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker
make env-dev   # Create virtual environment and install all dependencies
```

This creates a `.venv/` with all development, docs, and test dependencies
installed. Activate it with `source .venv/bin/activate` or prefix commands
with `uv run`.

### Useful Make Targets

| Target | Description |
|--------|-------------|
| `make test` | Run tests with pytest |
| `make test TEST=file` | Run a specific test file |
| `make test-cov` | Run tests with coverage reporting |
| `make typecheck` | Run type checking (mypy) |
| `make lint` | Run linting (ruff) |
| `make format` | Format code and fix linting issues |
| `make format-check` | Run all quality checks without fixing |
| `make check` | Run all quality checks (format + lint + typecheck + test) |
| `make demos` | Generate all demo screenshots |
| `make demos-to-docs` | Copy demo screenshots to `docs/_static/` |
| `make docs` | Build HTML documentation |
| `make docs-view` | Build and open documentation in browser |
| `make build` | Build distribution packages |
| `make clean` | Remove build artifacts |
| `make clean-all` | Remove virtualenv and lock file |

## Code Conventions

### Indentation

**Two spaces** in all file types — Python, Markdown, TOML, YAML. This is
non-negotiable and enforced by the formatter.

### Imports

Use **fully qualified imports**:

```python
# Correct
from yoker.backends.protocol import ChatChunk
from yoker.tools.annotations import Path

# Wrong
from yoker.backends import ChatChunk
```

### Entry Point

`python -m yoker` is the application entry point.

### Version Source of Truth

The version is defined in `src/yoker/__init__.py` (`__version__`) and must
match `pyproject.toml` (`version`). Version bumps are handled by the release
workflow — do not bump versions in regular PRs.

## Quality Workflow

Before submitting a PR, ensure all checks pass:

```bash
make check
```

This runs:

1. **Format check** — verifies code is properly formatted
2. **Lint** — checks for linting issues
3. **Typecheck** — runs mypy type checking
4. **Tests** — runs the full test suite

If any check fails, fix the issue and re-run. You can auto-fix formatting and
linting issues with `make format`.

### Known Cosmetic Noise

On Python 3.11, `make test` may emit a `RuntimeError: Event loop is closed`
traceback in stderr. This is a known CPython 3.11 bug unrelated to Yoker — all
tests pass (exit code 0). Do not investigate or attempt to fix it.

## Contributing Process

### 1. Fork and Branch

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/<your-username>/yoker.git
cd yoker
git remote add upstream https://github.com/christophevg/yoker.git
git checkout -b my-feature-branch
```

Branch from `master` for all work.

### 2. Write an Analysis Document

For any non-trivial change, create an analysis document in the `analysis/`
folder describing what you intend to change and why. This helps reviewers
understand your approach before diving into code.

The analysis document should cover:

- **Problem**: What issue are you addressing?
- **Proposed solution**: How do you intend to solve it?
- **Alternatives considered**: What other approaches did you consider?
- **Impact**: What parts of the codebase are affected?

### 3. Implement

Write your code following the conventions above. Add or update tests as
needed. Ensure `make check` passes before moving on.

### 4. Create a Pull Request

```bash
git add .
git commit -m "feat: add X"  # see commit conventions below
git push origin my-feature-branch
```

Open a PR on GitHub. In the PR description:

- Explain what the PR does and why
- Reference the analysis document for non-trivial changes
- Note any breaking changes

### 5. Review and Iterate

- Wait for feedback from maintainers
- Discuss any concerns — the analysis document helps ground the discussion
- Make changes as requested
- Ensure your branch is rebased on the latest `master`:

```bash
git fetch upstream
git rebase upstream/master
```

- Re-run `make check` after rebasing
- Request re-review when ready

### 6. Merge

After approval, a maintainer will merge your PR. Squash-merge is preferred to
keep the commit history clean.

## Commit Conventions

### Atomic Commits

Each commit should represent one logical change. If a PR addresses multiple
concerns, split them into separate commits (or separate PRs).

### Conventional Format

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <description>

[optional body]

[optional footer]
```

Common types:

| Type | Use for |
|------|---------|
| `feat` | New features |
| `fix` | Bug fixes |
| `docs` | Documentation changes |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks (deps, CI, etc.) |

### Agent-Made Commits

When a commit is created by an agent (e.g., via Yoker itself), add this
trailer line:

```
🤖 Implemented together with Yoker
```

Do **not** use `Co-authored-by` format.

## Documentation

Documentation is a first-class contribution. If your change affects user-facing
behavior, update the relevant documentation:

| Document | What it covers |
|----------|---------------|
| `README.md` | Project overview, installation, quick start |
| `docs/` | Full Read the Docs documentation |
| `PACKAGE.md` | Guide for developers using Yoker as a library |
| `CONTRIBUTING.md` | This file — how to contribute |
| `DISCLAIMER.md` | What Yoker is, does, and the risks involved |
| `AGENTS.md` | Codebase map and conventions for code agents |
| `examples/` | Runnable examples with `examples/README.md` as the index |

After updating docs, verify they build correctly:

```bash
make docs
```

## Testing

- Write tests for new features and bug fixes.
- Tests live in `tests/` and mirror the `src/yoker/` structure.
- Use pytest. Run specific tests with `make test TEST=path/to/test_file.py`.
- Run a single test function with `make test TEST=path/to/test_file.py::test_name`.
- Focus on testing **behavior**, not implementation details.
- See [AGENTS.md](AGENTS.md) for the testing philosophy.

## Questions?

- Open an issue on [GitHub](https://github.com/christophevg/yoker/issues) for
  bugs, feature requests, or questions.
- Read [AGENTS.md](AGENTS.md) for detailed codebase conventions.
- Read [DISCLAIMER.md](DISCLAIMER.md) to understand the security implications
  of the project.
