#MODEL=qwen3.5:397b-cloud    # sometimes qwen is better
#ARGS += --plugin-dir ./		 # future: when we expose a baseweb: plugin
ARGS += --plugin-dir ../c3   # always use the local C3 plugin - latest version

-include ~/.claude/Makefile

# Python version for documentation purposes
PYTHON_VERSION := 3.11

.PHONY: setup install test test-all test-3.10 test-3.11 test-3.12 test-file test-one typecheck lint format build publish publish-test clean clean-all help docs docs-view demo demos

## Setup

setup: ## Create virtual environment and install dependencies
	@echo "Creating virtual environment with Python $(PYTHON_VERSION)..."
	uv venv --python $(PYTHON_VERSION)
	@echo ""
	@echo "Installing dependencies..."
	uv sync
	@echo ""
	@echo "Setup complete. Run 'make install' to reinstall dependencies."

install: ## Install package in development mode with dev dependencies
	uv sync

## Testing

test: ## Run all tests with coverage
	uv run pytest

test-file: ## Run specific test file (usage: make test-file FILE=tests/test_package.py)
	uv run pytest $(FILE)

test-one: ## Run specific test function (usage: make test-one TEST=tests/test_package.py::test_import)
	uv run pytest $(TEST)

test-all: ## Run tests against all supported Python versions (3.10, 3.11, 3.12)
	uv run tox

test-3.10: ## Run tests against Python 3.10 only
	uv run tox -e py310

test-3.11: ## Run tests against Python 3.11 only
	uv run tox -e py311

test-3.12: ## Run tests against Python 3.12 only
	uv run tox -e py312

## Documentation

docs: ## Build HTML documentation
	cd docs && uv run make html

docs-view: docs ## Build and open documentation in browser
	@echo "Opening documentation..."
	@if command -v open >/dev/null; then \
	  open docs/_build/html/index.html; \
	elif command -v xdg-open >/dev/null; then \
	  xdg-open docs/_build/html/index.html; \
	fi

## Demo Screenshots

demo: ## Generate main session screenshot (media/session.svg)
	uv run python scripts/demo_session.py --script demos/session.md

demos: ## Generate all demo screenshots
	uv run python scripts/demo_session.py --scripts-dir demos/

## Code Quality

typecheck: ## Run mypy type checking
	uv run mypy --strict src

lint: ## Run ruff linting
	uv run ruff check src tests

format: ## Format code with ruff
	uv run ruff format src tests

check: typecheck lint ## Run all checks (typecheck + lint)

## Build & Publish

build: ## Build package distributions
	uv build

publish: build ## Build and publish to PyPI
	uv run twine upload dist/*

publish-test: build ## Build and publish to TestPyPI
	uv run twine upload --repository testpypi dist/*

## Cleanup

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

## Help

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
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | grep -v "setup\|install\|docs" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'