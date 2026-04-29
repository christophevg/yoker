# migrate-to-hatchling Implementation Summary

**Date:** 2026-04-29

## Task

Migrate yoker project from setuptools.build_meta to hatchling build backend.

## Changes Made

### pyproject.toml

| Section | Before | After |
|---------|--------|-------|
| `[build-system] requires` | `["setuptools>=61.0", "wheel"]` | `["hatchling"]` |
| `[build-system] build-backend` | `"setuptools.build_meta"` | `"hatchling.build"` |
| `[project] license` | `"MIT"` + `license-files` | `{text = "MIT"}` |
| `[tool.setuptools.packages.find]` | `where = ["src"]` | **Removed** |
| `[tool.setuptools.package-data]` | `yoker = ["py.typed"]` | **Removed** |
| `[tool.hatch.build]` | *N/A* | `sources = ["src"]` |
| `[tool.hatch.build.targets.wheel]` | *N/A* | `packages = ["src/yoker"]` |

## Verification Results

All acceptance criteria passed:

| Criteria | Result |
|----------|--------|
| `pip install -e ".[dev]"` | ✅ Success |
| `make test` | ✅ 487 tests pass |
| `python -m build` | ✅ Built sdist + wheel |
| `twine check dist/*` | ✅ PASSED |
| `python -m yoker --help` | ✅ Entry point works |

## Files Modified

- `pyproject.toml` - Updated build configuration
- `TODO.md` - Task marked complete

## Benefits of Hatchling

- **Smaller**: 83 kB vs setuptools' 894 kB
- **Simpler config**: Fewer `[tool.*]` sections
- **PEP 639**: Modern license metadata format
- **Gitignore support**: Won't accidentally include test/tooling directories
- **Auto-includes**: `py.typed` marker included automatically

## Notes

- All existing tool configurations (pytest, mypy, ruff, coverage, tox) preserved
- No changes to package structure or source code required
- Build artifacts verified with twine check