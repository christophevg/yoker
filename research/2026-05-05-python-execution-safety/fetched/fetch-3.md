# Bandit GitHub Repository

**Source**: https://github.com/pycqa/bandit
**Fetched**: 2026-05-05T00:45:00Z

---

## How Bandit Works (AST Processing)

"Bandit processes each file, builds an AST from it, and runs appropriate plugins against the AST nodes." Once scanning completes, it generates a report. It uses Python's AST module and covers various AST node types.

## Security Issues Detected

Bandit is a "security linter" designed to find "common security issues in Python code." The repository includes an `examples` folder with test cases for different issue patterns.

## Validating Agent-Generated Code

Bandit could scan generated Python code before execution by running it against generated files. The container image option enables isolated scanning environments.

## Integration Patterns

- **CI/CD**: GitHub Actions integration shown via build badges
- **Pre-commit hooks**: `.pre-commit-hooks.yaml` and `.pre-commit-config.yaml` files present
- **Container**: Docker images available via `ghcr.io/pycqa/bandit/bandit` (amd64, arm64, armv7, armv8)
- **Programmatic**: Python package installable via PyPI

## Limitations

The page doesn't detail limitations. It's specifically for Python code only and focuses on "common" security issues, implying it may not catch all vulnerability types.

## Project Stats

- 7,897+ GitHub stars
- 150+ contributors
- Originally developed for OpenStack Security Project
- Active maintenance