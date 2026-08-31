"""Version-guarded ``tomllib`` shim for the test suite.

:mod:`tomllib` ships with Python 3.11+; on 3.10 we fall back to the
``tomli`` backport, which is declared in the ``dev`` extra with a
``python_version < '3.11'`` marker.
"""

import sys

if sys.version_info >= (3, 11):
  import tomllib
else:  # pragma: no cover - depends on the interpreter running the tests
  try:
    import tomli as tomllib
  except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
      "Python < 3.11 requires the 'tomli' backport for these tests. "
      "Install the dev extra: uv sync --all-extras"
    ) from exc

__all__ = ["tomllib"]
