-include ~/.claude/Makefile

# MODEL=glm-5.2:cloud

.PHONY: env-dev env-run install-pythons test test-cov test-all test-file test-one format lint typecheck check run docs docs-view build publish publish-test pre-publish clean clean-all help demo demos

## Environment

env-dev: ## Install all dependencies (dev + docs)
	uv sync --all-extras
	uv pip install -e examples/plugins/demo

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
	uv run ruff format src tests examples
	uv run ruff check --fix src tests examples

lint: env-dev ## Check code for linting issues
	uv run ruff check src tests examples

typecheck: env-dev ## Run type checking
	uv run mypy src examples

format-check: format lint typecheck  ## Run all quality checks

check: format-check test ## Run all quality checks and test

check-all: format-check test-all ## Run all quality checks and test all

size:
	@echo "src/"
	@find src/ | grep "\.py$$" | xargs wc -l | sort -rn | head -10
	@echo "tests/"
	@find tests/ | grep "\.py$$" | xargs wc -l | sort -rn | head -10

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

pre-publish: check ## Pre-publication checks (run before publishing)
	@echo "Checking for relative image paths in README..."
	@grep -n '!\[.*](media/' README.md && (echo "ERROR: Relative image paths found - use raw GitHub URLs for PyPI"; exit 1) || echo "OK: No relative image paths"
	@echo "Checking version sync..."
	@VERSION_PY=$$(grep '^version =' pyproject.toml | cut -d'"' -f2); \
	VERSION_INIT=$$(grep '^__version__ = ' src/yoker/__init__.py | cut -d'"' -f2); \
	if [ "$$VERSION_PY" != "$$VERSION_INIT" ]; then \
		echo "ERROR: Version mismatch - pyproject.toml ($$VERSION_PY) vs __init__.py ($$VERSION_INIT)"; \
		exit 1; \
	fi; \
	echo "OK: Versions match ($$VERSION_PY)"
	@echo "Pre-publication checks passed"

publish: clean build ## Publish to PyPI (runs pre-publish checks)
	@$(MAKE) pre-publish
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

