"""A separate ServerControl library for suites that need their own server instance.

Robot imports libraries by module name and reuses one instance for GLOBAL-scope
libraries. Being a distinct library/module, ``IsolatedServerControl`` gets its own
instance, so a suite can run its own server on a separate port without clashing with the
shared server started by the top-level ``__init__.robot``.
"""

from ServerControl import ServerControl


class IsolatedServerControl(ServerControl):
    pass
