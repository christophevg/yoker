-include ~/.claude/Makefile

.PHONY: env-dev env-run install-pythons test test-cov test-all test-file test-one format lint typecheck check run docs docs-view build publish publish-test clean clean-all help demo demos

## Environment

env-dev: ## Install all dependencies (dev + docs)
	uv sync --all-extras

env-run: ## Install runtime dependencies only
	uv sync

install-pythons: ## Install Python 3.10, 3.11, 3.12
	uv python install 3.10 3.11 3.12

## Testing

test: env-dev ## Run tests (usage: make test / optional: TEST=file|file:test_name)
	uv run pytest -v $(TEST)

test-cov: env-dev ## Run tests with coverage
	uv run pytest --cov=src --cov-report=term-missing

test-all: env-dev ## Run tests on all Python versions
	uv run tox

## Code Quality

format: env-dev ## Format code and fix linting issues
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint: env-dev ## Check code for linting issues
	uv run ruff check src tests

typecheck: env-dev ## Run type checking
	uv run mypy --strict src

check: format lint typecheck test ## Run all quality checks

## Running

run: env-run ## Run the application
	uv run python -m yoker

## Documentation

docs: env-dev ## Build HTML documentation
	cd docs && uv run sphinx-build -M html . _build

docs-view: docs ## Build and open documentation
	open docs/_build/html/index.html

## Demo Screenshots

demo: ## Generate main session screenshot (media/session.svg)
	uv run python scripts/demo_session.py --script demos/session.md

demos: ## Generate all demo screenshots
	uv run python scripts/demo_session.py --scripts-dir demos/

## Build & Publish

build: ## Build distribution packages
	uv build

publish: clean build ## Publish to PyPI
	uv run twine upload dist/*

publish-test: build ## Publish to TestPyPI
	uv run twine upload --repository testpypi dist/*

## Cleanup

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .coverage .mypy_cache .ruff_cache
	rm -rf docs/_build
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Remove virtualenv and lock file
	rm -rf .venv uv.lock

## Help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | grep -v "install-pythons\|sync" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
