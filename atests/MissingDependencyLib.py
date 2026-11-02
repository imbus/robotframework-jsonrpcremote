"""Test-only library, loaded on the server via --pythonpath: its import fails because of a missing module."""

import a_module_that_does_not_exist  # type: ignore[import-not-found]  # noqa: F401


class MissingDependencyLib:
    pass
