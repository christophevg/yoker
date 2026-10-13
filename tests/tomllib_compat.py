"""Re-export ``tomllib`` from the standard library for the test suite.

:mod:`tomllib` ships with Python 3.11+, and yoker now requires 3.11+,
so the former version-guarded shim (tomli backport on 3.10) collapses
to a plain re-export.
"""

import tomllib

__all__ = ["tomllib"]
