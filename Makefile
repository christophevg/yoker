-include ~/.claude/Makefile

# Virtual environment configuration
VENV_NAME := yoker
PYTHON_VERSION := 3.11

.PHONY: setup activate install test test-all test-3.10 test-3.11 test-3.12 test-file typecheck lint format build publish clean clean-all help docs docs-view

# Guard to ensure virtual environment is active
define check_venv
  @if [ -z "$(VIRTUAL_ENV)" ] && [ "$(shell pyenv version-name 2>/dev/null)" != "$(VENV_NAME)" ]; then \
    echo "Error: No virtual environment detected. Run 'pyenv activate $(VENV_NAME)' or 'source .venv/bin/activate' first."; \
    exit 1; \
  fi
endef

## Setup

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

activate: ## Show instructions to activate the virtual environment
	@echo "Activate the virtual environment:"
	@echo "  pyenv activate $(VENV_NAME)"
	@echo ""
	@echo "Or add to .python-version for automatic activation:"
	@echo "  echo '$(VENV_NAME)' > .python-version"

install: ## Install package in development mode with dev dependencies
	$(check_venv)
	pip install -e ".[dev]"

## Testing

test: ## Run all tests with coverage
	$(check_venv)
	pytest

test-file: ## Run specific test file (usage: make test-file FILE=tests/test_package.py)
	$(check_venv)
	pytest $(FILE)

test-one: ## Run specific test function (usage: make test-one TEST=tests/test_package.py::test_import)
	$(check_venv)
	pytest $(TEST)

test-all: ## Run tests against all supported Python versions (3.10, 3.11, 3.12)
	tox

test-3.10: ## Run tests against Python 3.10 only
	tox -e py310

test-3.11: ## Run tests against Python 3.11 only
	tox -e py311

test-3.12: ## Run tests against Python 3.12 only
	tox -e py312

## Documentation

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

## Code Quality

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

## Build & Publish

build: ## Build package distributions
	$(check_venv)
	python -m build

publish: build ## Build and publish to PyPI
	$(check_venv)
	twine upload dist/*

publish-test: build ## Build and publish to TestPyPI
	$(check_venv)
	twine upload --repository testpypi dist/*

## Cleanup

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

## Help

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
