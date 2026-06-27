# Testing Review: MBI-002 Bootstrap Wizard (Logic Coverage)

**Reviewer:** testing-engineer
**Branch:** `feature/mbi-002-bootstrap` (commits `552d20b`, `a26d42f`)
**Scope:** Logic components only — wizard IO explicitly excluded per owner's
PR #34 directive ("pure IO and user interaction; testing is user-driven").
**Phase:** 8c — test coverage and quality review, following a passed
functional review.

## Verdict

**APPROVED** — with one recommended logic-coverage gap to fill
(`modellist.py`) and two minor suggestions. The core testable logic of
MBI-002 is well-covered by high-quality, non-brittle tests. No blocking
gaps in the logic the owner asked to be tested.

## Files Reviewed

| File | Role | Tests |
|------|------|-------|
| `src/yoker/bootstrap/detect.py` | Logic — `config_provided()` | `tests/test_bootstrap/test_config_provided.py` (12 tests) |
| `src/yoker/config/writer.py` | Logic — `ConfigWriter` rendering | `tests/test_config/test_writer.py` (16 tests) |
| `src/yoker/config/__init__.py` | Logic — default-model single source | `tests/test_config.py::TestSingleDefaultModel` |
| `src/yoker/bootstrap/modellist.py` | Logic — curated list construction | **none** |
| `src/yoker/bootstrap/steps.py` | Wizard IO (excluded) | none (per directive) |
| `src/yoker/bootstrap/wizard.py` | Wizard IO orchestration (excluded) | none (per directive) |

## Coverage Measurements

From `pytest tests/test_bootstrap/ tests/test_config/ tests/test_config.py
--cov=src/yoker/bootstrap --cov=src/yoker/config/writer`:

| Module | Coverage | Untested lines |
|--------|----------|----------------|
| `bootstrap/detect.py` | 100% | — |
| `bootstrap/__init__.py` | 100% | — |
| `config/writer.py` | 95% | 71–75 (dict rendering) |
| `bootstrap/modellist.py` | 73% | 46–47, 65–66 (`default_model_id`, `curated_models` bodies) |
| `bootstrap/steps.py` | 19% | wizard IO (excluded by directive) |
| `bootstrap/wizard.py` | 41% | wizard IO orchestration (excluded by directive) |

Full suite: **1304 passed, 6 warnings** — no existing tests broken by the
change. Updated fixture literals in `test_commands/test_agents.py`,
`test_main.py`, `test_tools/test_agent.py` (old `llama3.2:latest` → new
default) all pass.

## 1. `config_provided()` Coverage — Strong

Twelve tests across three well-named classes (`TestConfigProvidedFiles`,
`TestConfigProvidedCLI`, `TestConfigProvidedPaths`).

Covered:
- True cases: user file, project file, both files, empty-but-created file.
- False cases: no files + no CLI, empty CLI, unknown flag.
- CLI detection: yoker flag (`--backend-ollama-model`), UI flag
  (`--ui-mode`), short-circuit when file exists.
- Exclusion rules: `--help`/`-h` and `--with`/`--with=` do not count.
- Path handling: `~` tilde expansion via `HOME` monkeypatch (both
  absent and present cases on the same expanded path).

Quality:
- `tmp_path` and `monkeypatch.setenv("HOME", …)` used correctly; no
  leakage of real home directory.
- Assertions are boolean (`is True` / `is False`) — precise, not truthy.
- `test_empty_toml_file_counts_as_provided` correctly locks the
  "consciously created but empty file is still provided" design decision
  from `analysis/bootstrap-config-detection.md`.

No gaps. Edge cases (missing path, tilde, empty TOML, short-circuit,
exclusions) are all hit.

## 2. `ConfigWriter` Coverage — Strong

Sixteen tests across five classes. Round-trip via `tomllib.loads` is the
right validation primitive — it proves the output is real TOML, not just
string-matching.

Covered:
- Render basics: valid TOML, trailing newline, `None` defaults omitted
  (the `api_key` case — exactly the bootstrap-relevant field).
- Annotation-driven comments: `model` and `base_url` help text surfaces
  as inline `# …` comments; negative case (`version` has no `help`) emits
  no comment.
- Overrides: replace value, add `api_key`, do not mutate the input
  `Config` (frozen-dataclass immutability preserved through
  `dataclasses.replace`).
- Generic property: `test_new_annotated_field_is_rendered_automatically`
  builds a throwaway dataclass with a fresh `metadata={"help": …}` field
  and asserts it renders without writer changes. This is the single
  best test in the suite — it directly verifies the "no writer change
  for new config fields" guarantee that the docstring claims.
- `write_config`: creates file, applies `chmod 600` on create, tightens
  a pre-existing `0o644` file to `0o600`, and tightens when an API key
  is supplied via overrides.
- Round-trip: default `Config()` renders → parses → key wizard fields
  survive.

Quality:
- No over-mocking. Tests exercise the real writer and real `tomllib`.
- `tmp_path` used for all file writes; no real-filesystem mutation.
- Permission assertions use `stat.st_mode & 0o777`, portable across
  platforms.
- The "new annotated field picked up automatically" property test is
  the right way to guard the generic-introspection design — it would
  catch a regression to hardcoded field names.

## 3. Default-Model Guard — Adequate, Could Be Stronger

`TestSingleDefaultModel::test_no_stale_default_literal_in_source`
walks `src/yoker/` and asserts the old literal `llama3.2:latest` does
not appear in any `.py` file. This guards against stale regressions of
the old default and is not brittle (no string-counting, no path
hardcoding beyond `src/yoker`).

Weaker than its name implies: it only catches the **old** literal. If
someone introduced a **second** copy of the **new** default
(`gemini-3-flash-preview:cloud`) outside `config/__init__.py`, this
test would not catch it. The class docstring promises "the default
model must be defined in exactly one place" but the assertion does not
fully enforce that. `TestConfigSchema::test_default_model_is_gemini_cloud`
locks the Config value itself, and `modellist.py` reads from Config
(no literal), so the single-source property holds by construction —
but the guard test is one-directional.

Not blocking. See suggestion S3 below for a stronger, still-non-brittle
version.

## 4. Test Quality — High

- No `pass` / `assert True` / empty bodies.
- Gherkin-style intent is conveyed via test names and docstrings; no
  brittle Given/When/Then comments to maintain.
- `tmp_path` and `monkeypatch` used idiomatically; no fixture leakage.
- No flaky patterns (no `time.sleep`, no real network, no real home
  directory, no reliance on umask — `write_config` explicitly `chmod`s
  and the tests assert the resulting mode).
- No excessive mocking of `UIHandler` — the wizard IO path is
  correctly left untested per the owner's directive.
- Test names describe behavior (`test_empty_toml_file_counts_as_provided`,
  `test_write_tightens_permissions_on_existing_file`), not implementation.

## 5. Gaps in LOGIC Coverage

### G1 (recommended): `modellist.py` — pure logic, untested

`src/yoker/bootstrap/modellist.py` exposes two **pure logic** functions
(not IO):

- `default_model_id(config)` — returns `config.backend.ollama.model`
  (or `Config().backend.ollama.model` when `config is None`).
- `curated_models(config)` — returns the curated list with the default
  model first, label `"<id> (default)"`, and a fixed set of cloud/local
  entries.

Coverage report: lines 46–47 and 65–66 (both function bodies) are
unexecuted by any test. These are referenced only by `steps.py`, which
is (correctly) not unit-tested.

Why it matters:
- `default_model_id()` returning `Config().backend.ollama.model` is the
  runtime expression of the MBI-002 task 2.0 "single source of truth"
  guarantee. A regression here (e.g. someone hardcodes a literal in
  `modellist.py`) would silently break that guarantee and the
  stale-literal guard would not catch it.
- `curated_models()` placing the default first is a UX-critical
  guarantee ("accepting the default is a single keystroke" —
  `modellist.py` docstring). A regression reordering the list would
  change the first keystroke's meaning with no test failure.

These are logic, not wizard IO, and fall inside the owner's testing
directive. The functions are small and a test is ~10 lines.

Suggested test (`tests/test_bootstrap/test_modellist.py`):

```python
from yoker.bootstrap.modellist import curated_models, default_model_id
from yoker.config import Config


def test_default_model_id_matches_config_default():
  """default_model_id() reads from Config — single source of truth."""
  assert default_model_id() == Config().backend.ollama.model


def test_curated_models_has_default_first():
  """The first curated entry is the Config default, labelled as such."""
  models = curated_models()
  default_id = Config().backend.ollama.model
  assert models[0].model_id == default_id
  assert models[0].label == f"{default_id} (default)"


def test_curated_models_is_non_empty_and_unique():
  ids = {m.model_id for m in curated_models()}
  assert len(ids) == len(curated_models())  # no duplicates
  assert len(curated_models()) >= 3
```

### S1 (minor): `writer.py` dict rendering path uncovered (lines 71–75)

`_format_scalar` has a `dict` branch (lines 71–75) that is never
exercised. `Config` has two dict-typed fields (`handlers`, `trusted`)
that default to empty and are therefore omitted by the
`if not value: return None` guard, so the default-`Config()` round-trip
never reaches the dict-serialization branch.

The branch is reachable via overrides, e.g.
`overrides={"plugins.trusted": {"pkgq": True}}`. The writer is
documented as reusable for "in-session config augmentation", so a non-
empty dict override is a real use case. A one-line addition to an
existing override test would close this:

```python
def test_override_can_add_dict_value():
  toml_text = render_config_toml(
    Config(), overrides={"plugins.trusted": {"pkgq": True}}
  )
  parsed = tomllib.loads(toml_text)
  assert parsed["plugins"]["trusted"] == {"pkgq": True}
```

Not blocking — the bootstrap wizard only sets `model` and `api_key`
(string) overrides, so this path is not exercised by MBI-002's primary
flow. Noted for completeness because the writer is generic.

### S2 (minor, out of scope): `__main__.py` bootstrap gate

`_abort_non_interactive()` and the
`config_provided() → not sys.stdin.isatty() → abort` gate in `main()`
are logic-adjacent orchestration. They are borderline between "logic"
and "process-level IO" and are most naturally tested at subprocess
level (an integration test), which is out of scope for this logic-only
review. Not blocking; flagging for awareness only.

### S3 (minor): stronger single-source guard (optional)

If the team wants the `TestSingleDefaultModel` guard to actually
enforce "exactly one place", a stronger, still-non-brittle version
would assert the **new** default literal appears in exactly one source
file:

```python
def test_default_literal_appears_in_exactly_one_source_file():
  src_root = Path(__file__).parent.parent / "src" / "yoker"
  locations = []
  for path in src_root.rglob("*.py"):
    if "__pycache__" in path.parts:
      continue
    if "gemini-3-flash-preview:cloud" in path.read_text(encoding="utf-8"):
      locations.append(str(path.relative_to(src_root)))
  assert locations == ["config/__init__.py"], (
    f"default literal found in unexpected locations: {locations}"
  )
```

This subsumes the stale-literal check (a second copy of the new
default would fail) and enforces the docstring's actual claim. Keep
the existing stale-literal test too, or replace it — either is fine.
Optional; not blocking.

## 6. Existing Tests Not Broken

Confirmed by the full-suite run (1304 passed). The three updated
fixture literals (`llama3.2:latest` → `gemini-3-flash-preview:cloud`)
in `test_commands/test_agents.py`, `test_main.py`, and
`test_tools/test_agent.py` are test-data updates consistent with the
new default, not regressions. They keep the fixtures aligned with the
single source of truth rather than introducing new literals.

## Summary Table

| Area | Verdict | Notes |
|------|---------|-------|
| `config_provided()` | Strong | 100% coverage, all edge cases hit |
| `ConfigWriter` rendering | Strong | 95%, generic-property test is exemplary |
| `ConfigWriter` chmod 600 | Strong | Both create and pre-existing cases covered |
| Default-model guard | Adequate | One-directional; S3 would strengthen |
| `modellist.py` logic | **Gap (G1)** | Pure logic, untested — recommended fix |
| `writer.py` dict path | Minor (S1) | Reachable via overrides, not in wizard flow |
| `__main__` gate | Out of scope (S2) | Subprocess-level, not logic-unit-testable |
| Wizard IO | Excluded | Per owner directive — correctly not tested |
| Existing tests | Intact | 1304 pass, fixture literals updated cleanly |

## Recommendation

Approve. The one substantive logic-coverage gap is `modellist.py`,
which is pure logic and trivially testable (~10 lines, suggested above).
I recommend filling G1 before merge as it directly guards the
single-source-of-truth principle that MBI-002 task 2.0 establishes.
S1 and S3 are optional polish. No blocking issues.