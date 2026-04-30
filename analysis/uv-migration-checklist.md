# UV Migration Checklist

This document provides a detailed checklist for migrating the yoker project from pyenv to uv for dependency management.

## Overview

**Current Setup:**
- pyenv virtualenv named "yoker" with Python 3.11
- `.python-version` contains "yoker" (pyenv virtualenv name)
- `pip install -e ".[dev]"` for installation
- Tools (pytest, ruff, mypy, build, twine) run directly from venv
- tox for multi-version testing

**Target Setup:**
- uv for unified dependency management
- `uv sync` creates venv and installs dependencies
- `uv run <command>` for all tool execution
- `uv.lock` for reproducible builds
- `.python-version` contains version number only (uv uses this)
- uv-managed tox or alternative for multi-version testing

## Pre-Migration Verification

Before starting migration, verify current state works:

- [ ] Run `make test` and confirm all tests pass
- [ ] Run `make check` and confirm typecheck and lint pass
- [ ] Run `make build` and confirm package builds successfully
- [ ] Run `make docs` and confirm documentation builds
- [ ] Run `make demo` and confirm demo session works
- [ ] Document current test count for verification after migration

## File Changes

### 1. .python-version File

**Current:** Contains "yoker" (pyenv virtualenv name)

**Target:** Contains version number only

```bash
# Before
yoker

# After
3.11
```

**Rationale:** uv respects .python-version file but expects a Python version, not a virtualenv name. pyenv also works with version numbers in .python-version.

**Commands:**
```bash
echo "3.11" > .python-version
```

### 2. pyproject.toml

**Status:** No changes required

The current pyproject.toml is compatible with uv:
- Uses hatchling build backend (uv supports this)
- Dependencies are properly declared
- Optional dependencies (dev) are properly declared
- Tool configurations (pytest, mypy, ruff, tox) are standard

**Verification:**
- [ ] Confirm `uv pip compile pyproject.toml --dev` succeeds
- [ ] Confirm dependency resolution matches expectations

### 3. Makefile

**Major refactoring required.** Replace pyenv-specific commands with uv commands.

#### 3.1 Remove Virtual Environment Guard

**Current:** Complex venv guard checking pyenv activation
**Target:** Remove guard (uv manages its own venv)

```makefile
# REMOVE this entire block:
define check_venv
  @if [ -z "$(VIRTUAL_ENV)" ] && [ "$(shell pyenv version-name 2>/dev/null)" != "$(VENV_NAME)" ]; then \
    echo "Error: No virtual environment detected. Run 'pyenv activate $(VENV_NAME)' or 'source .venv/bin/activate' first."; \
    exit 1; \
  fi
endef
```

#### 3.2 Remove VENV_NAME and PYTHON_VERSION Variables

**Current:**
```makefile
VENV_NAME := yoker
PYTHON_VERSION := 3.11
```

**Target:** Remove or replace with:
```makefile
PYTHON_VERSION := 3.11
```

Keep PYTHON_VERSION for documentation purposes and possible version-specific commands.

#### 3.3 Update Setup Target

**Current:**
```makefile
setup: ## Create pyenv virtualenv and install dependencies
	@echo "Creating pyenv virtualenv '$(VENV_NAME)' with Python $(PYTHON_VERSION)..."
	@if pyenv versions | grep -q "$(VENV_NAME)"; then \
	  echo "Virtualenv '$(VENV_NAME)' already exists."; \
	else \
	  pyenv virtualenv $(PYTHON_VERSION) $(VENV_NAME); \
	  echo "Created virtualenv '$(VENV_NAME)'."; \
	fi
	@echo ""
	@echo "To activate, run:"
	@echo "  pyenv activate $(VENV_NAME)"
	@echo ""
	@echo "Then install dependencies:"
	@echo "  make install"
```

**Target:**
```makefile
setup: ## Create virtual environment and install dependencies
	@echo "Creating virtual environment with Python $(PYTHON_VERSION)..."
	uv venv --python $(PYTHON_VERSION)
	@echo ""
	@echo "Installing dependencies..."
	uv sync
	@echo ""
	@echo "Setup complete. Run 'make install' to reinstall dependencies."
```

#### 3.4 Update Activate Target

**Current:**
```makefile
activate: ## Show instructions to activate the virtual environment
	@echo "Activate the virtual environment:"
	@echo "  pyenv activate $(VENV_NAME)"
	@echo ""
	@echo "Or add to .python-version for automatic activation:"
	@echo "  echo '$(VENV_NAME)' > .python-version"
```

**Target:**
```makefile
activate: ## Show instructions to activate the virtual environment
	@echo "The virtual environment is managed by uv."
	@echo ""
	@echo "Use 'uv run <command>' to run commands in the virtual environment:"
	@echo "  uv run pytest        # Run tests"
	@echo "  uv run mypy src      # Run type checking"
	@echo "  uv run ruff check    # Run linting"
	@echo ""
	@echo "Or activate manually:"
	@echo "  source .venv/bin/activate"
	@echo ""
	@echo "For pyenv users with automatic activation:"
	@echo "  The .python-version file contains '3.11' for version selection."
	@echo "  pyenv will use this version if installed."
```

#### 3.5 Update Install Target

**Current:**
```makefile
install: ## Install package in development mode with dev dependencies
	$(check_venv)
	pip install -e ".[dev]"
```

**Target:**
```makefile
install: ## Install package in development mode with dev dependencies
	uv sync
```

#### 3.6 Update Test Targets

**Current:**
```makefile
test: ## Run all tests with coverage
	$(check_venv)
	pytest

test-file: ## Run specific test file (usage: make test-file FILE=tests/test_package.py)
	$(check_venv)
	pytest $(FILE)

test-one: ## Run specific test function (usage: make test-one TEST=tests/test_package.py::test_import)
	$(check_venv)
	pytest $(TEST)
```

**Target:**
```makefile
test: ## Run all tests with coverage
	uv run pytest

test-file: ## Run specific test file (usage: make test-file FILE=tests/test_package.py)
	uv run pytest $(FILE)

test-one: ## Run specific test function (usage: make test-one TEST=tests/test_package.py::test_import)
	uv run pytest $(TEST)
```

#### 3.7 Update Multi-Version Test Targets (tox)

**Current:**
```makefile
test-all: ## Run tests against all supported Python versions (3.10, 3.11, 3.12)
	tox

test-3.10: ## Run tests against Python 3.10 only
	tox -e py310

test-3.11: ## Run tests against Python 3.11 only
	tox -e py311

test-3.12: ## Run tests against Python 3.12 only
	tox -e py312
```

**Target Options:**

Option A: Keep tox (runs in its own environment, uv manages dependencies)
```makefile
test-all: ## Run tests against all supported Python versions (3.10, 3.11, 3.12)
	uv run tox

test-3.10: ## Run tests against Python 3.10 only
	uv run tox -e py310

test-3.11: ## Run tests against Python 3.11 only
	uv run tox -e py311

test-3.12: ## Run tests against Python 3.12 only
	uv run tox -e py312
```

Option B: Use uv's native multi-version testing (if available)
```makefile
# TODO: Check if uv supports multi-version testing natively
# For now, keep tox approach
test-all: ## Run tests against all supported Python versions (3.10, 3.11, 3.12)
	uv run tox
```

**Recommendation:** Use Option A (uv run tox) for now. tox will use its own environments, which is acceptable.

#### 3.8 Update Documentation Targets

**Current:**
```makefile
docs: ## Build HTML documentation
	$(check_venv)
	cd docs && make html

docs-view: docs ## Build and open documentation in browser
	@echo "Opening documentation..."
	@if command -v open >/dev/null; then \
	  open docs/_build/html/index.html; \
	elif command -v xdg-open >/dev/null; then \
	  xdg-open docs/_build/html/index.html; \
	fi
```

**Target:**
```makefile
docs: ## Build HTML documentation
	cd docs && uv run make html

docs-view: docs ## Build and open documentation in browser
	@echo "Opening documentation..."
	@if command -v open >/dev/null; then \
	  open docs/_build/html/index.html; \
	elif command -v xdg-open >/dev/null; then \
	  xdg-open docs/_build/html/index.html; \
	fi
```

Note: The docs/Makefile uses sphinx-build directly. We may need to run sphinx-build via uv:
```makefile
docs: ## Build HTML documentation
	uv run sphinx-build -b html docs docs/_build/html
```

#### 3.9 Update Demo Targets

**Current:**
```makefile
demo: ## Generate main session screenshot (media/session.svg)
	$(check_venv)
	python scripts/demo_session.py --script demos/session.md

demos: ## Generate all demo screenshots
	$(check_venv)
	python scripts/demo_session.py --scripts-dir demos/
```

**Target:**
```makefile
demo: ## Generate main session screenshot (media/session.svg)
	uv run python scripts/demo_session.py --script demos/session.md

demos: ## Generate all demo screenshots
	uv run python scripts/demo_session.py --scripts-dir demos/
```

#### 3.10 Update Code Quality Targets

**Current:**
```makefile
typecheck: ## Run mypy type checking
	$(check_venv)
	mypy --strict src

lint: ## Run ruff linting
	$(check_venv)
	ruff check src tests

format: ## Format code with ruff
	$(check_venv)
	ruff format src tests

check: typecheck lint ## Run all checks (typecheck + lint)
```

**Target:**
```makefile
typecheck: ## Run mypy type checking
	uv run mypy --strict src

lint: ## Run ruff linting
	uv run ruff check src tests

format: ## Format code with ruff
	uv run ruff format src tests

check: typecheck lint ## Run all checks (typecheck + lint)
```

#### 3.11 Update Build and Publish Targets

**Current:**
```makefile
build: ## Build package distributions
	$(check_venv)
	python -m build

publish: build ## Build and publish to PyPI
	$(check_venv)
	twine upload dist/*

publish-test: build ## Build and publish to TestPyPI
	$(check_venv)
	twine upload --repository testpypi dist/*
```

**Target:**
```makefile
build: ## Build package distributions
	uv build

publish: build ## Build and publish to PyPI
	uv run twine upload dist/*

publish-test: build ## Build and publish to TestPyPI
	uv run twine upload --repository testpypi dist/*
```

Note: uv has a built-in `uv build` command that replaces `python -m build`.

#### 3.12 Update Cleanup Targets

**Current:**
```makefile
clean: ## Remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf src/*.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Remove virtualenv as well
	@echo "Removing pyenv virtualenv '$(VENV_NAME)'..."
	-pyenv deactivate 2>/dev/null || true
	-pyenv virtualenv-delete -f $(VENV_NAME) 2>/dev/null || true
	@echo "Virtualenv removed."
```

**Target:**
```makefile
clean: ## Remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf src/*.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Remove virtual environment and lock file
	@echo "Removing virtual environment..."
	rm -rf .venv
	rm -f uv.lock
	@echo "Virtual environment and lock file removed."
	@echo ""
	@echo "Run 'make setup' to recreate the environment."
```

#### 3.13 Update Help Target

**Current:**
```makefile
help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Virtual Environment:"
	@echo "  make setup        - Create pyenv virtualenv '$(VENV_NAME)'"
	@echo "  make activate     - Show activation instructions"
	@echo "  make install      - Install dependencies (requires venv)"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs         - Build HTML documentation"
	@echo "  make docs-view    - Build and open documentation in browser"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | grep -v "setup\|activate\|install\|docs" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
```

**Target:**
```makefile
help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Virtual Environment:"
	@echo "  make setup        - Create virtual environment and install dependencies"
	@echo "  make install      - Install/update dependencies"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs         - Build HTML documentation"
	@echo "  make docs-view    - Build and open documentation in browser"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | grep -v "setup\|activate\|install\|docs" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
```

### 4. CI/CD Workflow (.github/workflows/tests.yml)

**Current:**
```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -e ".[dev]"

- name: Run tests with coverage
  run: |
    pytest --cov=yoker --cov-report=xml --cov-report=term-missing
```

**Target:**
```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v5
  with:
    version: "latest"

- name: Install dependencies
  run: uv sync

- name: Run tests with coverage
  run: uv run pytest --cov=yoker --cov-report=xml --cov-report=term-missing
```

Full workflow update:
```yaml
name: Tests

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync

      - name: Run tests with coverage
        run: uv run pytest --cov=yoker --cov-report=xml --cov-report=term-missing

      - name: Upload coverage to Coveralls
        if: matrix.python-version == '3.10'
        uses: coverallsapp/github-action@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### 5. Documentation Updates

#### 5.1 README.md

**Development section needs update:**

**Current:**
```markdown
## Development

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker
pip install -e ".[dev]"

make test     # Run tests with coverage
make check    # Type checking + linting
make docs     # Build documentation
```
```

**Target:**
```markdown
## Development

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker
make setup    # Create virtual environment and install dependencies

make test     # Run tests with coverage
make check    # Type checking + linting
make docs     # Build documentation
```

Requires Python 3.10+. Uses [uv](https://docs.astral.sh/uv/) for dependency management.
```

#### 5.2 CLAUDE.md

**Multiple sections need updates:**

**Current Development Setup section:**
```markdown
## Development Setup

Uses pyenv for virtual environment management. A virtual environment is required for all development operations.

```bash
# Create pyenv virtualenv
make setup

# Activate the virtual environment
pyenv activate yoker

# Install dependencies (includes dev dependencies)
make install
```

For automatic activation, a `.python-version` file is already present.
```

**Target:**
```markdown
## Development Setup

Uses uv for unified dependency management. A virtual environment is created automatically by uv.

```bash
# Create virtual environment and install dependencies
make setup

# Or manually:
uv sync
```

For pyenv users, the `.python-version` file contains the Python version (3.11) for automatic version selection.
```

**Current Makefile Usage section:**
```markdown
## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Create pyenv virtualenv |
| `make activate` | Show activation instructions |
| `make install` | Install dev dependencies (venv required) |
```

**Target:**
```markdown
## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Create virtual environment and install dependencies |
| `make install` | Install/update dependencies |
| `make test` | Run tests with coverage |
| `make test-all` | Run tests against all Python versions (tox) |
| `make typecheck` | Run mypy type checking |
| `make lint` | Run ruff linting |
| `make format` | Format code with ruff |
| `make check` | Run all checks (typecheck + lint) |
| `make build` | Build package distributions |
| `make publish` | Build and publish to PyPI |
| `make docs` | Build HTML documentation |
| `make docs-view` | Build and open documentation in browser |
| `make demo` | Generate main session screenshot |
| `make demos` | Generate all demo screenshots |
| `make clean` | Remove build artifacts |
| `make clean-all` | Remove virtual environment and lock file |
```

**Current Pre-Commit Requirements section:**
```markdown
## Pre-Commit Requirements

Before any commit, the following must be verified:

1. **All tests pass:** `make test`
2. **Type checking passes:** `make typecheck`
3. **Linting passes:** `make lint`

**IMPORTANT**: The minimal prototype must remain working. After any refactoring, run:
```bash
python -m yoker
```
And verify it starts correctly.
```

**Target:** No changes needed - commands remain the same via `make`.

### 6. .gitignore Updates

**Add uv-specific entries:**
```gitignore
# uv
uv.lock
.venv/
```

Note: `uv.lock` should typically be committed for applications, but may be excluded for libraries. Decision needed.

**Recommendation:** Keep `uv.lock` in version control for reproducible builds.

### 7. New Files

#### 7.1 uv.lock

After first `uv sync`, a `uv.lock` file will be created. This should be committed to version control.

**Verification:**
- [ ] `uv.lock` exists after `uv sync`
- [ ] `uv.lock` is in version control
- [ ] `uv sync --frozen` succeeds (verifies lock file consistency)

### 8. Migration Execution Steps

Execute in order:

1. **Backup and preparation:**
   - [ ] Run `make test` and save test count
   - [ ] Run `make check` and verify it passes
   - [ ] Run `make build` and verify it succeeds
   - [ ] Commit any pending changes

2. **Update .python-version:**
   - [ ] `echo "3.11" > .python-version`
   - [ ] Verify file contents

3. **Update Makefile:**
   - [ ] Apply all Makefile changes from section 3
   - [ ] Verify syntax: `make -n test` (dry run)
   - [ ] Verify all targets: `make help`

4. **Update CI/CD workflow:**
   - [ ] Apply changes from section 4
   - [ ] Verify YAML syntax

5. **Update documentation:**
   - [ ] Update README.md development section
   - [ ] Update CLAUDE.md development setup and Makefile sections

6. **Update .gitignore:**
   - [ ] Add uv-specific entries if needed

7. **Test new setup:**
   - [ ] Remove old pyenv virtualenv: `pyenv virtualenv-delete -f yoker`
   - [ ] Run `make clean-all`
   - [ ] Run `make setup`
   - [ ] Run `make install`
   - [ ] Run `make test` and verify same test count
   - [ ] Run `make check` and verify it passes
   - [ ] Run `make build` and verify it succeeds
   - [ ] Run `make docs` and verify it builds
   - [ ] Run `make demo` and verify it works
   - [ ] Test `python -m yoker` starts correctly

8. **Commit changes:**
   - [ ] Review all changes
   - [ ] Commit with message: "feat: migrate from pyenv to uv for dependency management"

## Post-Migration Verification

- [ ] `make setup` creates .venv and installs dependencies
- [ ] `make test` passes with same test count as before
- [ ] `make check` passes (typecheck + lint)
- [ ] `make build` produces dist/
- [ ] `make docs` builds documentation
- [ ] `make demo` generates screenshots
- [ ] `python -m yoker` starts correctly
- [ ] `.python-version` contains "3.11" (not "yoker")
- [ ] `uv.lock` exists and is valid
- [ ] CI/CD workflow uses uv
- [ ] README.md reflects uv workflow
- [ ] CLAUDE.md reflects uv workflow
- [ ] No pyenv references remain in codebase (except possibly in comments)

## Breaking Changes and Concerns

### 1. Virtual Environment Activation

**Breaking:** Users can no longer use `pyenv activate yoker` to activate the virtual environment.

**Mitigation:** 
- Document that `uv run <command>` is the recommended approach
- Manual activation still works: `source .venv/bin/activate`
- pyenv users with `.python-version` will have the version selected, but still need manual activation

### 2. Makefile Target Changes

**Breaking:** 
- `make setup` no longer creates pyenv virtualenv
- `make activate` behavior changes

**Mitigation:** Update help text and documentation to reflect new behavior.

### 3. tox Integration

**Concern:** tox creates its own environments. How does this interact with uv?

**Analysis:**
- tox will create its own environments for each Python version
- tox installs dependencies from pyproject.toml
- `uv run tox` will work, but tox won't use uv's venv
- Alternative: Use `uv run --python 3.10 pytest` for multi-version testing

**Mitigation:** 
- Keep tox for now (it's standard for multi-version testing)
- Document that tox manages its own environments
- Consider native uv multi-version testing in the future

### 4. CI/CD Runner Requirements

**Concern:** GitHub Actions runners need uv installed.

**Mitigation:** Use `astral-sh/setup-uv@v5` action to install uv. This is well-supported and fast.

### 5. Developer Workflow Changes

**Breaking:** Developers using pyenv will need to adapt their workflow.

**Mitigation:**
- Clear documentation in README.md
- Document that `make setup` handles everything
- Document `uv run <command>` pattern
- Keep `make` targets familiar (same names)

### 6. Lock File Strategy

**Decision:** Should `uv.lock` be committed?

**Recommendation:** Yes, for reproducible builds.
- Libraries can still be installed without the lock file
- Lock file ensures dev environment consistency
- Lock file speeds up `uv sync`

### 7. .python-version Behavior

**Breaking:** pyenv users expecting automatic activation from `.python-version` will be disappointed.

**Analysis:**
- Old: `.python-version` = "yoker" triggers pyenv activation
- New: `.python-version` = "3.11" only sets Python version
- Users need to manually activate: `source .venv/bin/activate`
- Or use `uv run <command>` which handles everything

**Mitigation:** Document this clearly in README.md and CLAUDE.md.

### 8. Dependency Version Pinning

**Concern:** Does `uv.lock` conflict with pyproject.toml version ranges?

**Analysis:**
- No, they work together
- pyproject.toml specifies version ranges
- uv.lock pins exact versions
- Developers get reproducible builds
- Users installing from PyPI use version ranges

## Rollback Plan

If migration fails or causes issues:

1. **Revert commit:**
   ```bash
   git revert HEAD
   ```

2. **Restore pyenv virtualenv:**
   ```bash
   pyenv virtualenv 3.11 yoker
   pyenv activate yoker
   pip install -e ".[dev]"
   ```

3. **Restore .python-version:**
   ```bash
   echo "yoker" > .python-version
   ```

4. **Verify old workflow works:**
   ```bash
   make test
   make check
   ```

## Success Criteria

Migration is successful when:

1. All tests pass with same count
2. All quality checks pass (typecheck, lint)
3. Build succeeds
4. Documentation builds
5. Demo scripts work
6. Interactive session starts
7. CI/CD pipeline passes
8. No pyenv references in active code
9. Documentation reflects uv workflow
10. Lock file exists and is valid